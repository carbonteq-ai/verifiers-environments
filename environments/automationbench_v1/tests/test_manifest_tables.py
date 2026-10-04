"""Finite collection closure and exact lookup qualify facts, never task policy."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_notification_evidence import run_operations

from automationbench.tools.zapier.google_sheets.row import (
    google_sheets_add_row,
    google_sheets_update_row,
)
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.sheet_effects import SheetEffectSource, capture_sheet_effects
from automationbench_v1.contracts.tables import (
    TableEvidence,
    TableSource,
    capture_table,
    left_lookup,
)


def selector(**changes):
    return TableSource(
        path=("task_evidence", "initial", "google_sheets"),
        spreadsheet_id="sheet",
        worksheet_id="tab",
        key_fields=("Email",),
        required_fields=("Status",),
        **changes,
    )


def row(identity: str | int = 1, email: str | float = "a@example.com", **cells):
    return {
        "spreadsheet_id": "sheet",
        "worksheet_id": "tab",
        "row_id": identity,
        "cells": {"Email": email, "Status": "Pending", **cells},
    }


def material(rows=None):
    return {
        "task_evidence": {
            "initial": {
                "google_sheets": {
                    "worksheets": [{"id": "tab", "spreadsheet_id": "sheet", "title": "Requests"}],
                    "rows": [row()] if rows is None else rows,
                }
            }
        }
    }


def capture(data):
    return capture_table(data, selector())


def test_real_simulator_hydrated_initial_flat_population_has_stable_provenance():
    data = run_operations(material()["task_evidence"]["initial"], [])
    table = capture(data)
    found = left_lookup(table, {"Email": "a@example.com"})
    assert table.closed and table.status == "qualified" and found.status == "matched"
    assert found.matches[0].identity == ("sheet", "tab", "int", 1)
    assert found.matches[0].native_record_id == data["task_evidence"]["initial"]["google_sheets"]["rows"][0]["id"]
    assert found.matches[0].source_path == (*selector().path, "rows", 0)
    assert json.loads(found.matches[0].cells_json)["Status"] == "Pending"
    assert TableEvidence.model_validate_json(table.model_dump_json()) == table


def test_absent_public_native_id_stays_unavailable_without_inventing_one():
    table = capture(material())
    assert table.closed and table.rows[0].native_record_id is None


def captured_public_initial():
    public = material()["task_evidence"]["initial"]
    data = run_operations(public, [("native-read-fixture", {}, lambda world: {"ok": True})])
    expected_id = data["task_evidence"]["initial"]["google_sheets"]["rows"][0]["id"]
    data["task_evidence"]["initial"] = copy.deepcopy(public)
    return data, expected_id


def modify_before(data, change):
    event = data["tool_execution_events"][0]
    receipt = json.loads(event["receipt_json"])
    envelope = json.loads(receipt["evidence_json"][0])
    action = envelope["action"]
    world = json.loads(envelope["snapshots"][action["before_digest"]])
    change(world)
    text = canonical_json(world)
    digest = hashlib.sha256(text.encode()).hexdigest()
    envelope["snapshots"][digest] = text
    action["before_digest"] = digest
    receipt["evidence_json"] = [canonical_json(envelope)]
    event["receipt_json"] = canonical_json(receipt)


def test_public_missing_id_binds_only_to_exact_native_revision_zero_before_world():
    data, expected_id = captured_public_initial()
    assert capture(data).rows[0].native_record_id == expected_id
    assert "id" not in data["task_evidence"]["initial"]["google_sheets"]["rows"][0]


@pytest.mark.parametrize("gap", ["ack", "nonzero", "step", "cells", "extra-cell", "extra-row", "native-id", "row-type", "tab"])
def test_initial_identity_binding_rejects_gaps_and_mismatched_public_scope(gap):
    data, _ = captured_public_initial()
    if gap == "ack":
        data["state_write_receipts"] = []
    elif gap in {"nonzero", "step"}:
        receipt = json.loads(data["tool_execution_events"][0]["receipt_json"])
        start, end = (1, 2) if gap == "nonzero" else (0, 2)
        receipt.update(state_read_revision=start, state_write_revision=end)
        data["tool_execution_events"][0]["receipt_json"] = canonical_json(receipt)
        data["state_write_receipts"][0].update(expected_revision=start, applied_revision=end)
    else:
        def change(world):
            service = world["google_sheets"]
            item = service["rows"][0]
            if gap == "cells":
                item["cells"]["Status"] = "Other"
            elif gap == "extra-cell":
                item["cells"]["Permission"] = "Admin"
            elif gap == "extra-row":
                service["rows"].append({**item, "row_id": 2, "id": "extra"})
            elif gap == "native-id":
                item["id"] = True
            elif gap == "row-type":
                item["row_id"] = "1"
            else:
                service["worksheets"][0]["title"] = "Other"
        modify_before(data, change)
    result = capture(data)
    assert result.rows[0].native_record_id is None
    assert json.loads(result.rows[0].cells_json)["Status"] == "Pending"


def test_all_revision_zero_snapshots_must_agree_on_initial_native_identity():
    data, identity = captured_public_initial()
    second = copy.deepcopy(data)
    modify_before(second, lambda world: world["google_sheets"]["rows"][0].update(id="conflicting-original"))
    receipt = json.loads(second["tool_execution_events"][0]["receipt_json"])
    receipt["invocation_id"] = "second-zero"
    data["tool_execution_events"].append({"source": "tool_server", "receipt_json": canonical_json(receipt)})
    data["state_write_receipts"].append({**second["state_write_receipts"][0], "write_id": "second-zero"})
    assert identity != "conflicting-original"
    assert capture(data).rows[0].native_record_id is None


def test_sha_bound_prepaid_public_initial_native_ids_bind_to_recorded_revision_zero():
    index = Path("/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate/cross-category-selection.json")
    selected = next(item for item in json.loads(index.read_text())["tasks"] if item["task_name"] == "finance.prepaid_amortization")
    raw = Path(selected["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == selected["source_episode_sha256"]
    episode = json.loads(raw)
    trace = episode["traces"][0]
    source = {"task_evidence": {"initial": episode["task"]["data"]["initial_state"]},
              "tool_execution_events": trace["tool_execution_events"],
              "state_write_receipts": trace["state_write_receipts"]}
    spec = TableSource(path=("task_evidence", "initial", "google_sheets"),
                       spreadsheet_id="ss_prepaids", worksheet_id="ws_prepaid_items", key_fields=("Item",))
    table = capture_table(source, spec)
    assert len(table.rows) == 5 and all(row.native_record_id is not None for row in table.rows)
    assert len({row.native_record_id for row in table.rows}) == 5
    assert all("id" not in row for row in source["task_evidence"]["initial"]["google_sheets"]["rows"])


@pytest.mark.parametrize("invalid", [None, "", " ", True, 1, {}, []])
def test_explicit_bad_native_identity_preserves_row_facts_but_not_closure(invalid):
    raw = material()
    raw["task_evidence"]["initial"]["google_sheets"]["rows"][0]["id"] = invalid
    table = capture(raw)
    assert table.status == "partial" and not table.closed
    assert table.rows[0].native_record_id is None
    assert json.loads(table.rows[0].cells_json)["Email"] == "a@example.com"


def test_duplicate_native_identity_cannot_be_laundered_by_different_row_positions():
    rows = [row(1), row(2, "other")]
    for item in rows:
        item["id"] = "same-native-id"
    table = capture(material(rows))
    assert table.status == "unavailable" and len(table.rows) == 2
    data = table.model_dump(mode="json")
    data.update(status="qualified", closed=True, enumerated=True)
    with pytest.raises(ValidationError, match="duplicate_native_identity"):
        TableEvidence.model_validate(data)


def test_retained_native_identity_is_strict_and_source_recapture_exposes_tamper():
    raw = material()
    raw["task_evidence"]["initial"]["google_sheets"]["rows"][0]["id"] = "native-original"
    table = capture(raw)
    restored = TableEvidence.model_validate_json(table.model_dump_json())
    assert restored.rows[0].native_record_id == "native-original"
    data = table.model_dump(mode="json")
    data["rows"][0]["native_record_id"] = True
    with pytest.raises(ValidationError):
        TableEvidence.model_validate(data)
    forged = table.rows[0].model_copy(update={"native_record_id": "replacement"})
    assert canonical_json(table.model_copy(update={"rows": (forged,)}).model_dump(mode="json")) != canonical_json(capture(raw).model_dump(mode="json"))


@pytest.mark.parametrize("omit_public_id", [False, True])
def test_delete_append_same_position_keeps_original_candidate_native_identity(omit_public_id):
    raw = material()["task_evidence"]["initial"]
    raw["google_sheets"]["rows"][0]["row_id"] = 2
    raw["google_sheets"]["rows"][0]["id"] = "protected-original"
    def replace(world):
        world.google_sheets.rows = []
        return google_sheets_add_row(world, spreadsheet="sheet", worksheet="tab",
                                    cells={"Email": "replacement", "Status": "Pending"})
    args = {"spreadsheet": "sheet", "worksheet": "tab", "row": "2", "cells": {"Status": "Changed"}}
    data = run_operations(raw, [("replacement-test-fixture", {}, replace),
        ("google_sheets_update_row", args, lambda world: google_sheets_update_row(world, **args))])
    if omit_public_id:
        data["task_evidence"]["initial"] = copy.deepcopy(raw)
        del data["task_evidence"]["initial"]["google_sheets"]["rows"][0]["id"]
    candidate = capture(data).rows[0]
    effects = capture_sheet_effects(data, SheetEffectSource(kind="update", spreadsheet_id="sheet", worksheet_id="tab"))
    effect = next(item for item in effects.effects if item.status == "qualified")
    assert effect.params_json is not None
    params = json.loads(effect.params_json)
    assert candidate.identity[-1] == params["row_id"] == 2
    assert candidate.native_record_id == "protected-original"
    assert candidate.native_record_id != params["native_record_id"]


def test_missing_rows_is_unavailable_but_declared_empty_is_closed():
    data = material([])
    assert left_lookup(capture(data), {"Email": "absent"}).status == "not_found"
    del data["task_evidence"]["initial"]["google_sheets"]["rows"]
    assert left_lookup(capture(data), {"Email": "absent"}).status == "unavailable"


@pytest.mark.parametrize("mutation", ["missing-service", "missing-tab", "duplicate-tab", "nested"])
def test_unsupported_or_ambiguous_collection_cannot_claim_empty(mutation):
    data = material()
    service = data["task_evidence"]["initial"]["google_sheets"]
    if mutation == "missing-service":
        del data["task_evidence"]["initial"]["google_sheets"]
    elif mutation == "missing-tab":
        service["worksheets"] = []
    elif mutation == "duplicate-tab":
        service["worksheets"].append(copy.deepcopy(service["worksheets"][0]))
    else:
        service["worksheets"][0]["rows"] = []
    assert not capture(data).closed and capture(data).status == "unavailable"


def test_duplicate_logical_keys_are_preserved_as_ambiguous():
    table = capture(material([row(1), row(2)]))
    found = left_lookup(table, {"Email": "a@example.com"})
    assert table.closed and found.status == "ambiguous" and len(found.matches) == 2


def test_duplicate_native_identity_is_unavailable_even_different_keys():
    table = capture(material([row(1), row(1, "b@example.com")]))
    assert table.status == "unavailable" and not table.closed and len(table.rows) == 2


def test_unrelated_missing_value_does_not_erase_known_match():
    second = row(2, "b@example.com")
    del second["cells"]["Status"]
    table = capture(material([row(1), second]))
    assert left_lookup(table, {"Email": "a@example.com"}).status == "matched"
    missing = left_lookup(table, {"Email": "b@example.com"})
    assert missing.status == "unavailable" and len(missing.matches) == 1


def test_unknown_key_blocks_closure_but_retains_definite_matches():
    second = row(2)
    del second["cells"]["Email"]
    table = capture(material([row(1), second]))
    found = left_lookup(table, {"Email": "a@example.com"})
    assert found.status == "unavailable" and len(found.matches) == len(found.unresolved_rows) == 1
    assert left_lookup(table, {"Email": "absent"}).status == "unavailable"


def test_malformed_unknown_scope_preserves_known_row_evidence():
    table = capture(material([row(), {"cells": {}}]))
    found = left_lookup(table, {"Email": "a@example.com"})
    assert table.status == "partial" and not table.closed
    assert found.status == "unavailable" and len(found.matches) == 1


def test_explicit_unrelated_scope_malformed_cells_does_not_poison_selected_table():
    unrelated = row(2)
    unrelated.update(worksheet_id="another", cells=None)
    assert (
        left_lookup(capture(material([row(), unrelated])), {"Email": "a@example.com"}).status
        == "matched"
    )


@pytest.mark.parametrize("query", ["A@example.com", " a@example.com", "a@example.com "])
def test_exact_keys_have_no_implicit_case_or_whitespace_normalization(query):
    assert left_lookup(capture(material()), {"Email": query}).status == "not_found"


def test_empty_cell_is_a_declared_literal_and_numeric_key_types_are_distinct():
    table = capture(material([row(1, ""), row("1", 1), row(2, 1.0)]))
    assert left_lookup(table, {"Email": ""}).status == "matched"
    assert left_lookup(table, {"Email": 1}).matches[0].identity[-1] == "1"
    assert left_lookup(table, {"Email": 1.0}).matches[0].identity[-1] == 2
    assert left_lookup(table, {"Email": True}).status == "unavailable"


@pytest.mark.parametrize(
    "field,value",
    [
        ("path", ()),
        ("path", (True,)),
        ("path", (-1,)),
        ("key_fields", ()),
        ("key_fields", ("Email", "Email")),
        ("required_fields", ("Status", "Status")),
    ],
)
def test_source_spec_rejects_ambiguous_or_untyped_selection(field, value):
    data = selector().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        TableSource.model_validate(data)


@pytest.mark.parametrize(
    "change", ["bool", "digest", "selector", "closure", "key", "missing", "scope", "path", "cells"]
)
def test_retained_table_receipt_rejects_inconsistent_projection(change):
    retained = capture(material()).model_dump(mode="json")
    if change == "bool":
        retained["closed"] = 1
    elif change == "digest":
        retained["source_digest"] = "x"
    elif change == "selector":
        retained["selector_digest"] = "0" * 64
    elif change == "closure":
        retained["closed"] = False
    elif change == "key":
        retained["rows"][0]["key_json"] = '[["str","invented"]]'
    elif change == "missing":
        retained["rows"][0]["missing_fields"] = ["Status"]
    elif change == "scope":
        retained["rows"][0]["identity"][1] = "another-tab"
    elif change == "path":
        retained["rows"][0]["source_path"] = []
    else:
        retained["rows"][0]["cells_json"] = "[]"
    with pytest.raises(ValidationError):
        TableEvidence.model_validate(retained)
