"""Native lookup authenticity and lookup-before-DM archive parity."""

import asyncio
import copy
import json

import pytest
import verifiers.v1 as vf
from test_manifest_airtable_record_writes import initial as sheet_initial
from test_manifest_gmail_observations import material, mutate_return
from test_manifest_guard_assessments import native_fixture, terminal_records
from test_manifest_slack_reads import call, initial
from test_manifest_trello_reads import declaration
from test_notification_evidence import run_operations

from automationbench.tools.zapier.slack.messaging import slack_send_direct_message
from automationbench.tools.zapier.slack.users import slack_find_user_by_email
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import SlackUserReadSource, load_contract
from automationbench_v1.contracts.slack_user_reads import capture_slack_user_reads
from automationbench_v1.tools import AutomationBenchState


def lookup(email="owner@example.com"):
    return call("slack_find_user_by_email", slack_find_user_by_email, email=email)


def dm():
    return call("slack_send_direct_message", slack_send_direct_message, user="Uowner", text="Card")


def capture(source):
    return capture_slack_user_reads(source, SlackUserReadSource())


def test_exact_user_and_authenticated_miss():
    hit = capture(material([lookup()], initial()))
    assert hit.complete, hit.reason
    assert json.loads(hit.effects[0].params_json)["record"]["id"] == "Uowner"
    miss = capture(material([lookup("missing@example.com")], initial()))
    assert miss.complete, miss.reason
    assert json.loads(miss.effects[0].params_json)["found"] is False


@pytest.mark.parametrize("field,value", [("id", "Uforeign"), ("email", "foreign@example.com")])
def test_coherent_forgery(field, value):
    source = mutate_return(material([lookup()], initial()), lambda r: r["user"].update({field: value}))
    assert not capture(source).complete


@pytest.mark.parametrize("scenario,expected", [("ordered", ("valid", 1)), ("late", ("valid", 0)), ("missing", ("abstained", None))])
def test_native_order_and_reload(monkeypatch, scenario, expected):
    raw = declaration().model_dump(mode="json")
    raw["sources"]["reads"] = SlackUserReadSource().model_dump(mode="json")
    raw["sources"]["writes"] = {"adapter": "slack.messages@1", "kind": "direct_message"}
    check = raw["checks"][0]
    check["effect_match"]["args"][0] = {"op": "eq", "left": {"kind": "field", "path": ["effect", "text"]}, "right": {"kind": "literal", "value": "Card"}}
    check["effect_joins"][0]["where"] = {"op": "eq", "left": {"kind": "field", "path": ["joined", "record", "id"]}, "right": {"kind": "field", "path": ["effect", "recipient_user_id"]}}
    contract = load_contract(canonical_json(raw))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    state = sheet_initial()
    state.update(initial())
    task, _, trace = native_fixture(run_operations(state, [dm(), lookup()] if scenario == "late" else [lookup(), dm()]), missing_ack=0 if scenario == "missing" else None)
    rewards = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    findings = {(r.signal.signal_id, r.status, r.value) for r in terminal_records(trace)}
    assert ("expense.status", *expected) in findings, findings
    assert trace.rewards == rewards and not trace.assessment_errors
    wire = vf.WireEpisode.model_validate({"task": trace.task.model_dump(mode="json"), "traces": [trace.model_dump(mode="json")]})
    restored = vf.WireEpisode.model_validate_json(wire.model_dump_json()).traces[0]
    restored.state = AutomationBenchState.model_validate(trace.state.model_dump(mode="json"))
    asyncio.run(task.score(restored))
    assert {(r.signal.signal_id, r.status, r.value) for r in terminal_records(restored)} == findings
    assert restored.rewards == rewards and not restored.assessment_errors
