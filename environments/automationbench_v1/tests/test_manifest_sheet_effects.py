"""Native Sheets writes, adversarial capture and SHA-bound recorded mutations."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.gmail.message import gmail_find_email, gmail_send_email
from automationbench.tools.zapier.google_drive.actions import google_drive_find_multiple_files
from automationbench.tools.zapier.google_sheets.row import (
    google_sheets_add_row,
    google_sheets_append_row,
    google_sheets_get_many_rows,
    google_sheets_update_row,
)
from automationbench.tools.zapier.google_sheets.spreadsheet import (
    google_sheets_get_spreadsheet_by_id,
)
from automationbench.tools.zapier.slack.search import slack_find_message
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.sheet_effects import (
    SheetEffectSource,
    capture_sheet_effects,
    capture_sheet_retention,
    validate_sheet_retention,
)


def initial():
    return {"google_sheets": {
        "spreadsheets": [{"id": "sheet", "title": "Budget"}],
        "worksheets": [{"id": "tab", "spreadsheet_id": "sheet", "title": "Schedule",
                        "headers": ["Name", "Amount"]}],
        "rows": [{"id": "native-row", "row_id": 2, "spreadsheet_id": "sheet",
                  "worksheet_id": "tab", "cells": {"Name": "Item", "Amount": "$10"}}]}}


def spec(kind="update"):
    return SheetEffectSource.model_validate({"kind": kind, "spreadsheet_id": "sheet", "worksheet_id": "tab"})


def update(**changes):
    args = {"spreadsheet": "sheet", "worksheet": "tab", "row": "2", "cells": {"Amount": "$20"}, **changes}
    return zapier("google_sheets_update_row", args, lambda world: google_sheets_update_row(world, **args))


def append(**changes):
    args = {"spreadsheet": "sheet", "worksheet": "tab", "cells": {"Name": "New", "Amount": "$30"}, **changes}
    return zapier("google_sheets_add_row", args, lambda world: google_sheets_add_row(world, **args))


def append_alias(**changes):
    args = {"spreadsheet_id": "sheet", "worksheet_id": "tab", **changes}
    return zapier("google_sheets_append_row", args, lambda world: google_sheets_append_row(world, **args))


@pytest.mark.parametrize("selected", ["cells", "row", "row_data", "values", "fields"])
def test_real_append_alias_uses_its_exact_conflicting_argument_precedence(selected):
    order = ["cells", "row", "row_data", "values", "fields"]
    args = {name: {} if order.index(name) < order.index(selected) else {"Name": name, "Amount": "$30"}
            for name in order}
    data = run_operations(initial(), [append_alias(**args)])
    evidence = capture_sheet_effects(data, spec("append"))
    assert evidence.complete and len(evidence.effects) == 1
    params = payload(evidence.effects[0])
    assert params["after_cells"]["Name"] == selected
    assert params["native_record_id"] == data["task_evidence"]["final"]["google_sheets"]["rows"][-1]["id"]
    assert params["native_record_id"] != "native-row"
    assert params["before_cells"] is None and params["requested_fields"] == ["Amount", "Name"]


def test_append_alias_and_add_row_keep_distinct_cell_precedence():
    args = {"cells": {}, "row": {"Name": "from-row"}, "values": {"Name": "from-values"}}
    assert payload(qualified(run_operations(initial(), [append_alias(**args)]), "append")[0])["after_cells"]["Name"] == "from-row"
    assert payload(qualified(run_operations(initial(), [append(**args)]), "append")[0])["after_cells"]["Name"] == "from-values"


@pytest.mark.parametrize("fault", ["missing_ack", "wrong_revision", "wrong_return", "reused_native_id"])
def test_append_alias_needs_ack_response_and_new_native_identity(fault):
    def execute(world):
        result = google_sheets_append_row(world, spreadsheet_id="sheet", worksheet_id="tab", row={"Name": "Alias"})
        if fault == "reused_native_id":
            world.google_sheets.rows[-1].id = "native-row"
        return result
    data = run_operations(initial(), [zapier("google_sheets_append_row",
        {"spreadsheet_id": "sheet", "worksheet_id": "tab", "row": {"Name": "Alias"}}, execute)])
    if fault == "missing_ack":
        data["state_write_receipts"] = []
    elif fault == "wrong_revision":
        data["state_write_receipts"][0]["applied_revision"] = 99
    elif fault == "wrong_return":
        alter_return(data, lambda result: result["row"]["cells"].update({"Name": "Wrong"}))
    assert not qualified(data, "append")


@pytest.mark.parametrize("batch,task_name,sha,sheet,tab,count", [
    (7, "support.zoho_account_health", "705789a97d7c86b384f2b1db0c77d419b11cd9d0d8a614d85353e1c3923b4153", "ss_health", "ws_dashboard", 5),
    (8, "marketing.content_repurpose", "e15794723da9c2fc771e288e4a533d383b8efdcc85e299267e412e3989ff8489", "ss_queue", "ws_tasks", 3),
])
def test_actual_sha_bound_legacy_append_calls_are_qualified_occurrences(batch, task_name, sha, sheet, tab, count):
    review = Path("/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate") / f"manifest-authoring-batch-{batch:02}-review.json"
    if not review.exists():
        pytest.skip("local recorded development source index unavailable")
    record = next(item for item in json.loads(review.read_text())["tasks"] if item["task_name"] == task_name)
    path = Path(record["qualification_source"]["episode_path"])
    if not path.exists():
        pytest.skip("local recorded development episode unavailable")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == sha == record["qualification_source"]["episode_sha256"]
    episode = json.loads(raw)
    trace = episode["traces"][0]
    source = {"task_evidence": {"initial": episode["task"]["data"]["initial_state"],
        "final": trace["info"]["automationbench"]["end_state"], "complete": trace["is_completed"]},
        "tool_execution_events": trace["tool_execution_events"], "state_write_receipts": trace["state_write_receipts"]}
    before = copy.deepcopy(source)
    result = capture_sheet_effects(source, SheetEffectSource(kind="append", spreadsheet_id=sheet, worksheet_id=tab))
    facts = [fact for fact in result.effects if fact.status == "qualified"]
    assert len(facts) == count and len({payload(fact)["native_record_id"] for fact in facts}) == count
    # Other calls are Sheets reads or services whose static footprint excludes
    # Sheets (Zoho Desk, Salesforce, Slack, Drive find), so the inventory closes.
    assert result.complete
    assert source == before and path.read_bytes() == raw


def payload(fact):
    assert fact.params_json is not None
    return json.loads(fact.params_json)


def qualified(data, kind="update"):
    return [fact for fact in capture_sheet_effects(data, spec(kind)).effects if fact.status == "qualified"]


def unrelated(name):
    functions = {
        "gmail_find_email": (gmail_find_email, {"query": "test"}),
        "gmail_send_email": (gmail_send_email, {"to": "person@example.com", "subject": "Hello", "body": "Notice"}),
        "google_drive_find_multiple_files": (google_drive_find_multiple_files, {"title": "Budget"}),
        "slack_find_message": (slack_find_message, {"query": "forecast"}),
        "google_sheets_get_many_rows": (google_sheets_get_many_rows, {"spreadsheet": "sheet", "worksheet": "tab"}),
        "google_sheets_get_spreadsheet_by_id": (google_sheets_get_spreadsheet_by_id, {"spreadsheet": "missing"}),
    }
    function, arguments = functions[name]
    return zapier(name, arguments, lambda world: function(world, **arguments))


@pytest.mark.parametrize("name", ["gmail_find_email", "gmail_send_email",
    "google_drive_find_multiple_files", "slack_find_message", "google_sheets_get_many_rows",
    "google_sheets_get_spreadsheet_by_id"])
def test_audited_native_read_discovery_and_foreign_operations_close_selected_sheet_scope(name):
    data = run_operations(initial(), [unrelated(name), update()])
    evidence = capture_sheet_effects(data, spec())
    assert evidence.complete and len(evidence.effects) == 1
    assert evidence.effects[0].invocation_id == "execution-1"


@pytest.mark.parametrize("name", ["gmail_find_email", "gmail_send_email", "google_sheets_get_many_rows"])
def test_unrelated_native_operation_missing_ack_keeps_scope_open_and_known_write(name):
    data = run_operations(initial(), [unrelated(name), update()])
    data["state_write_receipts"] = data["state_write_receipts"][1:]
    evidence = capture_sheet_effects(data, spec())
    assert not evidence.complete
    assert any(fact.status == "qualified" and fact.invocation_id == "execution-1" for fact in evidence.effects)


@pytest.mark.parametrize("name", ["custom_read_api", "gmail_custom_api", "google_sheets_get_row"])
def test_unknown_operations_do_not_close_scope_from_unchanged_endpoints_or_name_prefix(name):
    def temporary_mutation(world):
        old = dict(world.google_sheets.rows[0].cells)
        world.google_sheets.rows[0].cells["Amount"] = "$999"
        world.google_sheets.rows[0].cells = old
        return {"success": True}
    data = run_operations(initial(), [(name, {}, temporary_mutation), update()])
    evidence = capture_sheet_effects(data, spec())
    assert not evidence.complete
    assert evidence.effects[0].reason == "sheet_operation_scope_unsupported"
    assert evidence.effects[1].status == "qualified"


def test_known_handler_name_with_changed_selected_objects_cannot_close_scope():
    def changed(world):
        world.google_sheets.worksheets[0].title = "Changed"
        return {"success": True}
    data = run_operations(initial(), [("gmail_send_email", {}, changed), update()])
    evidence = capture_sheet_effects(data, spec())
    assert not evidence.complete and evidence.effects[0].status == "unavailable"


@pytest.mark.parametrize("changed", ["cells", "spreadsheet", "worksheet", "native_id"])
def test_public_initial_omitted_native_defaults_reconciles_only_against_qualified_original_world(changed):
    public = initial()
    del public["google_sheets"]["rows"][0]["id"]
    data = run_operations(public, [unrelated("gmail_find_email"), update()])
    data["task_evidence"]["initial"] = copy.deepcopy(public)
    assert capture_sheet_effects(data, spec()).complete
    declared = data["task_evidence"]["initial"]["google_sheets"]
    if changed == "cells":
        declared["rows"][0]["cells"]["Amount"] = "$999"
    elif changed == "spreadsheet":
        declared["spreadsheets"][0]["title"] = "Different budget"
    elif changed == "worksheet":
        declared["worksheets"][0]["title"] = "Different schedule"
    else:
        declared["rows"][0]["id"] = "replacement"
    evidence = capture_sheet_effects(data, spec())
    assert not evidence.complete
    assert any(fact.status == "qualified" for fact in evidence.effects)


@pytest.mark.parametrize("kind", ["append", "update"])
def test_native_write_binds_returned_scoped_row_and_exact_before_after(kind):
    data = run_operations(initial(), [append() if kind == "append" else update()])
    evidence = capture_sheet_effects(data, spec(kind))
    assert evidence.complete and len(evidence.effects) == 1
    fact = evidence.effects[0]
    params = payload(fact)
    assert fact.kind == kind and (fact.expected_revision, fact.applied_revision) == (0, 1)
    assert params["native_record_id"] and params["spreadsheet_id"] == "sheet" and params["worksheet_id"] == "tab"
    assert params["after_cells"]["Amount"] == ("$30" if kind == "append" else "$20")
    assert sorted(params["changed_fields"]) == (["Amount", "Name"] if kind == "append" else ["Amount"])
    assert params["before_cells"] is None if kind == "append" else params["before_cells"]["Amount"] == "$10"
    assert capture_sheet_retention(data, spec(kind)).closed


def test_title_and_installed_cell_alias_normalization_are_bound_to_public_headers():
    data = run_operations(initial(), [update(spreadsheet="Budget", worksheet="Schedule", row="#2", cells={"amount": "$20"})])
    facts = qualified(data)
    assert len(facts) == 1 and payload(facts[0])["requested_fields"] == ["Amount"]


@pytest.mark.parametrize("arguments", [{"spreadsheet": None}, {"worksheet": None}])
def test_native_omitted_target_qualifies_only_with_unique_pre_state_resolution(arguments):
    assert len(qualified(run_operations(initial(), [update(**arguments)]))) == 1


@pytest.mark.parametrize("argument", ["spreadsheet", "worksheet"])
def test_ambiguous_omitted_target_cannot_qualify(argument):
    raw = initial()
    tab = copy.deepcopy(raw["google_sheets"]["worksheets"][0])
    if argument == "spreadsheet":
        tab["spreadsheet_id"] = "another-sheet"
        raw["google_sheets"]["spreadsheets"].append({"id": "another-sheet", "title": "Another"})
    else:
        tab["id"] = "another-tab"
    raw["google_sheets"]["worksheets"].append(tab)
    assert not qualified(run_operations(raw, [update(**{argument: None})]))


def test_positional_cells_use_known_native_headers():
    data = run_operations(initial(), [update(cells=["Renamed", "$20"])])
    assert payload(qualified(data)[0])["after_cells"] == {"Name": "Renamed", "Amount": "$20"}


def test_successful_noop_is_occurrence_without_cell_progress():
    data = run_operations(initial(), [update(cells={"Amount": "$10"})])
    fact = qualified(data)[0]
    assert payload(fact)["changed_fields"] == []


def test_repeated_same_row_writes_keep_execution_identity_and_repair_terminal_state():
    data = run_operations(initial(), [update(), update(cells={"Amount": "$10"})])
    evidence = capture_sheet_effects(data, spec())
    assert evidence.complete and len(evidence.effects) == 2
    assert evidence.effects[0].effect_id == evidence.effects[1].effect_id
    assert {fact.invocation_id for fact in evidence.effects} == {"execution-0", "execution-1"}
    assert payload(evidence.effects[0])["after_cells"]["Amount"] == "$20"
    retained = capture_sheet_retention(data, spec())
    assert json.loads(retained.rows[0].cells_json)["Amount"] == "$10"


@pytest.mark.parametrize("gap", ["own-ack", "later-ack", "initial-collection", "terminal-collection", "incomplete"])
def test_unknown_scope_does_not_erase_independent_acknowledged_write(gap):
    data = run_operations(initial(), [update(), update(cells={"Amount": "$30"})])
    if gap in {"own-ack", "later-ack"}:
        data["state_write_receipts"] = [row for row in data["state_write_receipts"]
                                      if row["write_id"] != ("execution-0" if gap == "own-ack" else "execution-1")]
    elif gap == "initial-collection":
        del data["task_evidence"]["initial"]["google_sheets"]["rows"]
    elif gap == "terminal-collection":
        del data["task_evidence"]["final"]["google_sheets"]["rows"]
    else:
        data["task_evidence"]["complete"] = False
    evidence = capture_sheet_effects(data, spec())
    assert not evidence.complete and len([fact for fact in evidence.effects if fact.status == "qualified"]) >= 1
    if gap in {"terminal-collection", "incomplete"}:
        assert not capture_sheet_retention(data, spec()).closed


@pytest.mark.parametrize("row", ["missing", "99", True])
def test_failed_wrong_target_never_qualifies(row):
    assert not qualified(run_operations(initial(), [update(row=row)]))


def alter_return(data, transform):
    event = data["tool_execution_events"][0]
    receipt = json.loads(event["receipt_json"])
    envelope = json.loads(receipt["evidence_json"][0])
    result = json.loads(json.loads(envelope["action"]["result_json"]))
    transform(result)
    envelope["action"]["result_json"] = canonical_json(canonical_json(result))
    receipt["evidence_json"] = [canonical_json(envelope)]
    event["receipt_json"] = canonical_json(receipt)


@pytest.mark.parametrize("change", ["row", "cells", "success"])
def test_acknowledgement_does_not_override_wrong_returned_identity_or_cells(change):
    data = run_operations(initial(), [update()])
    def transform(result):
        if change == "row":
            result["row"]["row_id"] = "2"
        elif change == "cells":
            result["row"]["cells"]["Amount"] = "$999"
        else:
            result["success"] = 1
    alter_return(data, transform)
    assert not qualified(data)


def test_other_native_sheet_write_kind_is_not_the_selected_occurrence():
    assert not capture_sheet_effects(run_operations(initial(), [append()]), spec()).effects
    assert not capture_sheet_effects(run_operations(initial(), [update()]), spec("append")).effects


def test_foreign_mutation_preserves_known_write_but_does_not_close_inventory():
    def deletion(world):
        world.google_sheets.rows = []
        return {"success": True}
    data = run_operations(initial(), [update(), zapier("custom_delete_rows", {}, deletion)])
    evidence = capture_sheet_effects(data, spec())
    assert not evidence.complete and evidence.effects[0].status == "qualified"
    assert capture_sheet_retention(data, spec()).closed and not capture_sheet_retention(data, spec()).rows


def test_missing_retained_rows_are_unavailable_not_empty():
    data = run_operations(initial(), [update()])
    del data["task_evidence"]["final"]["google_sheets"]["rows"]
    retained = capture_sheet_retention(data, spec())
    assert not retained.closed and retained.status == "unavailable"


@pytest.mark.parametrize("defect", ["duplicate-row-id", "duplicate-native-id", "bool-row-id", "mixed-nested"])
def test_retained_population_cannot_close_malformed_native_identities(defect):
    data = run_operations(initial(), [update()])
    service = data["task_evidence"]["final"]["google_sheets"]
    if defect == "mixed-nested":
        service["worksheets"][0]["rows"] = []
    elif defect == "bool-row-id":
        service["rows"][0]["row_id"] = True
    else:
        row = copy.deepcopy(service["rows"][0])
        if defect == "duplicate-row-id":
            row["id"] = "other-internal-id"
        else:
            row["row_id"] = 99
        service["rows"].append(row)
    assert not capture_sheet_retention(data, spec()).closed


def test_retained_receipt_reload_and_model_copy_are_raw_source_bound():
    data = run_operations(initial(), [update()])
    retained = capture_sheet_retention(data, spec())
    validate_sheet_retention(type(retained).model_validate_json(retained.model_dump_json()), data, spec())
    with pytest.raises(ValidationError):
        validate_sheet_retention(retained.model_copy(update={"closed": 1}), data, spec())
    changed = retained.rows[0].model_copy(update={"cells_json": canonical_json({"Amount": "$999"})})
    with pytest.raises(ValueError):
        validate_sheet_retention(retained.model_copy(update={"rows": (changed,)}), data, spec())


@pytest.mark.parametrize("defect", ["duplicate-native-id", "foreign-scope", "bool-native-id", "bool-row-id"])
def test_retained_nested_copied_identity_is_readmitted_before_trust(defect):
    data = run_operations(initial(), [update()])
    retained = capture_sheet_retention(data, spec())
    original = retained.rows[0]
    if defect == "duplicate-native-id":
        other = original.model_copy(update={"identity": ("sheet", "tab", "int", 99)})
        rows = (original, other)
    elif defect == "foreign-scope":
        other = original.model_copy(update={"identity": ("sheet", "other-tab", "int", 99),
                                            "native_record_id": "other-native-id"})
        rows = (original, other)
    elif defect == "bool-native-id":
        rows = (original.model_copy(update={"native_record_id": True}),)
    else:
        rows = (original.model_copy(update={"identity": ("sheet", "tab", "int", True)}),)
    with pytest.raises(ValidationError):
        validate_sheet_retention(retained.model_copy(update={"rows": rows}), data, spec())


def test_retained_receipt_cannot_replace_source_with_coherent_foreign_row():
    data = run_operations(initial(), [update()])
    retained = capture_sheet_retention(data, spec())
    changed = retained.rows[0].model_copy(update={"native_record_id": "replacement-native-id"})
    with pytest.raises(ValueError, match="source_or_projection_mismatch"):
        validate_sheet_retention(retained.model_copy(update={"rows": (changed,)}), data, spec())


def test_actual_sha_bound_first_batch_luna_schedule_mutations():
    index = Path("/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate/cross-category-selection.json")
    if not index.exists():
        pytest.skip("selected development sources unavailable")
    selected = next(item for item in json.loads(index.read_text())["tasks"] if item["task_name"] == "finance.prepaid_amortization")
    raw = Path(selected["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == selected["source_episode_sha256"]
    episode = json.loads(raw)
    trace = episode["traces"][0]
    material = {"task_evidence": {"initial": episode["task"]["data"]["initial_state"],
        "final": trace["info"]["automationbench"]["end_state"], "complete": trace["is_completed"]},
        "tool_execution_events": trace["tool_execution_events"], "state_write_receipts": trace["state_write_receipts"]}
    before = copy.deepcopy(material)
    source = SheetEffectSource(kind="update", spreadsheet_id="ss_prepaids", worksheet_id="ws_prepaid_items")
    evidence = capture_sheet_effects(material, source)
    assert evidence.complete
    assert any(fact.status == "qualified" and payload(fact)["changed_fields"] for fact in evidence.effects)
    assert material == before
    assert capture_sheet_retention(material, source).closed
    # Actual native discovery capture avoids the optional Agents SDK required
    # only by fresh registry schema rendering in this test environment.
    receipt = json.loads(material["tool_execution_events"][1]["receipt_json"])
    assert json.loads(receipt["evidence_json"][0])["action"]["tool_name"] == "search_tools"
    material["state_write_receipts"] = [write for write in material["state_write_receipts"]
        if write["write_id"] != receipt["invocation_id"]]
    unavailable = capture_sheet_effects(material, source)
    assert not unavailable.complete
    assert any(fact.status == "qualified" for fact in unavailable.effects)
