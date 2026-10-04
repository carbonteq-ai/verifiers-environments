"""Round-6 engine corrections: each test reproduces one shared defect."""

import asyncio
import copy
import json
from typing import Any

import pytest
from test_manifest_guard_assessments import RAW_SIGNAL, native_fixture, penalties, terminal_records
from test_manifest_guards import create, declaration, initial
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.slack.messaging import slack_send_channel_message
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import EffectSource, TableSource, load_contract
from automationbench_v1.contracts.service_hydration import public_collection
from automationbench_v1.contracts.slack_effects import SlackEffectSource, capture_slack_effects
from automationbench_v1.contracts.slack_reads import SlackReadSource, capture_slack_reads

# --- D4: two harm guards firing on one call ---------------------------------


def _two_guard_contract(channels=("harm", "harm"), raw=False):
    first, second = declaration(), declaration()
    second["check_id"], second["signal_id"] = "prohibited-provision-again", "access.prohibited_again"
    return (dict if raw else lambda value: load_contract(canonical_json(value)))({
        "schema_version": 1,
        "manifest_id": "native-two-guard-fixture",
        "revision": "1",
        "public_request": "Do not provision processed requests or requests with manager rank below 3.",
        "sources": {
            **{
                name: TableSource(
                    path=("task_evidence", "initial", "google_sheets"),
                    spreadsheet_id="sheet", worksheet_id=name, key_fields=("Email",),
                    required_fields=("Manager", "Status") if name == "queue" else ("Rank",),
                ).model_dump(mode="json")
                for name in ("queue", "directory")
            },
            "creates": EffectSource(adapter="asana.actions@1", kind="create_task").model_dump(mode="json"),
        },
        "checks": [first, second],
        "credit": [{"check": first["check_id"], "policy": "per_effect_negative@1", "channel": channels[0]},
                   {"check": second["check_id"], "policy": "per_effect_negative@1", "channel": channels[1]}],
    })


@pytest.mark.parametrize("channels", [("harm", "harm"), ("harm", "harm_b")])
def test_two_harm_guards_on_one_call_are_both_penalised(monkeypatch, channels):
    contract = _two_guard_contract(channels)
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    task, _, trace = native_fixture(run_operations(initial(), [create()]))
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    raw = [record for record in terminal_records(trace)
           if record.signal.signal_id in {RAW_SIGNAL, "access.prohibited_again"} and record.value == 1]
    assert len(raw) == 2
    selected = penalties(trace)
    assert all(part.value == -1 and part.recipient.execution.invocation_id == "execution-0" for part in selected)
    assert {parent for part in selected for parent in part.parent_assessment_ids} == {
        record.assessment_id for record in raw}
    if channels[0] == channels[1]:
        # One contribution per call and channel: merged, earliest guard's signal.
        assert len(selected) == 1 and selected[0].signal.signal_id == RAW_SIGNAL + ".penalty"
        assert selected[0].transformation == "merged_prohibited_effect_penalty@1"
    else:
        assert sorted(part.signal.signal_id for part in selected) == [
            "access.prohibited_again.penalty", RAW_SIGNAL + ".penalty"]
    before = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == before and not trace.credit_errors


# --- Item 1: sparse public Slack state --------------------------------------


def _post(**changes):
    args: dict[str, Any] = {"channel": "Cops", "text": "Posted", **changes}
    return zapier("slack_send_channel_message", args, lambda world: slack_send_channel_message(world, **args))


def _sparse_slack_source(public_slack):
    data = {"slack": {"channels": [{"id": "Cops", "name": "ops", "channel_type": "public"}], **public_slack}}
    source = run_operations(data, [_post()])
    source["task_evidence"]["initial"] = data  # public state is sparse; native snapshots are hydrated
    return source


@pytest.mark.parametrize("public", [{}, {"users": []}, {"messages": []}])
def test_slack_scope_closes_when_public_state_omits_a_collection(public):
    evidence = capture_slack_effects(_sparse_slack_source(public),
                                     SlackEffectSource.model_validate({"kind": "channel_message"}))
    assert evidence.complete, evidence.reason
    assert [fact.status for fact in evidence.effects] == ["qualified"]


def test_slack_reads_close_when_public_state_omits_a_collection():
    evidence = capture_slack_reads(_sparse_slack_source({}), SlackReadSource.model_validate({}))
    assert evidence.complete, evidence.reason


def _nested_slack(top_level=True):
    slack: dict[str, Any] = {
        "channels": [{"id": "Cops", "name": "ops", "is_private": False, "messages": [
            {"text": "Pinned policy", "ts": "1737900000.000001", "user": "Upolicy"}]}],
        "users": [{"id": "Upolicy", "name": "Policy", "email": "policy@example.com"}]}
    if top_level:
        slack["messages"] = [{"channel_id": "Cops", "text": "Noise", "ts": "1741080009.000009", "user_id": "Unoise"}]
    return {"slack": slack}


@pytest.mark.parametrize("top_level", [True, False])
def test_slack_scope_reconciles_messages_nested_under_channels(top_level):
    data = _nested_slack(top_level)
    source = run_operations(copy.deepcopy(data), [_post()])
    source["task_evidence"]["initial"] = data
    assert capture_slack_effects(source, SlackEffectSource.model_validate({"kind": "channel_message"})).complete
    assert capture_slack_reads(source, SlackReadSource.model_validate({})).complete
    data["slack"]["channels"][0]["messages"][0]["text"] = "Different policy"
    assert not capture_slack_effects(source, SlackEffectSource.model_validate({"kind": "channel_message"})).complete


def test_omitted_public_collection_is_the_schema_default_only():
    assert public_collection({"slack": {"channels": []}}, "slack", "users") == []
    assert public_collection({}, "slack", "users") == []
    assert public_collection({"slack": {"users": "bad"}}, "slack", "users") == "bad"
    assert public_collection({"slack": []}, "slack", "users") is None
    assert public_collection({"slack": {}}, "slack", "not_a_field") is None
    native = copy.deepcopy(_sparse_slack_source({})["task_evidence"]["final"])
    assert public_collection(native, "slack", "messages") == native["slack"]["messages"]
    assert json.loads(canonical_json(native))["slack"]["users"] == []


def test_zendesk_scope_reconciles_sparse_public_state():
    from test_manifest_zendesk_effects import evidence as zendesk_evidence
    from test_manifest_zendesk_effects import initial as zendesk_initial
    from test_manifest_zendesk_effects import update

    source = run_operations(zendesk_initial(), [update()])
    source["task_evidence"]["initial"] = zendesk_initial()  # sparse public tickets
    assert zendesk_evidence(source).complete
    source["task_evidence"]["initial"]["zendesk"]["tickets"][0]["status"] = "pending"
    assert not zendesk_evidence(source).complete
    source = run_operations({}, [])
    source["task_evidence"]["initial"] = {}
    assert zendesk_evidence(source).complete


# --- Item 2: amount ranges, per-period suffixes and target magnitudes -------


def _mention(text, value, mode="amount", fmt="usd_string", sole=False):
    from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate

    raw = {"op": "mentions", "text": {"kind": "field", "path": ["effect", "body"], "domain": "string"},
           "value": {"kind": "literal", "value": value}, "mode": mode}
    if fmt:
        raw["format"] = fmt
    if sole:
        raw["sole"] = True
    return evaluate_predicate(parse_predicate(raw), {"effect": {"body": text}}).value


@pytest.mark.parametrize("text,value,sole,expected", [
    ("Grand total: $2,790.00-$3,267.00", "$3,267.00", False, True),
    ("Grand total: $2,790.00-$3,267.00", "$2,790.00", True, False),
    ("Grand total: $2,790.00–$3,267.00", "$2,790.00", True, False),
    ("Either $89/$99", "$99", False, True),
    ("Either $89/$99", "$89", True, False),
    ("Renewal amount: $89/mo", "$89", False, True),
    ("Renewal amount: $89/month", "$89", True, True),
    ("Renewal amount: $1,200/yr", "$1,200", False, True),
    ("Renewal amount: $89 per month", "$89", False, True),
    ("Due 3/5/2026", "$3", False, False),
    ("Ref 2026-05-01", "$5", False, False),
])
def test_unspaced_ranges_and_period_suffixes_read_every_amount(text, value, sole, expected):
    assert _mention(text, value, sole=sole) is expected


@pytest.mark.parametrize("text,value,mode,expected", [
    ("Plan: $299/mo", "$299/mo", "amount", True),
    ("Plan: $299 per month", "$299 per month", "amount", True),
    ("Plan: $300/mo", "$299/mo", "amount", False),
    ("Plan: $299/mo", "$299/mo", "amount_reformatted", False),   # same text is not reformatted
    ("Plan: 299 dollars", "$299/mo", "amount_reformatted", True),
    ("Valued at $4.2M", "$4.2M", "amount", True),
    ("Valued at $4,200,000", "$4.2M", "amount", True),
    ("Valued at $4,200,000", "$4.2M", "amount_reformatted", True),
    ("Valued at $4.2M", "$4.2M", "amount_reformatted", False),
    ("Valued at $4,250,000", "$4.2M", "amount", False),
    ("Valued at $4.2M", "4.2M", "amount", None),                  # bare m target stays unknown
    ("Valued at $4.2M", "$4.2M/mo extra", "amount", None),
])
def test_targets_with_period_or_magnitude_suffixes_are_readable(text, value, mode, expected):
    assert _mention(text, value, mode=mode) is expected


# --- Item 3: clock times with seconds, ISO timestamps and zone words --------


@pytest.mark.parametrize("text,value,expected", [
    ("Scheduled 14:00:00 UTC", "14:00", True),
    ("Scheduled 2026-02-10T14:00:00Z", "14:00", True),
    ("Scheduled 2026-02-10T10:00:00Z", "10:00 AM", True),    # ISO is 24-hour as written
    ("Scheduled 2026-02-10 14:00:00+00:00", "2:00 PM", True),
    ("Scheduled 2026-02-10T15:00:00Z", "14:00", False),
    ("Scheduled 2:00:00 PM", "14:00", True),
    ("Scheduled 08:00 America/Chicago", "08:00", True),
    ("Scheduled 14:00 Amsterdam time", "14:00", True),
    ("Scheduled 14:00 pmt", "14:00", True),
    ("Scheduled 9:00 pmc", "9:00 PM", None),                  # bare hour stays ambiguous
    ("Scheduled 9:00 pm", "9:00 PM", True),
    ("Scheduled 9:00 p.m.", "9:00 PM", True),
])
def test_clock_mentions_read_seconds_iso_and_ignore_am_pm_words(text, value, expected):
    assert _mention(text, value, mode="clock_time", fmt=None) is expected


@pytest.mark.parametrize("raw,minutes", [
    ("14:00:00", 840), ("2:00:30 PM", 840.5), ("2026-02-03T14:00:00Z", 840), ("2026-02-03T09:15:00-05:00", 555),
])
def test_clock_values_read_seconds_and_iso_timestamps(raw, minutes):
    from automationbench_v1.contracts.values import clock_minutes

    assert clock_minutes(raw) == minutes


# --- Item 4: collections keyed by <kind>_id (Xero) --------------------------


def _xero_initial():
    return {"xero": {"contacts": [{"contact_id": "C-1", "name": "Acme Ltd", "email_address": "ap@acme.example"}]}}


def test_xero_record_writes_use_a_single_declared_identity_field():
    from automationbench.tools.zapier.xero.contacts import xero_create_contact, xero_update_contact
    from automationbench_v1.contracts import RecordWriteSource
    from automationbench_v1.contracts.populations import InitialCollectionSource, capture_population
    from automationbench_v1.contracts.record_writes import capture_record_writes

    create_args = {"name": "Nimbus Supplies", "email_address": "billing@nimbus.example", "is_supplier": True}
    update_args = {"contact_id": "C-1", "phone": "+1 555 0100"}
    source = run_operations(_xero_initial(), [
        zapier("xero_create_contact", create_args, lambda world: xero_create_contact(world, **create_args)),
        zapier("xero_update_contact", update_args, lambda world: xero_update_contact(world, **update_args)),
    ])
    source["task_evidence"]["initial"] = _xero_initial()
    with pytest.raises(ValueError, match="identity"):
        RecordWriteSource.model_validate({"service": "xero", "collection": ["contacts"], "kind": "create"})
    with pytest.raises(ValueError, match="identity_paths_invalid"):  # a lone ["id"]-style path needs no-id schemas
        RecordWriteSource.model_validate({"service": "mailchimp", "collection": ["subscribers"], "kind": "create",
                                          "identity_paths": [["list_id"]]})
    spec = {"service": "xero", "collection": ["contacts"], "identity_paths": [["contact_id"]]}
    created = capture_record_writes(source, RecordWriteSource.model_validate({**spec, "kind": "create"}))
    updated = capture_record_writes(source, RecordWriteSource.model_validate({**spec, "kind": "update"}))
    assert created.complete and updated.complete, (created.reason, updated.reason)
    (new,) = [json.loads(fact.params_json) for fact in created.effects if fact.status == "qualified"]
    (changed,) = [json.loads(fact.params_json) for fact in updated.effects if fact.status == "qualified"]
    assert new["record"]["name"] == "Nimbus Supplies" and json.loads(new["record_id"]) == [new["record"]["contact_id"]]
    assert changed["record_id"] == '["C-1"]' and changed["changed_fields"] == ["phone"]
    population = capture_population(source, InitialCollectionSource.model_validate({
        "path": ["task_evidence", "initial", "xero", "contacts"], "identity_paths": [["contact_id"]],
        "fields": {"Name": ["name"]}, "key_fields": ["Name"]}))
    assert [row.identity[-1] for row in population.rows] == [changed["record_id"]], population.rows
    assert RecordWriteSource.model_validate({**spec, "kind": "create"}).model_dump(mode="json")["identity_paths"]
    plain = RecordWriteSource.model_validate({"service": "zoom", "collection": ["meetings"], "kind": "create"})
    assert "identity_paths" not in plain.model_dump(mode="json")


# --- Item 5 / D6: present predicate; decimal derivations vs number literals -


def _evaluate(raw, context):
    from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate

    return evaluate_predicate(parse_predicate(raw), context).value


def _present(*path):
    return {"op": "present", "value": {"kind": "field", "path": list(path)}}


@pytest.mark.parametrize("path,expected", [
    (("effect", "record", "params", "due_on"), True),
    (("effect", "record", "params", "assignee"), False),          # Asana omits unset params
    (("effect", "record", "params", "notes"), False),             # explicit null
    (("effect", "record", "signers", 0, "email"), True),
    (("effect", "record", "signers", 1, "email"), False),         # decidably absent index
    (("effect", "record", "cc", 0), False),                       # null container
    (("effect", "record", "name", "first"), None),                # scalar where a mapping is expected
    (("joined", "record_id"), True),
    (("request", "Owner"), None),                                  # missing key in a row: unread
    (("request", "Blank"), False),
    (("lookup_row", "Rank"), None),                                # unavailable record
])
def test_present_is_three_valued(path, expected):
    context = {"effect": {"record": {"name": "Task", "params": {"due_on": "2026-03-01", "notes": None},
                                     "signers": [{"email": "a@example.com"}], "cc": None}},
               "joined": {"record_id": "X"}, "request": {"Blank": None}}
    assert _evaluate(_present(*path), context) is expected


def test_present_rejects_non_field_operands_and_composes():
    with pytest.raises(ValueError):
        _evaluate({"op": "present", "value": {"kind": "literal", "value": 1}}, {})
    context = {"effect": {"record": {"params": {}}}}
    assert _evaluate({"op": "not", "arg": _present("effect", "record", "params", "assignee")}, context) is True


@pytest.mark.parametrize("op,number,expected", [("eq", 31, True), ("lte", 30, False), ("gt", 30.5, True), ("ne", 31, False)])
def test_decimal_derivations_compare_with_plain_numbers(op, number, expected):
    days = {"kind": "derived", "expression": {"kind": "days_between",
            "start": {"kind": "input", "format": "iso_date", "literal": "2026-01-01"},
            "end": {"kind": "input", "format": "iso_date", "literal": "2026-02-01"}}}
    raw = {"op": op, "left": days, "right": {"kind": "literal", "value": number}}
    assert _evaluate(raw, {}) is expected
    mirror = {"lt": "gt", "lte": "gte", "gt": "lt", "gte": "lte", "eq": "eq", "ne": "ne"}[op]
    assert _evaluate({"op": mirror, "left": {"kind": "literal", "value": number}, "right": days}, {}) is expected
    assert _evaluate({"op": op, "left": days, "right": {"kind": "literal", "value": "31"}}, {}) is None


# --- Items 6/7 (D1/D2): zero-call runs, failed no-op writes, raised calls ---


def _sheets():
    from test_manifest_sheet_effects import initial as sheet_initial
    from test_manifest_sheet_effects import spec as sheet_spec

    return sheet_initial, sheet_spec


def test_sheet_scope_closes_on_a_run_without_tool_calls():
    from automationbench_v1.contracts.sheet_effects import capture_sheet_effects

    sheet_initial, sheet_spec = _sheets()
    source = run_operations(sheet_initial(), [])
    source["task_evidence"]["initial"] = sheet_initial()
    evidence = capture_sheet_effects(source, sheet_spec("append"))
    assert evidence.complete and not evidence.effects, evidence.reason
    source["task_evidence"]["initial"]["google_sheets"]["rows"][0]["cells"]["Amount"] = "$11"
    assert not capture_sheet_effects(source, sheet_spec("append")).complete


def test_failed_sheet_write_that_changed_nothing_keeps_scope_closed():
    from automationbench.tools.zapier.google_sheets.row import google_sheets_add_row, google_sheets_update_row
    from automationbench_v1.contracts.sheet_effects import capture_sheet_effects

    sheet_initial, sheet_spec = _sheets()
    failed = zapier("google_sheets_update_row", {}, lambda world: google_sheets_update_row(world))
    args = {"spreadsheet": "sheet", "worksheet": "tab", "cells": {"Name": "New", "Amount": "$30"}}
    added = zapier("google_sheets_add_row", args, lambda world: google_sheets_add_row(world, **args))
    source = run_operations(sheet_initial(), [failed, added])
    evidence = capture_sheet_effects(source, sheet_spec("append"))
    assert evidence.complete, evidence.reason
    assert [fact.invocation_id for fact in evidence.effects if fact.status == "qualified"] == ["execution-1"]


def _with_raised_call(source, position=0):
    """Insert a dispatched call that raised before running (no write, no revision)."""
    source = copy.deepcopy(source)
    receipt = {"invocation_id": "raised-0", "phase": "raised", "tool_name": "quickbooks_create_invoice",
               "arguments_json": "{}", "error_json": canonical_json({"type": "TypeError"}),
               "state_read_revision": position, "state_persistence": "not_attempted"}
    source["tool_execution_events"].insert(position, {"source": "tool_server", "receipt_json": canonical_json(receipt)})
    return source


@pytest.mark.parametrize("position", [0, 1])
def test_a_call_that_raised_before_running_opens_no_inventory(position):
    from automationbench_v1.contracts.sheet_effects import capture_sheet_effects

    slack = _with_raised_call(_sparse_slack_source({}), position)
    evidence = capture_slack_effects(slack, SlackEffectSource.model_validate({"kind": "channel_message"}))
    assert evidence.complete and [fact.status for fact in evidence.effects] == ["qualified"], evidence.reason
    assert capture_slack_reads(slack, SlackReadSource.model_validate({})).complete
    sheet_initial, sheet_spec = _sheets()
    sheets = _with_raised_call(run_operations(sheet_initial(), []), 0)
    assert capture_sheet_effects(sheets, sheet_spec("append")).complete
    # A raised call that claims applied persistence is not exempt.
    claimed = copy.deepcopy(slack)
    for event in claimed["tool_execution_events"]:
        receipt = json.loads(event["receipt_json"])
        if receipt["invocation_id"] == "raised-0":
            receipt["state_persistence"] = "applied"
            event["receipt_json"] = canonical_json(receipt)
    assert not capture_slack_effects(claimed, SlackEffectSource.model_validate({"kind": "channel_message"})).complete


# --- Round-4 D3: admission is closed under canonical re-save ----------------


def _obligation_contract(copies):
    from test_manifest_obligation_assessments import contract as obligation_contract

    raw = obligation_contract().model_dump(mode="json")
    term = {"value": {"kind": "literal", "value": "2:00 PM"}, "mode": "clock_time"}
    label = {"value": {"kind": "literal", "value": "UTC"}, "mode": "words"}
    text = {"kind": "field", "path": ["effect", "notes"], "domain": "string"}
    raw["checks"][0]["effect_match"] = {
        "op": "any", "args": [{"op": "mentions_together", "text": text, "terms": [term, label]}] * copies}
    return raw


def test_contract_whose_canonical_resave_exceeds_the_budget_is_rejected_at_load():
    from automationbench_v1.contracts.predicates import parse_predicate

    copies = 190  # compact: under the 4096-node budget; canonical (defaults written out): over it
    raw = _obligation_contract(copies)
    parse_predicate(raw["checks"][0]["effect_match"])
    with pytest.raises(ValueError, match="contract_canonical_form_inadmissible"):
        load_contract(json.dumps(raw))
    loaded = load_contract(json.dumps(_obligation_contract(20)))
    assert load_contract(canonical_json(loaded.model_dump(mode="json"))) == loaded


def test_initial_records_read_one_key_of_a_string_keyed_mapping():
    from automationbench_v1.contracts.populations import InitialCollectionSource, capture_population

    spec = InitialCollectionSource.model_validate({
        "path": ["task_evidence", "initial", "hubspot", "contacts"],
        "fields": {"Stage": ["properties", "lifecyclestage"], "Email": ["email"]}, "key_fields": ["Email"]})
    data = {"hubspot": {"contacts": [
        {"id": "H1", "email": "a@example.com", "properties": {"lifecyclestage": "lead"}},
        {"id": "H2", "email": "b@example.com", "properties": {}}]}}
    source = run_operations(data, [])
    source["task_evidence"]["initial"] = data
    rows = capture_population(source, spec).rows
    assert [json.loads(row.cells_json).get("Stage") for row in rows] == ["lead", None]
    with pytest.raises(ValueError):
        InitialCollectionSource.model_validate({
            "path": ["task_evidence", "initial", "hubspot", "contacts"],
            "fields": {"Deep": ["properties", "a", "b"]}, "key_fields": ["Deep"]})
