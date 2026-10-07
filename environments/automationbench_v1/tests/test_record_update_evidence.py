"""Executed record updates and capture/schema counterexamples for one strategy."""

import copy
import json

import pytest
from test_notification_evidence import run_operations, zapier

from automationbench.domains.simple import tasks
from automationbench.tools.api.impl.salesforce import salesforce_opportunity_update as api_update
from automationbench.tools.zapier.salesforce.opportunity import salesforce_opportunity_update
from automationbench.tools.zapier.salesforce.record import salesforce_update_record
from automationbench_v1.simple_record_contracts import CONTRACTS, evaluate_simple_record_update


def public(contract):
    return getattr(tasks, "get_" + contract.task_name.replace(".", "_"))()


def update(contract, value=None, target=None, generic=False, api=False):
    field = contract.desired_fields[0]
    value = field.value if value is None else value
    identity = target or contract.record_id
    if api:
        args = {
            "method": "PATCH",
            "url": "/services/data/v60.0/sobjects/Opportunity/" + identity,
            "body": {field.name: value},
        }
        return (
            "api_fetch",
            args,
            lambda world: api_update(world, record_id=identity, **{field.name: value}),
        )
    if generic:
        args = {"object": "Opportunity", "recordId": identity, "fields": {field.name: value}}
        return zapier(
            "salesforce_update_record", args, lambda world: salesforce_update_record(world, **args)
        )
    args = {"opportunity_id": identity, field.name: value}
    return zapier(
        "salesforce_opportunity_update",
        args,
        lambda world: salesforce_opportunity_update(world, **args),
    )


def source(contract=CONTRACTS[0], operations=None, initial=None):
    data = public(contract)
    result = run_operations(
        initial if initial is not None else data["info"]["initial_state"],
        operations if operations is not None else [update(contract)],
    )
    result["task_evidence"].update(task_name=contract.task_name, prompt=data["prompt"])
    return result


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda item: item.task_name)
def test_all_ten_executed_native_updates_qualify_requested_field(contract):
    findings = evaluate_simple_record_update(source(contract))
    assert findings[0].value == 1 and findings[0].occurrence == "execution-0"
    assert findings[1].value == 1


@pytest.mark.parametrize("generic,api", [(True, False), (False, True)])
def test_native_generic_and_documented_empty_patch_result_are_supported(generic, api):
    contract = CONTRACTS[0]
    findings = evaluate_simple_record_update(
        source(contract, [update(contract, generic=generic, api=api)])
    )
    assert findings[0].value == 1 and findings[0].occurrence == "execution-0"


def test_wrong_target_changes_another_record_without_satisfying_request():
    contract = CONTRACTS[0]
    initial = copy.deepcopy(public(contract)["info"]["initial_state"])
    other = dict(initial["salesforce"]["opportunities"][0], id="other")
    initial["salesforce"]["opportunities"].append(other)
    findings = evaluate_simple_record_update(
        source(contract, [update(contract, target="other")], initial)
    )
    assert findings[0].value == 0 and findings[0].occurrence is None


def test_already_correct_then_break_restore_never_earns_progress_credit():
    contract = CONTRACTS[0]
    initial = source(contract)["task_evidence"]["final"]
    findings = evaluate_simple_record_update(
        source(contract, [update(contract, "Prospecting"), update(contract)], initial)
    )
    assert findings[0].value == 1 and findings[0].reason == "already_correct_state"
    assert findings[0].occurrence is None


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda item: item.task_name)
def test_all_ten_already_correct_baselines_preserve_goal_without_progress(contract):
    initial = source(contract)["task_evidence"]["final"]
    findings = evaluate_simple_record_update(source(contract, [update(contract)], initial))
    assert findings[0].value == 1 and findings[0].reason == "already_correct_state"
    assert findings[0].occurrence is None


def test_first_completion_then_damage_restore_does_not_multiply_accomplishment():
    contract = CONTRACTS[0]
    findings = evaluate_simple_record_update(
        source(contract, [update(contract), update(contract, "Prospecting"), update(contract)])
    )
    assert findings[0].value == 1 and findings[0].occurrence is None


def test_duplicate_noop_keeps_first_real_accomplishment():
    contract = CONTRACTS[0]
    findings = evaluate_simple_record_update(source(contract, [update(contract), update(contract)]))
    assert findings[0].value == 1 and findings[0].occurrence == "execution-0"


def test_missing_ack_keeps_final_outcome_without_fabricating_attribution():
    result = source()
    result["state_write_receipts"] = []
    findings = evaluate_simple_record_update(result)
    assert findings[0].value == 1 and findings[0].occurrence is None
    assert findings[1].value is None


def test_failed_native_update_and_unreconciled_terminal_do_not_gain_action_credit():
    contract = CONTRACTS[0]
    result = source(contract, [update(contract, target="absent")])
    assert evaluate_simple_record_update(result)[0].value == 0
    result = source(contract)
    result["task_evidence"]["final"]["salesforce"]["opportunities"][0]["description"] = (
        "external unrecorded change"
    )
    assert evaluate_simple_record_update(result)[0].occurrence is None
    assert evaluate_simple_record_update(result)[1].value is None


@pytest.mark.parametrize("change", ["absent", "duplicate", "wrong_schema"])
def test_target_absence_ambiguity_and_schema_are_unavailable(change):
    result = source()
    records = result["task_evidence"]["initial"]["salesforce"]["opportunities"]
    if change == "absent":
        records.clear()
    elif change == "duplicate":
        records.append(dict(records[0]))
    else:
        records[0]["not_a_native_field"] = "invented"
    assert evaluate_simple_record_update(result)[0].value is None


def test_changed_public_request_or_nonempty_add_description_is_unavailable():
    result = source()
    result["task_evidence"]["prompt"] = [{"role": "user", "content": "Update every opportunity"}]
    with pytest.raises(ValueError, match="exact_public_request_unresolved"):
        evaluate_simple_record_update(result)
    description = CONTRACTS[5]
    initial = copy.deepcopy(public(description)["info"]["initial_state"])
    initial["salesforce"]["opportunities"][0]["description"] = "Existing context"
    findings = evaluate_simple_record_update(source(description, initial=initial))
    assert (
        findings[0].value is None
        and findings[0].reason == "record_baseline_interpretation_contract_required"
    )


def test_response_wrong_identity_cannot_attribute_field_change():
    result = source()
    event = result["tool_execution_events"][0]
    receipt = json.loads(event["receipt_json"])
    envelope = json.loads(receipt["evidence_json"][0])
    payload = json.loads(json.loads(envelope["action"]["result_json"]))
    payload["opportunity"]["Id"] = "wrong"
    envelope["action"]["result_json"] = json.dumps(json.dumps(payload))
    receipt["evidence_json"] = [json.dumps(envelope)]
    event["receipt_json"] = json.dumps(receipt)
    findings = evaluate_simple_record_update(result)
    assert findings[0].value == 1 and findings[0].occurrence is None


@pytest.mark.parametrize("success", [None, "missing", False, 1])
def test_native_success_must_be_explicit_true_not_inferred_from_matching_response(success):
    result = source()
    event = result["tool_execution_events"][0]
    receipt = json.loads(event["receipt_json"])
    envelope = json.loads(receipt["evidence_json"][0])
    payload = json.loads(json.loads(envelope["action"]["result_json"]))
    if success == "missing":
        payload.pop("success")
    else:
        payload["success"] = success
    envelope["action"]["result_json"] = json.dumps(json.dumps(payload))
    receipt["evidence_json"] = [json.dumps(envelope)]
    event["receipt_json"] = json.dumps(receipt)
    findings = evaluate_simple_record_update(result)
    assert findings[0].value == 1 and findings[0].occurrence is None


def test_public_from_stage_requirement_is_not_silently_discarded():
    contract = CONTRACTS[6]
    initial = copy.deepcopy(public(contract)["info"]["initial_state"])
    initial["salesforce"]["opportunities"][0]["stage_name"] = "Negotiation/Review"
    findings = evaluate_simple_record_update(source(contract, initial=initial))
    assert (
        findings[0].value is None
        and findings[0].reason == "record_baseline_interpretation_contract_required"
    )
