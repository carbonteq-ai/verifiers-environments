"""Terminal goals follow original objects rather than successful past writes."""

import copy
import json

import pytest
from test_manifest_sheet_effects import initial, spec, update
from test_notification_evidence import run_operations

from automationbench_v1.contracts import ContractSpec, RetainedRowCheck
from automationbench_v1.contracts.retained import evaluate_retained_rows
from automationbench_v1.contracts.sheet_effects import capture_sheet_retention
from automationbench_v1.contracts.tables import TableSource, capture_table


def table():
    return TableSource(path=("task_evidence", "initial", "google_sheets"),
        spreadsheet_id="sheet", worksheet_id="tab", key_fields=("Name",))


def check(**changes):
    raw = {"check_id": "balance", "signal_id": "balance.retained", "role": "goal",
        "operator": "sheets.retained_when@1", "population": "rows", "source": "writes",
        "required_when": {"op": "eq", "left": {"kind": "literal", "value": True},
                          "right": {"kind": "literal", "value": True}},
        "retained_when": {"op": "eq", "left": {"kind": "field", "path": ["retained", "Amount"], "domain": "string"},
                          "right": {"kind": "literal", "value": "$20"}}, **changes}
    return RetainedRowCheck.model_validate(raw)


def evaluate(data, selected=None):
    return evaluate_retained_rows(data, selected or check(), {"rows": capture_table(data, table())},
        capture_sheet_retention(data, spec()), retention_source=spec(), population_sources={"rows": table()})


@pytest.mark.parametrize("amounts,expected", [(["$20"], 1), (["$20", "$30"], 0),
    (["$20", "$30", "$20"], 1), ([], 0)])
def test_retained_outcome_reads_final_state_not_best_write(amounts, expected):
    result = evaluate(run_operations(initial(), [update(cells={"Amount": value}) for value in amounts]))
    assert result.findings[0].value == expected and result.scope_complete


def test_split_updates_and_combined_updates_have_the_same_goal():
    predicate = {"op": "all", "args": [check().retained_when.model_dump(mode="json"),
        {"op": "eq", "left": {"kind": "field", "path": ["retained", "Name"], "domain": "string"},
         "right": {"kind": "literal", "value": "Renamed"}}]}
    selected = check(retained_when=predicate)
    for calls in ([update(cells={"Amount": "$20", "Name": "Renamed"})],
                  [update(), update(cells={"Name": "Renamed"})]):
        assert evaluate(run_operations(initial(), calls), selected).findings[0].value == 1


@pytest.mark.parametrize("mutation,expected", [("delete", 0), ("replace", 0), ("move", 1)])
def test_native_identity_handles_absence_replacement_and_relocation(mutation, expected):
    def mutate(world):
        if mutation == "delete":
            world.google_sheets.rows.clear()
        elif mutation == "replace":
            world.google_sheets.rows[0].id = "replacement"
        else:
            world.google_sheets.rows[0].row_id = 3
        return {"success": True}
    data = run_operations(initial(), [update(), ("custom_mutation", {}, mutate)])
    result = evaluate(data)
    assert result.findings[0].value == expected and result.scope_complete


@pytest.mark.parametrize("gap", ["unfinished", "missing-field", "missing-final", "missing-original-id"])
def test_unknown_material_abstains(gap):
    data = run_operations(initial(), [update()])
    if gap == "unfinished":
        data["task_evidence"]["complete"] = False
    elif gap == "missing-field":
        del data["task_evidence"]["final"]["google_sheets"]["rows"][0]["cells"]["Amount"]
    elif gap == "missing-final":
        del data["task_evidence"]["final"]["google_sheets"]["rows"]
    else:
        del data["task_evidence"]["initial"]["google_sheets"]["rows"][0]["id"]
        data["state_write_receipts"] = []
    finding = evaluate(data).findings[0]
    assert finding.status == "abstained" and finding.value is None


def test_missing_action_ack_does_not_erase_known_terminal_outcome():
    data = run_operations(initial(), [update()])
    data["state_write_receipts"] = []
    assert evaluate(data).findings[0].value == 1


def test_original_id_can_bind_from_acknowledged_first_snapshot():
    public = initial()
    del public["google_sheets"]["rows"][0]["id"]
    data = run_operations(public, [update()])
    data["task_evidence"]["initial"] = public
    assert evaluate(data).findings[0].value == 1


def test_inapplicable_row_does_not_require_final_capture():
    data = run_operations(initial(), [])
    data["task_evidence"]["complete"] = False
    selected = check(required_when={"op": "eq", "left": {"kind": "literal", "value": True},
                                  "right": {"kind": "literal", "value": False}})
    assert evaluate(data, selected).findings[0].status == "inapplicable"


def test_instance_budget_abstains_without_partial_success():
    raw = initial()
    raw["google_sheets"]["rows"].append({**copy.deepcopy(raw["google_sheets"]["rows"][0]),
        "id": "second", "row_id": 3, "cells": {"Name": "Other", "Amount": "$20"}})
    result = evaluate(run_operations(raw, []), check(max_instances=1))
    assert not result.findings and not result.scope_complete


@pytest.mark.parametrize("target", ["table", "retention"])
def test_coherent_tampered_projection_rejects_before_outcome(target):
    data = run_operations(initial(), [update()])
    population, retention = capture_table(data, table()), capture_sheet_retention(data, spec())
    if target == "table":
        population = population.model_copy(update={"rows": (population.rows[0].model_copy(
            update={"native_record_id": "forged"}),)})
    else:
        retention = retention.model_copy(update={"rows": (retention.rows[0].model_copy(
            update={"cells_json": json.dumps({"Amount": "$999", "Name": "Item"}, sort_keys=True, separators=(",", ":"))}),)})
    with pytest.raises(ValueError, match="projection_mismatch"):
        evaluate_retained_rows(data, check(), {"rows": population}, retention,
            retention_source=spec(), population_sources={"rows": table()})


@pytest.mark.parametrize("root", ["retained", "effect", "future"])
def test_requirement_cannot_read_terminal_or_action_context(root):
    with pytest.raises(ValueError, match="context_unknown"):
        check(required_when={"op": "eq", "left": {"kind": "field", "path": [root, "Amount"], "domain": "string"},
                             "right": {"kind": "literal", "value": "$20"}})


def test_manifest_registers_outcome_check_but_rejects_occurrence_credit():
    raw = {"schema_version": 1, "manifest_id": "retained-fixture", "revision": "1", "public_request": "Update balances",
        "sources": {"rows": table().model_dump(mode="json"), "writes": spec().model_dump(mode="json")},
        "checks": [check().model_dump(mode="json")], "credit": []}
    admitted = ContractSpec.model_validate(raw)
    assert isinstance(admitted.checks[0], RetainedRowCheck)
    raw["credit"] = [{"check": "balance", "policy": "required_effect_once@1", "channel": "goal"}]
    with pytest.raises(ValueError, match="capability_mismatch"):
        ContractSpec.model_validate(raw)


@pytest.mark.parametrize("mutation", ["future_population", "different_sheet", "different_tab", "non_sheet"])
def test_manifest_rejects_unreviewed_retained_source_context(mutation):
    raw = {"schema_version": 1, "manifest_id": "retained-fixture", "revision": "1", "public_request": "Update balances",
        "sources": {"rows": table().model_dump(mode="json"), "writes": spec().model_dump(mode="json")},
        "checks": [check().model_dump(mode="json")], "credit": []}
    if mutation == "future_population":
        raw["sources"]["rows"]["path"][1] = "final"
    elif mutation == "non_sheet":
        raw["sources"]["writes"] = {"adapter": "gmail.messages@1", "kind": "send"}
    else:
        raw["sources"]["writes"]["spreadsheet_id" if mutation == "different_sheet" else "worksheet_id"] = "other"
    with pytest.raises(ValueError, match="retained_"):
        ContractSpec.model_validate(raw)
