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
           "value": {"kind": "literal", "value": value}, "mode": mode, "format": fmt}
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
