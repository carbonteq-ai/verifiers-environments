"""Appended support messages reuse authenticated parent writes, not old text."""

import json

import pytest
from test_manifest_record_writes import call
from test_notification_evidence import run_operations

from automationbench.tools.zapier.gorgias.tickets import gorgias_create_ticket_message
from automationbench.tools.zapier.reamaze.conversations import reamaze_add_message
from automationbench_v1.contracts import RecordWriteSource
from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate
from automationbench_v1.contracts.record_writes import capture_record_writes


@pytest.mark.parametrize("service,collection,handler,identity_arg,body_field", [
    ("reamaze", "conversations", reamaze_add_message, "conversation_id", "body"),
    ("gorgias", "tickets", gorgias_create_ticket_message, "ticket_id", "body_text"),
])
@pytest.mark.parametrize("body,expected", [("Verified follow-up", True), ("Unrelated reply", False)])
def test_only_newly_appended_message_matches(service, collection, handler, identity_arg, body_field, body, expected):
    # Matching old customer prose must not be mistaken for a new agent action.
    old = {"id": "old", body_field: "Verified follow-up"}
    initial = {service: {collection: [{"id": "target", "messages": [old]}]}}
    operation = call(handler.__name__, handler, **{identity_arg: "target", body_field: body})
    evidence = capture_record_writes(run_operations(initial, [operation]),
                                     RecordWriteSource(service=service, collection=(collection,), kind="update"))
    assert evidence.complete, evidence.reason
    (fact,) = evidence.effects
    effect = json.loads(fact.params_json)
    assert effect["record_id"] == "target"
    assert len(effect["record"]["messages"]) == 2 and len(effect["added_items"]["messages"]) == 1
    predicate = parse_predicate({
        "op": "any_item", "items": {"kind": "field", "path": ["effect", "added_items", "messages"]},
        "where": {"op": "eq", "left": {"kind": "field", "path": ["item", body_field], "domain": "string"},
                  "right": {"kind": "literal", "value": "Verified follow-up"}},
    })
    assert evaluate_predicate(predicate, {"effect": effect}).value is expected


@pytest.mark.parametrize("service,collection,handler,identity_arg,body_field", [
    ("reamaze", "conversations", reamaze_add_message, "conversation_id", "body"),
    ("gorgias", "tickets", gorgias_create_ticket_message, "ticket_id", "body_text"),
])
def test_nonexistent_parent_does_not_produce_message_credit(service, collection, handler, identity_arg, body_field):
    initial = {service: {collection: [{"id": "target", "messages": []}]}}
    operation = call(handler.__name__, handler, **{identity_arg: "absent", body_field: "Verified follow-up"})
    evidence = capture_record_writes(run_operations(initial, [operation]),
                                     RecordWriteSource(service=service, collection=(collection,), kind="update"))
    assert evidence.complete and not evidence.effects
