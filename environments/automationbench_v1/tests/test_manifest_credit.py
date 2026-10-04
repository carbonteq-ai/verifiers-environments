"""Retained transition credit, with no task re-evaluation or duplicate reward."""

import copy
import json
from typing import Any

import pytest
from test_notification_evidence import zapier
from test_record_update_evidence import CONTRACTS, source, update

from automationbench.tools.zapier.salesforce.opportunity import salesforce_opportunity_update
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract, load_task_contract
from automationbench_v1.contracts.credit import select_credit
from automationbench_v1.contracts.engine import Evaluation, evaluate_contract


def selections(data, previous=CONTRACTS[0], contract=None):
    contract = contract or load_task_contract(previous.task_name)
    evaluation = evaluate_contract(data, contract)
    return evaluation, select_credit(contract, evaluation)


def test_record_credit_routes_mixed_retained_policy_and_rejects_misrouted_findings():
    from test_manifest_retained import check, table
    from test_manifest_sheet_effects import spec

    manifest = load_task_contract(CONTRACTS[0].task_name).model_dump(mode="json")
    manifest["sources"].update({"rows": table().model_dump(mode="json"),
                                "writes": spec().model_dump(mode="json")})
    manifest["checks"].append(check().model_dump(mode="json"))
    manifest["credit"].append({"check": "balance", "policy": "retained_completion_once@1",
                               "channel": "completion", "goal_fields": ["Amount"]})
    contract = load_contract(canonical_json(manifest))
    evaluation, selected = selections(source(), contract=contract)
    assert len(selected) == 1 and selected[0].check_id != "balance"
    wrong = evaluation.results[0].model_copy(update={"check_id": "balance", "signal_id": "balance.retained"})
    misrouted = Evaluation.model_validate(evaluation.model_dump() | {"results": [wrong.model_dump()]})
    with pytest.raises(ValueError, match="manifest_credit_check_unknown"):
        select_credit(contract, misrouted)


@pytest.mark.parametrize("previous", CONTRACTS, ids=lambda item: item.task_name)
def test_all_ten_executed_updates_have_one_verified_recipient(previous):
    evaluation, selected = selections(source(previous), previous)
    assert evaluation.results[0].value == 1
    assert len(selected) == 1 and selected[0].occurrence == "execution-0"
    assert selected[0].value == 1 and selected[0].channel == "goal"


@pytest.mark.parametrize("generic,api", [(True, False), (False, True)])
def test_generic_and_empty_api_patch_return_can_receive_credit(generic, api):
    _, selected = selections(source(operations=[update(CONTRACTS[0], generic=generic, api=api)]))
    assert len(selected) == 1


def test_missing_ack_preserves_outcome_but_has_no_action_recipient():
    data = source()
    data["state_write_receipts"] = []
    evaluation, selected = selections(data)
    assert evaluation.results[0].value == 1
    assert evaluation.results[1].value is None and selected == ()


@pytest.mark.parametrize("previous", CONTRACTS, ids=lambda item: item.task_name)
def test_all_ten_initially_correct_tasks_keep_goal_without_credit(previous):
    initial = source(previous)["task_evidence"]["final"]
    evaluation, selected = selections(source(previous, [update(previous)], initial), previous)
    assert evaluation.results[0].value == 1 and selected == ()


def test_initially_correct_break_restore_does_not_mint_progress():
    previous = CONTRACTS[0]
    initial = source(previous)["task_evidence"]["final"]
    evaluation, selected = selections(
        source(previous, [update(previous, "Prospecting"), update(previous)], initial)
    )
    assert evaluation.results[0].value == 1 and selected == ()


def test_first_completion_then_damage_restore_has_no_credit():
    previous = CONTRACTS[0]
    _, selected = selections(
        source(previous, [update(previous), update(previous, "Prospecting"), update(previous)])
    )
    assert selected == ()


def test_duplicate_noop_retains_only_first_real_accomplishment():
    previous = CONTRACTS[0]
    _, selected = selections(source(previous, [update(previous), update(previous)]))
    assert len(selected) == 1 and selected[0].occurrence == "execution-0"


def test_incomplete_finalization_cannot_use_stale_successful_write_for_credit():
    data = source()
    data["task_evidence"]["complete"] = False
    evaluation, selected = selections(data)
    assert evaluation.results[0].status == "abstained" and selected == ()


def test_retained_output_roundtrip_drives_credit_without_rechecking(monkeypatch):
    from automationbench_v1.contracts import engine

    contract = load_task_contract(CONTRACTS[0].task_name)
    evaluation = evaluate_contract(source(), contract)
    expected = select_credit(contract, evaluation)

    def forbidden(*args, **kwargs):
        pytest.fail("credit selection recomputed task checks")

    monkeypatch.setattr(engine, "capture_records", forbidden)
    monkeypatch.setattr(engine, "evaluate_contract", forbidden)
    retained = Evaluation.model_validate_json(evaluation.model_dump_json())
    assert select_credit(contract, retained) == expected


def test_wrong_manifest_revision_cannot_consume_retained_credit():
    contract = load_task_contract(CONTRACTS[0].task_name)
    evaluation = evaluate_contract(source(), contract)
    changed = contract.model_dump(mode="json")
    changed["revision"] += "-changed"
    with pytest.raises(ValueError, match="credit_contract_mismatch"):
        select_credit(load_contract(json.dumps(changed)), evaluation)


@pytest.mark.parametrize("mutation", ["selector", "inventory"])
def test_credit_rejects_receipt_with_wrong_source_selection(mutation):
    contract = load_task_contract(CONTRACTS[0].task_name)
    evaluation = evaluate_contract(source(), contract)
    retained = json.loads(evaluation.evidence_json)
    if mutation == "selector":
        retained["target"]["selector_digest"] = "0" * 64
    else:
        retained["extra-source"] = copy.deepcopy(retained["target"])
    changed = Evaluation.model_validate(evaluation.model_dump() | {
        "evidence_json": canonical_json(retained),
    })
    with pytest.raises(ValueError, match="manifest_credit_(selector|source_inventory)_mismatch"):
        select_credit(contract, changed)


def test_two_goal_checks_same_execution_channel_require_explicit_aggregation():
    previous = CONTRACTS[0]
    manifest = load_task_contract(previous.task_name).model_dump(mode="json")
    second = copy.deepcopy(manifest["checks"][0])
    second["check_id"] = "requested-type"
    second["expected"] = [{"field": "type", "value": "Renewal", "comparison": "string"}]
    manifest["checks"].append(second)
    manifest["credit"].append(
        {"check": "requested-type", "policy": "verified_transition_once@1", "channel": "goal"}
    )
    contract = load_contract(json.dumps(manifest))
    args: dict[str, Any] = {
        "opportunity_id": previous.record_id,
        "stage_name": "Closed Won",
        "type": "Renewal",
    }
    operation = zapier(
        "salesforce_opportunity_update",
        args,
        lambda world: salesforce_opportunity_update(world, **args),
    )
    evaluation = evaluate_contract(source(previous, [operation]), contract)
    assert all(item.value == 1 for item in evaluation.results)
    with pytest.raises(ValueError, match="credit_aggregation_required"):
        select_credit(contract, evaluation)


def edit_payload(data, change):
    event = data["tool_execution_events"][0]
    receipt = json.loads(event["receipt_json"])
    envelope = json.loads(receipt["evidence_json"][0])
    payload = json.loads(json.loads(envelope["action"]["result_json"]))
    change(payload)
    envelope["action"]["result_json"] = json.dumps(json.dumps(payload))
    receipt["evidence_json"] = [json.dumps(envelope)]
    event["receipt_json"] = json.dumps(receipt)


def joint_contract():
    manifest = load_task_contract(CONTRACTS[0].task_name).model_dump(mode="json")
    second = copy.deepcopy(manifest["checks"][0])
    second["check_id"] = "requested-type"
    second["expected"] = [{"field": "type", "value": "Renewal", "comparison": "string"}]
    manifest["checks"].append(second)
    manifest["credit"] = [
        {
            "checks": ["requested-state", "requested-type"],
            "policy": "joint_verified_transition_once@1",
            "channel": "goal",
        }
    ]
    return load_contract(json.dumps(manifest))


def combined_update(**fields):
    args: dict[str, Any] = {"opportunity_id": CONTRACTS[0].record_id, **fields}
    return zapier(
        "salesforce_opportunity_update",
        args,
        lambda world: salesforce_opportunity_update(world, **args),
    )


def test_joint_credit_has_one_contribution_and_both_goal_parents():
    contract = joint_contract()
    data = source(operations=[combined_update(stage_name="Closed Won", type="Renewal")])
    evaluation = evaluate_contract(data, contract)
    selected = select_credit(contract, evaluation)
    assert len(selected) == 1
    assert selected[0].check_ids == ("requested-state", "requested-type")
    assert selected[0].occurrence == "execution-0" and selected[0].value == 1
    assert selected[0].policy == "joint_verified_transition_once@1"


@pytest.mark.parametrize(
    "boundary", ["different-witness", "initially-correct", "missing-ack", "missing-parent"]
)
def test_joint_credit_cannot_merge_unqualified_or_distinct_accomplishments(boundary):
    contract = joint_contract()
    operations = [combined_update(stage_name="Closed Won", type="Renewal")]
    initial = None
    if boundary == "different-witness":
        operations = [combined_update(stage_name="Closed Won"), combined_update(type="Renewal")]
    elif boundary == "initially-correct":
        initial = copy.deepcopy(source()["task_evidence"]["initial"])
        initial["salesforce"]["opportunities"][0]["type"] = "Renewal"
    data = source(operations=operations, initial=initial)
    if boundary == "missing-ack":
        data["state_write_receipts"] = []
    evaluation = evaluate_contract(
        data, contract, check_ids=("requested-state",) if boundary == "missing-parent" else None
    )
    assert select_credit(contract, evaluation) == ()


@pytest.mark.parametrize("success", [False, None, 1])
def test_response_success_requires_exact_true(success):
    data = source()
    edit_payload(data, lambda payload: payload.update(success=success))
    evaluation, selected = selections(data)
    assert evaluation.results[0].value == 1 and selected == ()


def test_wrong_returned_identity_cannot_attribute_persisted_change():
    data = source()
    edit_payload(data, lambda payload: payload["opportunity"].update(Id="wrong-returned-id"))
    evaluation, selected = selections(data)
    assert evaluation.results[0].value == 1 and selected == ()


def test_invalid_returned_calendar_date_cannot_be_accepted_by_prefix():
    previous = CONTRACTS[3]
    data = source(previous)
    edit_payload(
        data,
        lambda payload: payload["opportunity"].update(CloseDate="2026-03-31 invalid date suffix"),
    )
    evaluation, selected = selections(data, previous)
    assert evaluation.results[0].value == 1 and selected == ()


def test_numeric_returned_bool_cannot_equal_requested_one():
    previous = CONTRACTS[2]
    manifest = load_task_contract(previous.task_name).model_dump(mode="json")
    manifest["checks"][0]["expected"][0]["value"] = 1
    data = source(previous, [update(previous, 1)])
    edit_payload(data, lambda payload: payload["opportunity"].update(Amount=True))
    evaluation, selected = selections(data, previous, load_contract(json.dumps(manifest)))
    assert evaluation.results[0].value == 1 and selected == ()


def test_unrequested_field_drift_cannot_receive_action_credit():
    args = {"opportunity_id": CONTRACTS[0].record_id, "description": "Updated context"}
    operation = zapier(
        "salesforce_opportunity_update",
        args,
        lambda world: salesforce_opportunity_update(
            world,
            opportunity_id=CONTRACTS[0].record_id,
            description="Updated context",
            stage_name="Closed Won",
        ),
    )
    data = source(operations=[operation])
    evaluation, selected = selections(data)
    assert evaluation.results[0].value == 1 and selected == ()


@pytest.mark.parametrize("break_restore", [False, True])
def test_missing_initial_field_default_cannot_fabricate_verified_transition(break_restore):
    initial = copy.deepcopy(source()["task_evidence"]["initial"])
    del initial["salesforce"]["opportunities"][0]["stage_name"]
    operations = (
        [update(CONTRACTS[0]), update(CONTRACTS[0], "Prospecting"), update(CONTRACTS[0])]
        if break_restore
        else [update(CONTRACTS[0])]
    )
    data = source(initial=initial, operations=operations)
    # Preserve the captured public baseline omission rather than the simulator's
    # hydrated model default. Credit requires explicit baseline field evidence.
    del data["task_evidence"]["initial"]["salesforce"]["opportunities"][0]["stage_name"]
    evaluation, selected = selections(data)
    assert evaluation.results[0].value == 1 and selected == ()
