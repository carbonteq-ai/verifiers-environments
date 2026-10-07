"""Real Airtable mutations, independently enveloped for native scoring tests."""

import asyncio
import copy
import json

import pytest
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture
from test_manifest_record_writes import call, field, payload
from test_notification_evidence import run_operations

from automationbench.tools.zapier.airtable.actions import airtable_updateRecord
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import RecordWriteSource, load_contract
from automationbench_v1.contracts.record_writes import capture_record_writes
from automationbench_v1.tools import AutomationBenchState

SOURCE = RecordWriteSource(service="airtable", collection=("bases", "tables", "records"), kind="update")


def initial():
    return {"airtable": {"bases": [{"id": "app", "name": "Expenses", "tables": [
        {"id": "tbl", "name": "Requests", "records": [
            {"id": "r1", "fields": {"Status": "Pending", "Reason": ""}}]}]}]},
        "google_sheets": {"worksheets": [{"id": "w", "spreadsheet_id": "s", "title": "W"}],
                          "rows": [{"spreadsheet_id": "s", "worksheet_id": "w", "row_id": 1,
                                    "cells": {"Record": "r1", "Status": "Approved"}}]}}


def update(status="Approved", row="r1", base="app", table="Requests"):
    return call("airtable_updateRecord", airtable_updateRecord, applicationId=base,
                tableName=table, rowId=row, fields_json=canonical_json({"Status": status, "Reason": "Policy"}))


def test_persisted_fields_not_action_log_claims():
    material = run_operations(initial(), [update()])
    evidence = capture_record_writes(material, SOURCE)
    assert evidence.complete, evidence.reason
    (fact,) = evidence.effects
    actual = payload(fact)
    assert actual["record"]["fields"]["Status"] == "Approved"
    assert actual["before"]["fields"]["Status"] == "Pending"
    assert actual["record"]["base_id"] == "app" and actual["record"]["table_id"] == "tbl"
    assert actual["record"]["record_id"] == "r1"
    missing = run_operations(initial(), [update(row="absent")])
    assert missing["task_evidence"]["final"]["airtable"]["actions"]["updateRecord"][0]["params"]["fields"]
    empty = capture_record_writes(missing, SOURCE)
    assert empty.complete and not empty.effects


def test_parent_identity_and_alternative_handler_names():
    public = initial()
    sibling = copy.deepcopy(public["airtable"]["bases"][0])
    sibling["id"], sibling["name"] = "other", "Other"
    public["airtable"]["bases"].append(sibling)
    evidence = capture_record_writes(run_operations(public, [update(base="Expenses", table="tbl")]), SOURCE)
    assert evidence.complete
    (fact,) = evidence.effects
    assert json.loads(payload(fact)["record_id"]) == ["app", "tbl", "r1"]


def test_repeated_action_log_does_not_repeat_a_persisted_write():
    evidence = capture_record_writes(run_operations(initial(), [update(), update()]), SOURCE)
    assert evidence.complete and len(evidence.effects) == 1


def test_terminal_field_tamper_cannot_close_scope():
    material = run_operations(initial(), [update()])
    material["task_evidence"]["final"]["airtable"]["bases"][0]["tables"][0]["records"][0]["fields"]["Status"] = "Rejected"
    evidence = capture_record_writes(material, SOURCE)
    assert not evidence.complete and evidence.reason == "record_writes_initial_terminal_scope_mismatch"


@pytest.mark.parametrize("damage", ["duplicate_base", "duplicate_table", "duplicate_row", "missing_fields", "missing_id"])
def test_malformed_nested_inventory_abstains(damage):
    public = initial()
    bases = public["airtable"]["bases"]
    tables = bases[0]["tables"]
    rows = tables[0]["records"]
    if damage == "duplicate_base":
        bases.append(copy.deepcopy(bases[0]))
    elif damage == "duplicate_table":
        tables.append(copy.deepcopy(tables[0]))
    elif damage == "duplicate_row":
        rows.append(copy.deepcopy(rows[0]))
    elif damage == "missing_fields":
        del rows[0]["fields"]
    else:
        del tables[0]["id"]
    evidence = capture_record_writes(run_operations(public, []), SOURCE)
    # No-call scope validation must inspect the selected inventory as well.
    assert not evidence.complete


def test_nested_admission_is_fixed_and_bounded():
    with pytest.raises(ValidationError, match="airtable_identity_fixed"):
        RecordWriteSource(service="airtable", collection=("bases", "tables", "records"),
                          kind="update", identity_paths=(("id",), ("name",)))
    public = initial()
    public["airtable"]["bases"] = [public["airtable"]["bases"][0]] * 65_537
    evidence = capture_record_writes(run_operations(public, []), SOURCE)
    assert not evidence.complete and "budget" in evidence.reason


def contract():
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "airtable-write-fixture", "revision": "1",
        "public_request": "Do not provision processed requests or requests with manager rank below 3.",
        "sources": {"queue": {"adapter": "google_sheets.rows@1",
                              "path": ["task_evidence", "initial", "google_sheets"],
                              "spreadsheet_id": "s", "worksheet_id": "w", "key_fields": ["Record"],
                              "required_fields": ["Status"]}, "writes": SOURCE.model_dump(mode="json")},
        "checks": [{"check_id": "status", "signal_id": "expense.status", "role": "goal",
                    "operator": "effects.required_when@1", "semantics": "new_occurrence",
                    "population": "queue", "source": "writes",
                    "required_when": {"op": "ne", "left": field("request", "Record"),
                                      "right": {"kind": "literal", "value": ""}},
                    "effect_match": {"op": "all", "args": [
                        {"op": "eq", "left": field("effect", "record", "base_id"),
                         "right": {"kind": "literal", "value": "app"}},
                        {"op": "eq", "left": field("effect", "record", "table_id"),
                         "right": {"kind": "literal", "value": "tbl"}},
                        {"op": "eq", "left": field("effect", "record", "record_id"),
                         "right": field("request", "Record")},
                        {"op": "eq", "left": field("effect", "record", "fields", "Status"),
                         "right": field("request", "Status")}]}}],
        "credit": [{"check": "status", "policy": "required_effect_once@1", "channel": "useful-action"}]}))


@pytest.mark.parametrize("status,row,missing_ack,expected", [
    ("Approved", "r1", None, ("valid", 1)), ("Rejected", "r1", None, ("valid", 0)),
    ("Approved", "absent", None, ("valid", 0)), ("Approved", "r1", 0, ("abstained", None)),
])
def test_native_status_credit_and_repeat_parity(monkeypatch, status, row, missing_ack, expected):
    declared = contract()
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, _, trace = native_fixture(run_operations(initial(), [update(status, row)]), missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)

    def score():
        start = len(trace.assessment_batches)
        asyncio.run(task.score(trace))
        assert not trace.assessment_errors and not trace.credit_errors and trace.rewards == scalar
        return sorted((json.loads(r.payload_json)["status"], json.loads(r.payload_json)["value"])
                      for b in trace.assessment_batches[start:] for r in b.run.execution_evidence
                      if json.loads(r.payload_json).get("kind") == "finding"
                      and json.loads(r.payload_json).get("check_id") == "status")

    before = score()
    assert expected in before
    assert score() == before
    trace = type(trace).model_validate_json(trace.model_dump_json())
    trace.state = AutomationBenchState(world=trace.info["automationbench"]["end_state"],
                                      initial_state=task.data.initial_state, assertions=task.data.assertions)
    assert score() == before
    credits = [c for a in trace.credit_assignments if a.status == "complete"
               for c in a.contributions if c.value == 1]
    assert bool(credits) == (expected == ("valid", 1))
