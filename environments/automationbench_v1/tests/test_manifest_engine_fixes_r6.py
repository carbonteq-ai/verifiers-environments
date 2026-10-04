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


def _two_guard_contract(channels=("harm", "harm")):
    first, second = declaration(), declaration()
    second["check_id"], second["signal_id"] = "prohibited-provision-again", "access.prohibited_again"
    return load_contract(canonical_json({
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
    }))


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
