"""Completion allocation uses qualified transitions and preserved final goals."""

import copy
import json
from dataclasses import replace

import pytest
from test_manifest_retained import check, table
from test_manifest_sheet_effects import initial, spec, unrelated, update
from test_notification_evidence import run_operations

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import ContractSpec, CreditSpec
from automationbench_v1.contracts.retained_credit import (
    CompletionEvaluation,
    evaluate_retained_completion,
)
from automationbench_v1.contracts.sheet_effects import (
    capture_sheet_effects,
    capture_sheet_retention,
)
from automationbench_v1.contracts.tables import capture_table


def rule(**changes):
    return CreditSpec.model_validate({"check": "balance", "policy": "retained_completion_once@1",
        "channel": "completion", "goal_fields": ["Amount"], **changes})


def evaluate(data, selected=None, policy=None, effects=None):
    return evaluate_retained_completion(data, selected or check(), policy or rule(),
        {"rows": capture_table(data, table())}, capture_sheet_retention(data, spec()),
        effects or capture_sheet_effects(data, spec()),
        population_sources={"rows": table()}, retention_source=spec())


def chosen(result: CompletionEvaluation):
    selection = result.findings[0].selection
    assert selection is not None
    return selection


@pytest.mark.parametrize("amounts,selected", [(["$20"], "execution-0"),
    (["$20", "$30"], None), (["$20", "$30", "$20"], "execution-2"),
    (["$30"], None), ([], None)])
def test_latest_observed_completion_requires_final_goal(amounts, selected):
    result = evaluate(run_operations(initial(), [update(cells={"Amount": amount}) for amount in amounts]))
    found = result.findings[0].selection
    assert (found.occurrence if found else None) == selected
    if found:
        assert result.findings[0].initially_satisfied is False
        assert found.native_record_id == "native-row" and found.value == 1


def test_initial_success_break_restore_cannot_mint_credit():
    raw = initial()
    raw["google_sheets"]["rows"][0]["cells"]["Amount"] = "$20"
    result = evaluate(run_operations(raw, [update(cells={"Amount": "$30"}), update()]))
    assert result.outcome.findings[0].value == 1
    assert result.findings[0].selection is None
    assert result.findings[0].reason == "completion_initially_satisfied"


@pytest.mark.parametrize("tail", [{"Amount": "$20"}, {"Name": "Renamed"}])
def test_noop_or_unrelated_field_update_cannot_steal_completion(tail):
    result = evaluate(run_operations(initial(), [update(), update(cells=tail)]))
    assert chosen(result).occurrence == "execution-0"


def test_split_updates_credit_the_final_required_field_not_all_writes():
    predicate = {"op": "all", "args": [check().retained_when.model_dump(mode="json"),
        {"op": "eq", "left": {"kind": "field", "path": ["retained", "Name"], "domain": "string"},
         "right": {"kind": "literal", "value": "Renamed"}}]}
    selected = check(retained_when=predicate)
    policy = rule(goal_fields=["Amount", "Name"])
    for calls, expected in (([update(cells={"Amount": "$20", "Name": "Renamed"})], "execution-0"),
                           ([update(), update(cells={"Name": "Renamed"})], "execution-1")):
        assert chosen(evaluate(run_operations(initial(), calls), selected, policy)).occurrence == expected


def money(path=None, literal=None):
    expression: dict[str, object] = {"kind": "input", "format": "usd_string"}
    if path is not None:
        expression["path"] = path
    else:
        assert literal is not None
        expression["literal"] = literal
    return {"kind": "derived", "expression": expression}


def numeric_check():
    return check(retained_when={"op": "eq", "left": money(path=["retained", "Amount"]),
                                "right": money(literal="$20")})


def test_numeric_formatting_after_completion_does_not_steal_credit():
    result = evaluate(run_operations(initial(), [update(), update(cells={"Amount": "$20.00"})]), numeric_check())
    assert chosen(result).occurrence == "execution-0"


def test_numeric_equivalent_initial_goal_has_no_credit():
    raw = initial()
    raw["google_sheets"]["rows"][0]["cells"]["Amount"] = "$20.00"
    result = evaluate(run_operations(raw, [update()]), numeric_check())
    assert result.findings[0].initially_satisfied is True
    assert result.findings[0].selection is None


@pytest.mark.parametrize("gap", ["ack", "initial-field", "unfinished", "terminal-field", "identity"])
def test_unavailable_evidence_never_invents_completion(gap):
    raw = initial()
    if gap == "initial-field":
        del raw["google_sheets"]["rows"][0]["cells"]["Amount"]
    data = run_operations(raw, [update()])
    if gap == "ack":
        data["state_write_receipts"] = []
    elif gap == "unfinished":
        data["task_evidence"]["complete"] = False
    elif gap == "terminal-field":
        del data["task_evidence"]["final"]["google_sheets"]["rows"][0]["cells"]["Amount"]
    elif gap == "identity":
        del data["task_evidence"]["initial"]["google_sheets"]["rows"][0]["id"]
        data["state_write_receipts"] = []
    result = evaluate(data)
    assert result.findings[0].selection is None
    assert result.findings[0].status == "unavailable"


def test_missing_unrelated_ack_preserves_known_completion_and_unknown_action_scope():
    data = run_operations(initial(), [unrelated("gmail_find_email"), update()])
    data["state_write_receipts"] = data["state_write_receipts"][1:]
    result = evaluate(data)
    assert chosen(result).occurrence == "execution-1"
    assert result.action_scope_complete is False


@pytest.mark.parametrize("mutation,eligible", [("move", True), ("replace", False), ("delete", False)])
def test_original_identity_not_final_position_controls_completion(mutation, eligible):
    def change(world):
        if mutation == "move":
            world.google_sheets.rows[0].row_id = 3
        elif mutation == "replace":
            world.google_sheets.rows[0].id = "replacement"
        else:
            world.google_sheets.rows.clear()
        return {"success": True}
    result = evaluate(run_operations(initial(), [update(), ("custom_mutation", {}, change)]))
    assert (result.findings[0].selection is not None) == eligible


def test_equal_revision_observed_completions_abstain_from_allocation():
    data = run_operations(initial(), [update()])
    event = json.loads(data["tool_execution_events"][0]["receipt_json"])
    event["invocation_id"] = "parallel-execution"
    data["tool_execution_events"].append({"source": "tool_server", "receipt_json": canonical_json(event)})
    data["state_write_receipts"].append({**data["state_write_receipts"][0], "write_id": "parallel-execution"})
    result = evaluate(data)
    assert result.outcome.findings[0].value == 1
    assert result.findings[0].selection is None
    assert result.findings[0].reason == "completion_revision_order_ambiguous"


@pytest.mark.parametrize("tamper", ["origin", "revision", "native_id", "requested_fields", "source"])
def test_supplied_effect_projection_must_match_raw_recapture(tamper):
    data = run_operations(initial(), [update()])
    evidence = capture_sheet_effects(data, spec())
    fact = evidence.effects[0]
    if tamper == "origin":
        fact = replace(fact, origin="model")
    elif tamper == "revision":
        fact = replace(fact, applied_revision=True)
    elif tamper == "source":
        evidence = replace(evidence, source_digest="0" * 64)
    else:
        assert fact.params_json is not None
        params = json.loads(fact.params_json)
        params["native_record_id" if tamper == "native_id" else "requested_fields"] = "other" if tamper == "native_id" else ["Name"]
        fact = replace(fact, params_json=canonical_json(params))
    if tamper != "source":
        evidence = replace(evidence, effects=(fact,))
    with pytest.raises(ValueError, match="projection_mismatch"):
        evaluate(data, effects=evidence)


def contract(policy=None, selected=None, selector=None):
    return {"schema_version": 1, "manifest_id": "completion-fixture", "revision": "1",
        "public_request": "Set the amount to twenty dollars",
        "sources": {"rows": table().model_dump(mode="json"), "writes": (selector or spec()).model_dump(mode="json")},
        "checks": [(selected or check()).model_dump(mode="json")],
        "credit": [(policy or rule()).model_dump(mode="json")]}


def test_completion_manifest_roundtrips_and_reads_derived_goal_fields():
    value = ContractSpec.model_validate(contract(selected=numeric_check()))
    assert ContractSpec.model_validate(value.model_dump(mode="python")) == value


@pytest.mark.parametrize("fields", [[], ["Amount", "Amount"], [True], [""]])
def test_completion_goal_fields_are_nonempty_unique_identifiers(fields):
    with pytest.raises(ValueError):
        rule(goal_fields=fields)


@pytest.mark.parametrize("policy", ["required_effect_once@1", "verified_transition_once@1", "per_effect_negative@1"])
def test_other_policies_reject_even_explicit_empty_goal_fields(policy):
    with pytest.raises(ValueError, match="goal_fields_only"):
        CreditSpec.model_validate({"policy": policy, "check": "balance", "channel": "goal", "goal_fields": []})


@pytest.mark.parametrize("invalid", ["append", "unrelated", "constant", "joint"])
def test_manifest_cannot_select_unsupported_completion_semantics(invalid):
    raw = contract()
    if invalid == "append":
        raw["sources"]["writes"]["kind"] = "append"
    elif invalid == "unrelated":
        raw["credit"][0]["goal_fields"] = ["Name"]
    elif invalid == "joint":
        raw["credit"][0]["check"] = None
        raw["credit"][0]["checks"] = ["balance", "other"]
    else:
        raw["checks"][0]["retained_when"] = {"op": "eq", "left": {"kind": "literal", "value": True},
                                               "right": {"kind": "literal", "value": True}}
    with pytest.raises(ValueError):
        ContractSpec.model_validate(raw)


def test_direct_selector_cannot_bypass_goal_field_relevance_or_copied_model_types():
    data = run_operations(initial(), [update()])
    with pytest.raises(ValueError, match="goal_field_not_read"):
        evaluate(data, policy=rule(goal_fields=["Name"]))
    with pytest.raises(ValueError):
        evaluate(data, policy=rule().model_copy(update={"goal_fields": (True,)}))
    predicate = copy.deepcopy(check().retained_when.model_dump(mode="python"))
    predicate["left"]["path"] = ("retained", True)
    with pytest.raises(ValueError):
        evaluate(data, selected=check().model_copy(update={"retained_when": predicate}))


def test_vacuous_field_reference_does_not_mint_completion():
    value = {"kind": "field", "path": ["retained", "Amount"], "domain": "string"}
    result = evaluate(run_operations(initial(), [update()]), check(retained_when={"op": "eq", "left": value, "right": value}))
    assert result.findings[0].initially_satisfied is True
    assert result.findings[0].selection is None
