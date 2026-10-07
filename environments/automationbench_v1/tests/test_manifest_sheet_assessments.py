"""Shared manifest/native bridge for real Sheets writes in labeled test envelopes."""

import asyncio
import copy
import json
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_manifest_guards import comparison, field, literal
from test_manifest_sheet_effects import append, initial, spec, update
from test_notification_evidence import run_operations

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import SheetEffectSource, TableSource, load_contract
from automationbench_v1.contracts.sheet_effects import capture_sheet_retention
from automationbench_v1.manifest_guard_assessments import capture_guard_inputs, restore_guard_inputs
from automationbench_v1.manifest_obligation_assessments import OBLIGATION_OUTPUT


def declaration(kind="update", blocked=False):
    match = {"op": "all", "args": [
        comparison("eq", field("effect", "spreadsheet_id", domain="string"), literal("sheet")),
        comparison("eq", field("effect", "worksheet_id", domain="string"), literal("tab")),
        comparison("eq", field("effect", "after_cells", "Name", domain="string"), field("request", "Name", domain="string")),
    ]}
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "manufactured-sheet-bridge", "revision": "1",
        "public_request": "Record one acknowledged worksheet action for the named row; prohibited rows must not be written.",
        "sources": {"rows": TableSource(path=("task_evidence", "initial", "google_sheets"),
            spreadsheet_id="sheet", worksheet_id="tab", key_fields=("Name",)).model_dump(mode="json"),
            "writes": SheetEffectSource.model_validate({"kind": kind, "spreadsheet_id": "sheet", "worksheet_id": "tab"}).model_dump(mode="json")},
        "checks": [{"check_id": "sheet-action", "signal_id": "sheet.observation", "role": "harm" if blocked else "goal",
            "operator": "effects.prohibited_when@1" if blocked else "effects.required_when@1",
            "population": "rows", "source": "writes", "effect_match": match,
            **({"prohibited_when": comparison("eq", field("request", "Name", domain="string"), literal("Item"))}
               if blocked else {"semantics": "new_occurrence",
                   "required_when": comparison("eq", field("request", "Name", domain="string"), literal("Item"))})}],
        "credit": [{"check": "sheet-action", "policy": "per_effect_negative@1" if blocked else "required_effect_once@1",
                    "channel": "sheet-harm" if blocked else "sheet-progress"}]}))


def run(monkeypatch, *, kind="update", blocked=False, operations=None, missing_ack=None):
    contract = declaration(kind, blocked)
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    material = run_operations(initial(), operations or [update()])
    task, episode, trace = native_fixture(material, missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    return task, episode, trace, material


def outcome(trace):
    return next(record for record in terminal_records(trace) if record.signal.signal_id == "sheet.observation")


def test_native_sheet_update_publishes_goal_and_exact_execution_progress(monkeypatch):
    _, _, trace, _ = run(monkeypatch)
    assert outcome(trace).value == 1 and outcome(trace).subject.kind == "trace"
    parts = penalties(trace)
    assert len(parts) == 1 and parts[0].value == 1
    assert parts[0].recipient.execution.invocation_id == "execution-0"


@pytest.mark.parametrize("blocked", [False, True])
def test_native_candidate_identity_matches_renamed_rows_without_cell_identity_guess(monkeypatch, blocked):
    raw = declaration(blocked=blocked).model_dump(mode="json")
    raw["checks"][0]["effect_match"]["args"][2] = comparison(
        "eq", field("effect", "row_id", domain="integer"), field("candidate", "identity", 3, domain="integer"))
    contract = load_contract(canonical_json(raw))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    material = run_operations(initial(), [update(cells={"Name": "Renamed", "Amount": "$20"})])
    task, _, trace = native_fixture(material)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    assert outcome(trace).value == 1
    assert len(penalties(trace)) == 1
    assert penalties(trace)[0].value == (-1 if blocked else 1)


@pytest.mark.parametrize("blocked", [False, True])
def test_candidate_namespace_cannot_be_shadowed_by_lookup_alias(blocked):
    raw = declaration(blocked=blocked).model_dump(mode="json")
    raw["checks"][0]["lookups"] = [{"source": "rows", "alias": "candidate",
                                    "keys": {"Name": field("request", "Name", domain="string")}}]
    with pytest.raises(ValueError, match="lookup_alias_conflict"):
        load_contract(canonical_json(raw))


def test_native_successful_noop_remains_factual_occurrence_without_useful_credit(monkeypatch):
    _, _, trace, _ = run(monkeypatch, operations=[update(cells={"Amount": "$10"})])
    assert outcome(trace).value == 1 and not penalties(trace)
    outputs = [json.loads(receipt.payload_json) for batch in trace.assessment_batches
               for receipt in batch.run.execution_evidence if receipt.kind == OBLIGATION_OUTPUT]
    assert any(output["kind"] == "finding" and output["witnesses"] for output in outputs)


def test_earlier_noop_does_not_hide_later_qualified_state_progress(monkeypatch):
    _, _, trace, _ = run(monkeypatch, operations=[update(cells={"Amount": "$10"}), update()])
    assert outcome(trace).value == 1 and len(penalties(trace)) == 1
    assert penalties(trace)[0].recipient.execution.invocation_id == "execution-1"


def test_native_new_append_can_receive_one_credit_for_created_entity(monkeypatch):
    _, _, trace, _ = run(monkeypatch, kind="append", operations=[append(cells={"Name": "Item", "Amount": "$30"})])
    assert outcome(trace).value == 1 and len(penalties(trace)) == 1


def test_native_sheet_guard_harm_persists_after_repair(monkeypatch):
    _, _, trace, material = run(monkeypatch, blocked=True,
        operations=[update(), update(cells={"Amount": "$10"})])
    assert outcome(trace).value == 1
    parts = penalties(trace)
    assert len(parts) == 2 and all(part.value == -1 for part in parts)
    retained = capture_sheet_retention(material, spec())
    assert json.loads(retained.rows[0].cells_json)["Amount"] == "$10"


def test_native_own_missing_ack_abstains_and_has_no_credit(monkeypatch):
    _, _, trace, _ = run(monkeypatch, missing_ack=0)
    assert outcome(trace).value is None and not penalties(trace)


def test_native_sheet_reload_and_rescore_do_not_duplicate_consumption(monkeypatch):
    task, episode, trace, _ = run(monkeypatch)
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    retained = cast(Any, restored.traces[0])
    retained.state = trace.state
    assert retained.assessment_batches == trace.assessment_batches
    asyncio.run(task.score(retained))
    assert not retained.assessment_errors and not retained.credit_errors
    assert len(penalties(retained)) == 1


def test_manifest_sheet_source_admission_is_schema_data_without_task_dispatch():
    contract = declaration()
    assert isinstance(contract.sources["writes"], SheetEffectSource)
    modified = contract.model_dump(mode="json")
    modified["sources"]["writes"]["adapter"] = "google_sheets.row_writes@999"
    with pytest.raises(ValueError):
        load_contract(canonical_json(modified))


def test_obligation_only_manifest_does_not_duplicate_guard_input_material():
    material = run_operations(initial(), [update()])
    assert capture_guard_inputs(material, declaration()) == {"table_evidence_json": "{}", "effect_evidence_json": "{}"}


def test_mixed_guard_and_obligation_retain_required_sources_independently(monkeypatch):
    declared = declaration().model_dump(mode="json")
    harm = declaration(blocked=True).model_dump(mode="json")["checks"][0]
    harm["check_id"] = "separate-harm"
    harm["signal_id"] = "sheet.harm"
    declared["checks"].append(harm)
    declared["credit"].append({"check": "separate-harm", "policy": "per_effect_negative@1", "channel": "sheet-harm"})
    contract = load_contract(canonical_json(declared))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    material = run_operations(initial(), [update()])
    assert set(json.loads(capture_guard_inputs(material, contract)["table_evidence_json"])) == {"rows"}
    task, _, trace = native_fixture(material)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    assert outcome(trace).value == 1
    assert next(record for record in terminal_records(trace) if record.signal.signal_id == "sheet.harm").value == 1
    assert {part.value for part in penalties(trace)} == {1, -1}


@pytest.mark.parametrize("kind", ["effect", "table"])
def test_coherent_cached_guard_labels_cannot_replace_raw_evidence(kind):
    contract = declaration(blocked=True)
    source = run_operations(initial(), [update()])
    material = {"source": source, **capture_guard_inputs(source, contract)}
    if kind == "effect":
        value = json.loads(material["effect_evidence_json"])
        params = json.loads(value["writes"]["effects"][0]["params_json"])
        params["after_cells"]["Amount"] = "$999"
        value["writes"]["effects"][0]["params_json"] = canonical_json(params)
        material["effect_evidence_json"] = canonical_json(value)
    else:
        value = json.loads(material["table_evidence_json"])
        row = value["rows"]["rows"][0]
        cells = json.loads(row["cells_json"])
        cells["Name"] = "Invented"
        row["cells_json"] = canonical_json(cells)
        row["key_json"] = canonical_json([["str", "Invented"]])
        material["table_evidence_json"] = canonical_json(value)
    with pytest.raises(ValueError, match="raw_source_membership"):
        restore_guard_inputs(material, contract)
