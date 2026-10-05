"""Generic persisted record writes across typed and action-record collections."""

import asyncio
import copy
import json

import pytest
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture
from test_manifest_notification_effects import send
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.google_sheets.row import google_sheets_update_row
from automationbench.tools.zapier.helpcrunch.customers import helpcrunch_update_customer
from automationbench.tools.zapier.monday.actions import monday_create_item
from automationbench.tools.zapier.salesforce.task import salesforce_task_create
from automationbench.tools.zapier.zoom.meeting import zoom_create_meeting
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import RecordWriteSource, load_contract
from automationbench_v1.contracts.record_writes import capture_record_writes


def call(tool, handler, /, **args):
    return zapier(tool, args, lambda world: handler(world, **args))


def world():
    return {"gmail": {"messages": [], "drafts": []},
            "helpcrunch": {"customers": [{"id": "hc1", "email": "a@example.com", "name": "Ada", "tags": []}]},
            "google_sheets": {"worksheets": [{"id": "w", "spreadsheet_id": "s", "title": "W"}],
                              "rows": [{"spreadsheet_id": "s", "worksheet_id": "w", "row_id": 1,
                                        "cells": {"Item": "A", "Total": "$1"}}]}}


def meeting(topic="Safety training"):
    return call("zoom_create_meeting", zoom_create_meeting, type=2, topic=topic,
                start_time="2026-03-02T15:00:00Z", duration=60)


def sheet_update():
    return call("google_sheets_update_row", google_sheets_update_row, spreadsheet="s", worksheet="w",
                row="1", cells={"Total": "$2"})


def payload(fact):
    return json.loads(fact.params_json)


ZOOM = RecordWriteSource(service="zoom", collection=("meetings",), kind="create")


def test_typed_collection_create_is_observed_with_full_record():
    evidence = capture_record_writes(run_operations(world(), [sheet_update(), meeting()]), ZOOM)
    assert evidence.complete, evidence.reason
    (fact,) = evidence.effects
    assert fact.status == "qualified" and fact.kind == "create" and fact.invocation_id == "execution-1"
    record = payload(fact)["record"]
    assert record["topic"] == "Safety training" and payload(fact)["operation"] == "zoom_create_meeting"


def test_action_record_service_create_is_observed():
    spec = RecordWriteSource(service="monday", collection=("actions", "create_item"), kind="create")
    data = run_operations(world(), [call("monday_create_item", monday_create_item,
                                         board_id="b1", item_name="Inspect Generator A-2")])
    evidence = capture_record_writes(data, spec)
    assert evidence.complete, evidence.reason
    assert payload(evidence.effects[0])["record"]["params"]["item_name"] == "Inspect Generator A-2"


def test_salesforce_task_and_helpcrunch_update():
    tasks = RecordWriteSource(service="salesforce", collection=("tasks",), kind="create")
    data = run_operations(world(), [call("salesforce_task_create", salesforce_task_create,
                                         subject="Follow up: no-show", priority="High")])
    (fact,) = capture_record_writes(data, tasks).effects
    assert payload(fact)["record"]["subject"] == "Follow up: no-show"
    updates = RecordWriteSource(service="helpcrunch", collection=("customers",), kind="update")
    data = run_operations(world(), [call("helpcrunch_update_customer", helpcrunch_update_customer,
                                         customer_id="hc1", name="Ada Lovelace")])
    evidence = capture_record_writes(data, updates)
    assert evidence.complete, evidence.reason
    (fact,) = evidence.effects
    assert "name" in payload(fact)["changed_fields"] and payload(fact)["before"]["name"] == "Ada"


def test_kinds_are_separate_inventories():
    data = run_operations(world(), [meeting()])
    updates = RecordWriteSource(service="zoom", collection=("meetings",), kind="update")
    evidence = capture_record_writes(data, updates)
    assert evidence.complete and evidence.effects == ()


def test_write_through_unrecognised_tool_is_still_observed():
    def custom(world_state):
        zoom_create_meeting(world_state, type=2, topic="Via API")
        return {"success": True}
    evidence = capture_record_writes(run_operations(world(), [("custom_tool", {}, custom)]), ZOOM)
    assert [payload(f)["record"]["topic"] for f in evidence.effects] == ["Via API"]


def test_no_write_is_known_absent_beside_unrelated_calls():
    evidence = capture_record_writes(run_operations(world(), [sheet_update(), send()]), ZOOM)
    assert evidence.complete and evidence.effects == ()


def test_missing_ack_on_the_writing_call_is_unavailable():
    data = run_operations(world(), [meeting()])
    data["state_write_receipts"] = []
    evidence = capture_record_writes(data, ZOOM)
    assert not evidence.complete and evidence.effects[0].status == "unavailable"


def test_failed_call_that_changed_state_is_unavailable():
    data = run_operations(world(), [meeting()])
    event = data["tool_execution_events"][0]
    receipt = json.loads(event["receipt_json"])
    body = json.loads(receipt["evidence_json"][0])
    body["action"]["error_json"] = canonical_json({"error": "boom"})
    receipt["evidence_json"] = [canonical_json(body)]
    data["tool_execution_events"][0] = {**event, "receipt_json": canonical_json(receipt)}
    evidence = capture_record_writes(data, ZOOM)
    assert not evidence.complete
    assert evidence.effects[0].status == "unavailable"


def test_sparse_public_initial_service_reconciles():
    data = run_operations(world(), [meeting()])
    sparse = copy.deepcopy(data)
    sparse["task_evidence"]["initial"] = world()
    assert capture_record_writes(sparse, ZOOM).complete
    changed = copy.deepcopy(sparse)
    changed["task_evidence"]["initial"]["zoom"] = {"meetings": [{"id": "invented", "topic": "x"}]}
    assert not capture_record_writes(changed, ZOOM).complete


@pytest.mark.parametrize("raw,message", [
    ({"service": "zoom", "collection": ["participants"], "kind": "create"}, "record_writes_collection_identity_unavailable"),
    ({"service": "nope", "collection": ["x"], "kind": "create"}, "record_writes_service_unknown"),
    ({"service": "monday", "collection": ["actions"], "kind": "create"}, "record_writes_collection_unsupported"),
    ({"service": "zoom", "collection": ["meetings", "x"], "kind": "create"}, "record_writes_collection_identity_unavailable"),
])
def test_declarations_resolve_against_installed_schema(raw, message):
    with pytest.raises(ValidationError, match=message):
        RecordWriteSource.model_validate(raw)


FOLLOWUPS = [("Acme", "Follow up: Acme no-show", "High"), ("Globex", "Follow up: Globex no-show", "Normal")]


def followup_world():
    base = world()
    base["google_sheets"]["worksheets"].append({"id": "f", "spreadsheet_id": "s", "title": "Followups"})
    base["google_sheets"]["rows"] += [{"spreadsheet_id": "s", "worksheet_id": "f", "row_id": 10 + i,
                                       "cells": {"Account": a, "Subject": subject, "Priority": priority}}
                                      for i, (a, subject, priority) in enumerate(FOLLOWUPS)]
    return base


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def followup_contract():
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "followup-fixture", "revision": "1",
        "public_request": "Create a Salesforce follow-up task for each no-show.",
        "sources": {"followups": {"adapter": "google_sheets.rows@1",
                                  "path": ["task_evidence", "initial", "google_sheets"],
                                  "spreadsheet_id": "s", "worksheet_id": "f", "key_fields": ["Account"],
                                  "required_fields": ["Subject", "Priority"]},
                    "tasks": {"adapter": "service.record_writes@1", "service": "salesforce",
                              "collection": ["tasks"], "kind": "create"}},
        "checks": [{"check_id": "followup-task", "signal_id": "sales.followup_task", "role": "goal",
                    "operator": "effects.required_when@1", "semantics": "new_occurrence",
                    "population": "followups", "source": "tasks",
                    "required_when": {"op": "ne", "left": field("request", "Account"),
                                      "right": {"kind": "literal", "value": ""}},
                    "effect_match": {"op": "all", "args": [
                        {"op": "eq", "left": field("effect", "record", "subject"), "right": field("request", "Subject")},
                        {"op": "eq", "left": field("effect", "record", "priority"), "right": field("request", "Priority")}]}}],
        "credit": [{"check": "followup-task", "policy": "required_effect_once@1", "channel": "useful-action"}]}))


def scored(monkeypatch, calls, missing_ack=None):
    declared = followup_contract()
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, _, trace = native_fixture(run_operations(followup_world(), calls), missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    found = {}
    for batch in trace.assessment_batches:
        for receipt in batch.run.execution_evidence:
            body = json.loads(receipt.payload_json)
            if body.get("kind") == "finding":
                found[body["candidate_identity"][-1]] = (body["status"], body["value"])
    credited = [part.recipient.execution.invocation_id for assignment in trace.credit_assignments
                if assignment.status == "complete" for part in assignment.contributions if part.value == 1]
    return found, credited


def create_task(subject, priority):
    return call("salesforce_task_create", salesforce_task_create, subject=subject, priority=priority)


def test_native_obligation_credits_the_creating_execution(monkeypatch):
    found, credited = scored(monkeypatch, [create_task("Follow up: Acme no-show", "High"), sheet_update()])
    assert found == {10: ("valid", 1), 11: ("valid", 0)}
    assert credited == ["execution-0"]


def test_native_wrong_priority_and_missing_ack(monkeypatch):
    found, credited = scored(monkeypatch, [create_task("Follow up: Acme no-show", "Low")])
    assert found[10] == ("valid", 0) and not credited
    found, credited = scored(monkeypatch, [create_task("Follow up: Acme no-show", "High")], missing_ack=0)
    assert found[10][0] == "abstained" and not credited


def test_record_id_is_the_plain_native_identity():
    (fact,) = capture_record_writes(run_operations(world(), [meeting()]), ZOOM).effects
    body = payload(fact)
    # Not a JSON-quoted string: it compares equal to the native field.
    assert body["record_id"] == body["record"]["id"]
    assert type(body["record_id"]) is type(body["record"]["id"])


def test_sibling_action_keys_form_one_inventory():
    from automationbench.tools.zapier.monday.actions import (
        monday_change_status_column_value,
        monday_change_text_column_value,
    )
    both = RecordWriteSource(service="monday", collection=("actions", "change_status_column_value",
                                                           "change_text_column_value"), kind="create")
    status_only = RecordWriteSource(service="monday", collection=("actions", "change_status_column_value"),
                                    kind="create")
    data = run_operations(world(), [call("monday_change_text_column_value", monday_change_text_column_value,
                                         board_id="b1", item_id="i1", column_id="status", value_text="Done")])
    (fact,) = capture_record_writes(data, both).effects
    assert payload(fact)["record"]["action_key"] == "change_text_column_value"
    assert capture_record_writes(data, status_only).effects == ()
    data = run_operations(world(), [call("monday_change_status_column_value", monday_change_status_column_value,
                                         board_id="b1", item_id="i1", column_id="status", value_label="Done")])
    assert len(capture_record_writes(data, both).effects) == 1
    with pytest.raises(ValidationError, match="record_writes_collection_unsupported"):
        RecordWriteSource(service="monday", collection=("actions", "k", "k"), kind="create")


def test_values_text_exposes_agent_chosen_fields():
    spec = RecordWriteSource(service="monday", collection=("actions", "create_item"), kind="create")
    data = run_operations(world(), [call("monday_create_item", monday_create_item,
                                         board_id="b1", item_name="Inspect Generator A-2")])
    (fact,) = capture_record_writes(data, spec).effects
    assert "Inspect Generator A-2" in payload(fact)["values_text"].splitlines()


@pytest.mark.parametrize("shape", ["typed", "actions"])
def test_persisted_effect_predicates_use_exact_record_projection(shape):
    from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate

    if shape == "typed":
        source, invocation, name, path = ZOOM, meeting(), "Safety training", ["effect", "record", "topic"]
    else:
        source = RecordWriteSource(service="monday", collection=("actions", "create_item"), kind="create")
        invocation = call("monday_create_item", monday_create_item, board_id="b1", item_name="Inspect Generator A-2")
        name, path = "Inspect Generator A-2", ["effect", "record", "params", "item_name"]
    evidence = capture_record_writes(run_operations(world(), [invocation]), source)
    assert evidence.complete and len(evidence.effects) == 1
    context = {"effect": payload(evidence.effects[0])}
    predicate = {"op": "eq", "left": {"kind": "field", "path": path, "domain": "string"},
        "right": {"kind": "literal", "value": name}}
    assert evaluate_predicate(parse_predicate(predicate), context).value is True
    extra_wrapper = copy.deepcopy(predicate)
    extra_wrapper["left"]["path"].insert(2, "record")
    assert evaluate_predicate(parse_predicate(extra_wrapper), context).value is None


def test_generated_fields_absent_from_public_records_do_not_block_closure():
    seeded = world()
    seeded["salesforce"] = {"tasks": [{"id": "t0", "subject": "Existing", "status": "Open"}]}
    data = run_operations(seeded, [create_task("Follow up: Acme no-show", "High")])
    sparse = copy.deepcopy(data)
    sparse["task_evidence"]["initial"] = seeded  # public record lacks generated timestamps
    tasks = RecordWriteSource(service="salesforce", collection=("tasks",), kind="create")
    evidence = capture_record_writes(sparse, tasks)
    assert evidence.complete, evidence.reason
    changed = copy.deepcopy(sparse)
    changed["task_evidence"]["initial"]["salesforce"]["tasks"][0]["subject"] = "Different"
    assert not capture_record_writes(changed, tasks).complete
