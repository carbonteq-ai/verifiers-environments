"""Original typed-record goals qualify useful completion independently of outcomes."""

import copy
import json
from dataclasses import replace

import pytest
from test_manifest_zendesk_effects import initial, update
from test_notification_evidence import run_operations

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.models import CreditSpec
from automationbench_v1.contracts.populations import InitialCollectionSource, capture_population
from automationbench_v1.contracts.record_retained_credit import evaluate_record_retained_completion
from automationbench_v1.contracts.retained_records import (
    RetainedRecordCheck,
    RetainedRecordSource,
    capture_record_retention,
)
from automationbench_v1.contracts.zendesk_effects import (
    ZendeskTicketEffectSource,
    capture_zendesk_ticket_effects,
)


def field(root, name):
    return {"kind": "field", "path": [root, name], "domain": "string"}


def spec():
    return InitialCollectionSource(path=("task_evidence", "initial", "zendesk", "tickets"),
        fields={"ID": ("id",), "Status": ("status",)}, key_fields=("ID",))


def terminal():
    return RetainedRecordSource(path=("task_evidence", "final", "zendesk", "tickets"), fields={"Status": ("status",)})


def check():
    return RetainedRecordCheck.model_validate({"check_id": "solved", "signal_id": "ticket.solved", "role": "goal", "population": "tickets", "source": "final",
        "required_when": {"op": "eq", "left": field("request", "ID"), "right": {"kind": "literal", "value": "T-1"}},
        "retained_when": {"op": "eq", "left": field("retained", "Status"), "right": {"kind": "literal", "value": "solved"}}})


def rule(**changes):
    return CreditSpec.model_validate({"check": "solved", "policy": "records_retained_completion_once@1",
        "channel": "completion", "goal_fields": ["Status"], "completion_selection": "earliest", "effects": "writes", **changes})


def evaluate(source, *, selected_rule=None, effects=None, population=None):
    initial_spec, final_spec, effect_spec = spec(), terminal(), ZendeskTicketEffectSource()
    return evaluate_record_retained_completion(source, check(), selected_rule or rule(),
        {"tickets": population or capture_population(source, initial_spec)}, capture_record_retention(source, final_spec),
        effects or capture_zendesk_ticket_effects(source, effect_spec),
        population_sources={"tickets": initial_spec}, retention_source=final_spec, effect_source=effect_spec)


def target(result):
    return next(finding for finding in result.findings if finding.native_record_id == "T-1")


@pytest.mark.parametrize("method", [None, "PUT", "PATCH"])
def test_real_updates_qualify_exact_completion_and_outcome(method):
    result = evaluate(run_operations(initial(), [update(method=method)]))
    finding = target(result)
    assert finding.status == "eligible" and finding.initially_satisfied is False
    assert finding.selection is not None and finding.selection.occurrence == "execution-0"
    assert next(goal for goal in result.outcome.findings if goal.native_record_id == "T-1").value == 1


def test_initially_solved_then_broken_and_restored_never_acquires_completion_credit():
    finding = target(evaluate(run_operations(initial("solved"), [update("open"), update()])))
    assert finding.status == "ineligible" and finding.initially_satisfied is True and finding.selection is None


@pytest.mark.parametrize("statuses,occurrence", [(["solved", "open", "solved"], "execution-0"),
                                               (["pending", "solved"], "execution-1"),
                                               (["solved", "solved"], "execution-0")])
def test_earliest_observed_completing_action_survives_repair_and_noops(statuses, occurrence):
    finding = target(evaluate(run_operations(initial(), [update(status) for status in statuses])))
    assert finding.status == "eligible" and finding.selection is not None
    assert finding.selection.occurrence == occurrence


def test_terminal_damage_disqualifies_earlier_completion():
    result = evaluate(run_operations(initial(), [update(), update("open")]))
    assert target(result).selection is None and target(result).status == "ineligible"
    assert next(goal for goal in result.outcome.findings if goal.native_record_id == "T-1").value == 0


def test_wrong_target_cannot_complete_original_goal():
    assert target(evaluate(run_operations(initial(), [update(identity="T-2")]))).selection is None


def test_missing_ack_does_not_erase_terminal_outcome_but_cannot_create_recipient():
    source = run_operations(initial(), [update()])
    source["state_write_receipts"].clear()
    result = evaluate(source)
    assert next(goal for goal in result.outcome.findings if goal.native_record_id == "T-1").value == 1
    assert target(result).status == "unavailable" and target(result).selection is None


@pytest.mark.parametrize("raw", [None, True, 1, "__missing__"])
def test_missing_or_malformed_initial_goal_never_inherits_a_default(raw):
    source = run_operations(initial(), [update()])
    record = source["task_evidence"]["initial"]["zendesk"]["tickets"][0]
    if raw == "__missing__":
        del record["status"]
    else:
        record["status"] = raw
    finding = target(evaluate(source))
    assert finding.status == "unavailable" and finding.initially_satisfied is None and finding.selection is None


def test_independent_qualified_completion_survives_later_missing_ack():
    source = run_operations(initial(), [update(), update("open"), update()])
    source["state_write_receipts"].pop()
    result = evaluate(source)
    assert not result.action_scope_complete
    selection = target(result).selection
    assert selection is not None and selection.occurrence == "execution-0"


def test_manufactured_competing_same_revision_witnesses_abstain():
    # Conflicting journals are adversarial raw evidence, not a claimed valid
    # serial controller trajectory. Each receipt is locally acknowledged.
    source = run_operations(initial(), [update()])
    second = copy.deepcopy(source["tool_execution_events"][0])
    receipt = json.loads(second["receipt_json"])
    receipt["invocation_id"] = "competing-execution"
    second["receipt_json"] = canonical_json(receipt)
    source["tool_execution_events"].append(second)
    acknowledgement = copy.deepcopy(source["state_write_receipts"][0])
    acknowledgement["write_id"] = "competing-execution"
    source["state_write_receipts"].append(acknowledgement)
    evidence = capture_zendesk_ticket_effects(source, ZendeskTicketEffectSource())
    assert len([fact for fact in evidence.effects if fact.status == "qualified"]) == 2
    finding = target(evaluate(source))
    assert finding.status == "unavailable" and finding.selection is None
    assert finding.reason == "record_completion_revision_order_ambiguous"


def test_forged_effect_projection_or_initial_projection_rejects():
    source = run_operations(initial(), [update()])
    evidence = capture_zendesk_ticket_effects(source, ZendeskTicketEffectSource())
    forged = replace(evidence, effects=(replace(evidence.effects[0], invocation_id="foreign"),))
    with pytest.raises(ValueError):
        evaluate(source, effects=forged)
    population = capture_population(source, spec())
    forged_population = population.model_copy(update={"source_digest": "0" * 64})
    with pytest.raises(ValueError):
        evaluate(source, population=forged_population)


def test_explicit_selection_and_projected_goal_field_are_required():
    source = run_operations(initial(), [update()])
    with pytest.raises(ValueError):
        rule(completion_selection=None)
    with pytest.raises(ValueError, match="goal_field_not_read"):
        evaluate(source, selected_rule=rule(goal_fields=["ID"]))


def test_source_mutation_does_not_reuse_prior_result():
    source = run_operations(initial(), [update()])
    assert target(evaluate(source)).selection is not None
    damaged = copy.deepcopy(source)
    damaged["task_evidence"]["final"]["zendesk"]["tickets"][0]["status"] = "open"
    assert target(evaluate(damaged)).selection is None
