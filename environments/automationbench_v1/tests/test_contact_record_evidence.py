"""Shared Contact capability over real native mutations; no task evaluator."""

import asyncio
import copy
import json
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_batch01_manifests import recorded
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_notification_evidence import run_operations, zapier
from verifiers.v1.assessment_source import capture_trace_source

from automationbench.tools.api.impl.salesforce import salesforce_contact_update as api_update
from automationbench.tools.zapier.salesforce.contact import salesforce_contact_update
from automationbench.tools.zapier.salesforce.record import salesforce_update_record
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import RecordSource, load_contract
from automationbench_v1.contracts.credit import select_credit
from automationbench_v1.contracts.engine import evaluate_contract
from automationbench_v1.contracts.evidence import capture_records, target_record
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState


def public() -> dict[str, Any]:
    return {"salesforce": {"contacts": [{"id": "contact-1", "first_name": "Alex", "last_name": "Example",
        "email": "alex@example.com", "account_id": "account-1", "account_name": "Old Company",
        "assistant_name": "Old Assistant", "assistant_email": "old@example.com"}],
        "accounts": [{"id": "account-1", "account_name": "Old Company"}]}}


def declaration(fields=None):
    fields = fields or {"assistant_name": "New Assistant", "assistant_email": "new@example.com"}
    return load_contract(canonical_json({"schema_version": 1, "manifest_id": "manufactured-contact-update",
        "revision": "1", "public_request": "Update requested Contact fields on the existing person.",
        "sources": {"contact": {"adapter": "salesforce.record@1", "object_type": "Contact", "record_id": "contact-1"}},
        "checks": [{"check_id": "requested-contact-fields", "signal_id": "contact.updated", "role": "goal",
            "operator": "record.fields_equal@1", "source": "contact", "expected": [
                {"field": field, "value": value, "comparison": "string"} for field, value in fields.items()]}],
        "credit": [{"check": "requested-contact-fields", "policy": "verified_transition_once@1", "channel": "contact-update"}]}))


def update(fields=None, *, route="specialized", identity="contact-1", object_type="Contact"):
    fields = fields or {"assistant_name": "New Assistant", "assistant_email": "new@example.com"}
    if route == "api":
        args = {"method": "PATCH", "url": "/services/data/v60.0/sobjects/Contact/" + identity, "body": fields}
        return "api_fetch", args, lambda world: api_update(world, record_id=identity, **fields)
    if route == "generic":
        args = {"object": object_type, "recordId": identity, "fields": fields}
        return zapier("salesforce_update_record", args, lambda world: salesforce_update_record(world, **args))
    args = {"id": identity, **fields}
    return zapier("salesforce_contact_update", args, lambda world: salesforce_contact_update(world, **args))


def result(data, contract=None):
    contract = contract or declaration()
    evaluation = evaluate_contract(data, contract)
    return evaluation.results[0], select_credit(contract, evaluation)


@pytest.mark.parametrize("route,fields", [
    ("specialized", {"assistant_name": "New Assistant", "assistant_email": "new@example.com"}),
    ("generic", {"assistant_name": "New Assistant", "assistant_email": "new@example.com"}),
    ("generic", {"AssistantName": "New Assistant", "AssistantEmail": "new@example.com"}),
    ("api", {"assistant_name": "New Assistant", "assistant_email": "new@example.com"}),
    ("api", {"AssistantName": "New Assistant", "AssistantEmail": "new@example.com"}),
])
def test_real_native_contact_routes_qualify_same_two_field_conjunction(route, fields):
    data = run_operations(public(), [update(fields, route=route)])
    outcome, credit = result(data)
    assert outcome.status == "valid" and outcome.value == 1
    assert len(credit) == 1 and credit[0].occurrence == "execution-0"
    fact = capture_records(data, declaration().sources)["contact"].writes[0]
    assert fact.qualified and fact.requested_fields == ("assistant_email", "assistant_name")


@pytest.mark.parametrize("field", ["account_name", "AccountName", "Account.Name"])
def test_account_name_updates_contact_without_claiming_account_rename(field):
    data = run_operations(public(), [update({field: "New Company"}, route="generic")])
    outcome, credit = result(data, declaration({"account_name": "New Company"}))
    assert outcome.value == 1 and len(credit) == 1
    assert data["task_evidence"]["final"]["salesforce"]["accounts"][0]["account_name"] == "Old Company"
    assert data["task_evidence"]["final"]["salesforce"]["contacts"][0]["account_id"] == "account-1"


def test_account_record_rename_does_not_complete_contact_name_request():
    data = run_operations(public(), [update({"account_name": "New Company"}, route="generic", identity="account-1", object_type="Account")])
    outcome, credit = result(data, declaration({"account_name": "New Company"}))
    assert outcome.value == 0 and not credit


@pytest.mark.parametrize("scenario", ["wrong-person", "only-one-field", "split-wrong-people"])
def test_both_fields_must_hold_on_exact_same_contact(scenario):
    initial = public()
    initial["salesforce"]["contacts"].append(dict(initial["salesforce"]["contacts"][0], id="contact-2"))
    calls = [update(identity="contact-2")] if scenario == "wrong-person" else [update({"assistant_name": "New Assistant"})]
    if scenario == "split-wrong-people":
        calls.append(update({"assistant_email": "new@example.com"}, identity="contact-2"))
    outcome, credit = result(run_operations(initial, calls))
    assert outcome.value == 0 and not credit


def test_successful_split_write_allocates_to_completion():
    data = run_operations(public(), [update({"assistant_name": "New Assistant"}), update({"assistant_email": "new@example.com"})])
    outcome, credit = result(data)
    assert outcome.value == 1 and credit[0].occurrence == "execution-1"


@pytest.mark.parametrize("gap", ["ack", "stale-final", "initial-field", "initial-population", "duplicate", "wrong-type"])
def test_missing_stale_or_ambiguous_material_never_creates_progress(gap):
    data = run_operations(public(), [update()])
    if gap == "ack":
        data["state_write_receipts"] = []
    elif gap == "stale-final":
        data["task_evidence"]["final"]["salesforce"]["contacts"][0]["notes"] = "unrecorded mutation"
    elif gap == "initial-field":
        del data["task_evidence"]["initial"]["salesforce"]["contacts"][0]["assistant_email"]
    elif gap == "initial-population":
        del data["task_evidence"]["initial"]["salesforce"]["contacts"]
    elif gap == "duplicate":
        rows = data["task_evidence"]["initial"]["salesforce"]["contacts"]
        rows.append(copy.deepcopy(rows[0]))
    else:
        data["task_evidence"]["final"]["salesforce"]["contacts"][0]["assistant_email"] = True
    _, credit = result(data)
    assert not credit


def test_already_correct_break_restore_or_repeated_noop_cannot_mint_new_progress():
    initial = run_operations(public(), [update()])["task_evidence"]["final"]
    for calls in ([update()], [update({"assistant_name": "Wrong"}), update()]):
        outcome, credit = result(run_operations(initial, calls))
        assert outcome.value == 1 and not credit


def test_shared_native_publisher_keeps_scalar_and_reload_deduplicates(monkeypatch):
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declaration())
    task, episode, trace = native_fixture(run_operations(public(), [update()]))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    assert next(record for record in terminal_records(trace) if record.signal.signal_id == "contact.updated").value == 1
    assert len(penalties(trace)) == 1
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors and len(penalties(replay)) == 1


@pytest.mark.parametrize("name,identity,qualified", [
    ("simple.email_sf_contact_assistant_update", "003010", True),
    ("simple.email_sf_contact_account_update", "003005", False),
])
def test_sha_bound_actual_luna_contact_write_inventory(name, identity, qualified):
    path, raw, _, trace, data = recorded(name)
    scalar = copy.deepcopy(trace.rewards)
    trace.state = AutomationBenchState(world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state, assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    snapshot = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    material = json.loads(snapshot.source_json)
    selector = declaration().sources["contact"].model_copy(update={"record_id": identity})
    facts = capture_records(material, {"contact": selector})["contact"]
    assert any(write.qualified for write in facts.writes) is qualified
    assert trace.rewards == scalar and path.read_bytes() == raw


@pytest.mark.parametrize("raw", [True, False, "1", 1.0, float("inf"), float("nan")])
def test_raw_contact_integer_fields_reject_schema_coercion(raw):
    material = public()
    material["salesforce"]["contacts"][0]["lead_score"] = raw
    with pytest.raises(ValueError, match="raw_numeric_type_invalid"):
        target_record(material, declaration().sources["contact"])


def test_raw_bool_cannot_become_positive_numeric_contact_outcome():
    material = public()
    material["salesforce"]["contacts"][0]["lead_score"] = 0
    data = run_operations(material, [])
    data["task_evidence"]["final"]["salesforce"]["contacts"][0]["lead_score"] = True
    raw = declaration().model_dump(mode="json")
    raw["checks"][0]["expected"] = [{"field": "lead_score", "value": 1, "comparison": "number"}]
    outcome, credit = result(data, load_contract(canonical_json(raw)))
    assert outcome.status == "abstained" and outcome.value is None and not credit


@pytest.mark.parametrize("raw", [True, "1", float("inf"), float("nan")])
def test_shared_opportunity_float_rejects_raw_coercion_and_nonfinite(raw):
    selector = RecordSource(adapter="salesforce.record@1", object_type="Opportunity", record_id="opp")
    with pytest.raises(ValueError, match="raw_numeric_type_invalid"):
        target_record({"salesforce": {"opportunities": [{"id": "opp", "name": "Deal", "amount": raw}]}}, selector)


@pytest.mark.parametrize("raw", [1, 1.5])
def test_shared_opportunity_float_preserves_legitimate_json_numbers(raw):
    selector = RecordSource(adapter="salesforce.record@1", object_type="Opportunity", record_id="opp")
    assert target_record({"salesforce": {"opportunities": [{"id": "opp", "name": "Deal", "amount": raw}]}}, selector)["amount"] == raw
