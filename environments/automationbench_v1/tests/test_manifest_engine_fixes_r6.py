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
