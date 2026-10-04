"""Genuine native Zendesk handlers qualify facts, never business reward."""

import copy
import json
from dataclasses import asdict, replace
from typing import Any, cast

import pytest
from test_notification_evidence import run_operations, zapier

from automationbench.tools.api.fetch import api_fetch
from automationbench.tools.zapier.zendesk.tickets import zendesk_update_ticket
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.effects import EffectEvidence
from automationbench_v1.contracts.zendesk_effects import (
    ZendeskTicketEffectSource,
    capture_zendesk_ticket_effects,
    validate_zendesk_ticket_effects,
)


def initial(status="open"):
    return {"zendesk": {"tickets": [{"id": "T-1", "subject": "Original", "status": status},
                                   {"id": "T-2", "subject": "Other", "status": "pending"}]}}


def update(status="solved", *, identity="T-1", method=None, url=None, wrapped=True):
    if method:
        body = {"ticket": {"status": status}} if wrapped else {"status": status}
        args = {"url": url or f"https://acme.zendesk.com/api/v2/tickets/{identity}", "method": method, "body": body}
        return "api_fetch", args, lambda world: api_fetch(world, **args)
    args: dict[str, Any] = {"ticket_id": identity, "status": status}
    return zapier("zendesk_update_ticket", args, lambda world: zendesk_update_ticket(world, **args))


def evidence(source):
    return capture_zendesk_ticket_effects(source, ZendeskTicketEffectSource())


def positives(value):
    return [fact for fact in value.effects if fact.status == "qualified"]


def mutate_action(source, change):
    source = copy.deepcopy(source)
    event = source["tool_execution_events"][0]
    receipt = json.loads(event["receipt_json"])
    capture = json.loads(receipt["evidence_json"][0])
    change(capture["action"])
    receipt["evidence_json"][0] = canonical_json(capture)
    event["receipt_json"] = canonical_json(receipt)
    return source


@pytest.mark.parametrize("method,wrapped", [(None, True), ("PUT", True), ("PATCH", True), ("PUT", False)])
def test_genuine_native_status_updates_match_request_response_and_persisted_id(method, wrapped):
    value = evidence(run_operations(initial(), [update(method=method, wrapped=wrapped)]))
    assert value.complete and len(positives(value)) == 1
    fact = positives(value)[0]
    assert fact.kind == "status_update" and fact.expected_revision == 0 and fact.applied_revision == 1
    assert fact.params_json is not None
    assert json.loads(fact.params_json) == {"native_record_id": "T-1", "before_fields": {"status": "open"},
        "after_fields": {"status": "solved"}, "requested_fields": ["status"], "changed_fields": ["status"]}


def test_exact_native_dynamic_host_route_is_supported():
    value = evidence(run_operations(initial(), [update(method="PATCH", url="https://acme.zendesk.com/api/v2/tickets/T-1")]))
    assert value.complete and len(positives(value)) == 1


def test_repeated_noops_are_factual_without_claiming_changed_status_or_progress():
    value = evidence(run_operations(initial(), [update(), update()]))
    assert value.complete and len(positives(value)) == 2
    assert [json.loads(cast(str, fact.params_json))["changed_fields"] for fact in positives(value)] == [["status"], []]
    assert len({fact.effect_id for fact in positives(value)}) == 2


def test_damage_repair_and_later_gap_preserve_independent_occurrences():
    source = run_operations(initial(), [update(), update("open"), update()])
    assert len(positives(evidence(source))) == 3
    source["state_write_receipts"].pop()
    value = evidence(source)
    assert not value.complete and len(positives(value)) == 2
    assert [fact.invocation_id for fact in positives(value)] == ["execution-0", "execution-1"]


@pytest.mark.parametrize("method", [None, "PUT"])
def test_acknowledged_missing_target_business_failure_is_not_positive(method):
    value = evidence(run_operations(initial(), [update(identity="missing", method=method)]))
    assert value.complete and not positives(value)


@pytest.mark.parametrize("change", ["raised", "error", "returned-id", "returned-status", "request-id", "request-status"])
def test_coherent_native_receipt_cannot_override_local_or_request_result_agreement(change):
    source = run_operations(initial(), [update()])
    def alter(action):
        if change == "raised":
            action["status"] = "raised"
        elif change == "error":
            action["error_json"] = canonical_json({"type": "RuntimeError"})
        elif change.startswith("returned"):
            result = json.loads(json.loads(action["result_json"]))
            result["ticket"]["id" if change == "returned-id" else "status"] = "T-2" if change == "returned-id" else "open"
            action["result_json"] = canonical_json(json.dumps(result))
        else:
            outer = json.loads(action["arguments_json"])
            args = json.loads(outer["arguments"])
            args["ticket_id" if change == "request-id" else "status"] = "T-2" if change == "request-id" else "open"
            outer["arguments"] = canonical_json(args)
            action["arguments_json"] = canonical_json(outer)
    value = evidence(mutate_action(source, alter))
    assert not value.complete and not positives(value)


def test_duplicate_native_target_ids_are_unavailable_even_when_handler_picks_first():
    world = initial()
    world["zendesk"]["tickets"].append(copy.deepcopy(world["zendesk"]["tickets"][0]))
    value = evidence(run_operations(world, [update()]))
    assert not value.complete and not positives(value)


def test_missing_ack_and_wrong_handler_target_do_not_qualify_status_effect():
    source = run_operations(initial(), [update()])
    source["state_write_receipts"] = []
    assert not positives(evidence(source))
    call = zapier("zendesk_update_ticket", {"ticket_id": "T-1", "status": "solved"},
                  lambda world: zendesk_update_ticket(world, ticket_id="T-2", status="solved"))
    assert not positives(evidence(run_operations(initial(), [call])))


def test_unsupported_operation_does_not_erase_known_status_update():
    call = ("custom_read", {}, lambda world: "{}")
    value = evidence(run_operations(initial(), [update(), call]))
    assert len(positives(value)) == 1 and not value.complete


def test_real_dispatch_does_not_support_bare_zendesk_relative_route():
    value = evidence(run_operations(initial(), [update(method="PATCH", url="/zendesk/api/v2/tickets/T-1")]))
    assert not positives(value) and not value.complete


@pytest.mark.parametrize("method", [None, "PUT"])
def test_error_payload_cannot_coexist_with_a_claimed_successful_update(method):
    source = run_operations(initial(), [update(method=method)])
    def alter(action):
        result = json.loads(json.loads(action["result_json"]))
        result["error"] = "contradictory failure"
        action["result_json"] = canonical_json(json.dumps(result))
    value = evidence(mutate_action(source, alter))
    assert not positives(value) and not value.complete


@pytest.mark.parametrize("change", ["extra-failure", "omitted-record-field"])
def test_native_response_contract_cannot_be_replaced_by_a_reduced_or_conflicting_wrapper(change):
    source = run_operations(initial(), [update(method="PUT")])
    def alter(action):
        result = json.loads(json.loads(action["result_json"]))
        if change == "extra-failure":
            result["success"] = False
        else:
            del result["ticket"]["subject"]
        action["result_json"] = canonical_json(json.dumps(result))
    assert not positives(evidence(mutate_action(source, alter)))


def test_unknown_before_status_abstains_without_erasing_other_qualified_updates():
    def corrupt(world):
        world.zendesk.tickets[0].status = cast(Any, 1)
        return "{}"
    value = evidence(run_operations(initial(), [update(identity="T-2"), ("custom_mutation", {}, corrupt), update()]))
    assert [json.loads(cast(str, fact.params_json))["native_record_id"] for fact in positives(value)] == ["T-2"]
    assert not value.complete


def test_no_status_request_and_invalid_raw_status_are_explicitly_unavailable():
    call = zapier("zendesk_update_ticket", {"ticket_id": "T-1", "subject": "Renamed"},
        lambda world: zendesk_update_ticket(world, ticket_id="T-1", subject="Renamed"))
    assert not positives(evidence(run_operations(initial(), [call])))
    call = zapier("zendesk_update_ticket", {"ticket_id": "T-1", "status": True},
        lambda world: zendesk_update_ticket(world, ticket_id="T-1", status=cast(Any, True)))
    assert not positives(evidence(run_operations(initial(), [call])))


def test_exact_raw_recapture_rejects_changed_params_and_source_after_wire_reload():
    source = run_operations(initial(), [update()])
    value = evidence(source)
    raw = json.loads(canonical_json(asdict(value)))
    restored = EffectEvidence(raw["source_digest"], raw["selector_digest"], value.effects,
        raw["complete"], raw["reason"])
    validate_zendesk_ticket_effects(restored, source, ZendeskTicketEffectSource())
    forged = replace(value, effects=(replace(value.effects[0], params_json=canonical_json({"native_record_id": "T-2"})),))
    with pytest.raises(ValueError, match="raw_source_or_projection"):
        validate_zendesk_ticket_effects(forged, source, ZendeskTicketEffectSource())
    source["task_evidence"]["final"]["zendesk"]["tickets"][0]["status"] = "open"
    with pytest.raises(ValueError, match="raw_source_or_projection"):
        validate_zendesk_ticket_effects(value, source, ZendeskTicketEffectSource())
