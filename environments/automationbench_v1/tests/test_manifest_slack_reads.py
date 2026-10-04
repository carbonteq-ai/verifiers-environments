"""Genuine Slack read handlers: returned messages as read evidence and join sources."""

import asyncio
import copy
import json
from dataclasses import asdict
from typing import Any

import pytest
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.gmail.message import gmail_send_email
from automationbench.tools.zapier.slack.messaging import (
    slack_add_reaction,
    slack_send_channel_message,
)
from automationbench.tools.zapier.slack.search import (
    slack_find_message,
    slack_find_message_in_channel,
    slack_get_channel_messages,
    slack_get_message,
    slack_get_message_reactions,
    slack_get_thread_replies,
    slack_list_channel_messages,
)
from automationbench.tools.zapier.slack.users import slack_find_user_by_email
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import SlackReadSource, load_contract
from automationbench_v1.contracts.slack_reads import capture_slack_reads, validate_slack_reads

GUIDE = ("Cguidelines", "1767000000.000100")
OTHER = ("Crandom", "1767000100.000200")


def initial():
    return {"slack": {
        "channels": [{"id": "Cguidelines", "name": "brand-guidelines", "channel_type": "public"},
                     {"id": "Crandom", "name": "random", "channel_type": "public"},
                     {"id": "Cmarketing", "name": "marketing", "channel_type": "public"}],
        "users": [{"id": "Uowner", "name": "Brand Owner", "username": "owner", "email": "owner@example.com"}],
        "messages": [
            {"channel_id": GUIDE[0], "ts": GUIDE[1], "user_id": "Uowner", "text": "Guidelines: use sentence case"},
            {"channel_id": GUIDE[0], "ts": "1767000050.000300", "user_id": "Uowner", "text": "Ack",
             "thread_ts": GUIDE[1]},
            {"channel_id": OTHER[0], "ts": OTHER[1], "user_id": "Uowner", "text": "Lunch at noon"}]}}


def call(name, function, **args: Any):
    return zapier(name, args, lambda world: function(world, **args))


READS = {
    "find": lambda: call("slack_find_message", slack_find_message, query="Guidelines"),
    "find_in_channel": lambda: call("slack_find_message_in_channel", slack_find_message_in_channel,
                                    query="sentence", channel="#brand-guidelines"),
    "get": lambda: call("slack_get_message", slack_get_message, channel=GUIDE[0], latest=GUIDE[1]),
    "reactions": lambda: call("slack_get_message_reactions", slack_get_message_reactions,
                              channel=GUIDE[0], timestamp=GUIDE[1]),
    "list": lambda: call("slack_list_channel_messages", slack_list_channel_messages, channel="brand-guidelines"),
    "history": lambda: call("slack_get_channel_messages", slack_get_channel_messages, channel=GUIDE[0]),
}


def post(text="Launch post in sentence case"):
    return call("slack_send_channel_message", slack_send_channel_message, channel="Cmarketing", text=text)


def read_other():
    return call("slack_list_channel_messages", slack_list_channel_messages, channel="random")


def material(calls, world=None):
    source = run_operations(world or initial(), calls)
    _, _, trace = native_fixture(source)
    source["tool_execution_events"] = [{"source": "tool_server", "receipt_json": event.receipt_json}
                                       for event in trace.tool_execution_events]
    source["state_write_receipts"] = [receipt.model_dump(mode="json") for receipt in trace.state_write_receipts]
    return source


def evidence(source):
    return capture_slack_reads(source, SlackReadSource())


def positive(value):
    return [json.loads(fact.params_json) for fact in value.effects if fact.status == "qualified"]


@pytest.mark.parametrize("name", sorted(READS))
def test_every_message_read_handler_returns_the_stored_guideline(name):
    value = evidence(material([READS[name]()]))
    assert value.complete, value.reason
    facts = [params for params in positive(value) if params["message_ts"] == GUIDE[1]]
    assert len(facts) == 1
    params = facts[0]
    assert params["native_record_id"] == canonical_json(list(GUIDE))
    assert params["channel_id"] == GUIDE[0] and params["channel_name"] == "brand-guidelines"
    assert params["text"] == "Guidelines: use sentence case" and params["user_id"] == "Uowner"
    assert "text" in params["returned_fields"] and params["thread_ts"] is None


def test_channel_history_omits_thread_replies_but_thread_read_returns_them():
    listed = positive(evidence(material([READS["list"]()])))
    assert [params["message_ts"] for params in listed] == [GUIDE[1]]
    replies = call("slack_get_thread_replies", slack_get_thread_replies, channel=GUIDE[0], thread_ts=GUIDE[1])
    value = evidence(material([replies]))
    assert value.complete and [p["thread_ts"] for p in positive(value)] == [GUIDE[1]]


@pytest.mark.parametrize("calls", [
    [call("slack_list_channel_messages", slack_list_channel_messages, channel="missing")],
    [call("slack_get_message", slack_get_message, channel=GUIDE[0], latest="1.0")],
    [call("slack_find_message", slack_find_message, query="no such words")],
    [call("slack_find_user_by_email", slack_find_user_by_email, email="owner@example.com")],
])
def test_failed_empty_and_non_message_reads_return_nothing(calls):
    value = evidence(material(calls))
    assert value.complete and positive(value) == []


def test_writes_and_other_services_are_not_reads_and_keep_scope_closed():
    send = call("gmail_send_email", gmail_send_email, to="a@example.com", subject="s", body="b")
    react = call("slack_add_reaction", slack_add_reaction, channel=GUIDE[0], timestamp=GUIDE[1], emoji="eyes")
    value = evidence(material([post(), send, react]))
    assert value.complete and value.effects == ()


def test_rewritten_result_cannot_invent_a_read():
    source = material([READS["get"]()])
    tampered = copy.deepcopy(source)
    for event in tampered["tool_execution_events"]:
        receipt = json.loads(event["receipt_json"])
        if receipt["phase"] != "returned":
            continue
        capture = json.loads(receipt["evidence_json"][0])
        result = json.loads(json.loads(capture["action"]["result_json"]))
        result["message"]["text"] = "Guidelines: anything goes"
        encoded = canonical_json(json.dumps(result))
        capture["action"]["result_json"] = receipt["result_json"] = encoded
        receipt["evidence_json"][0] = canonical_json(capture)
        event["receipt_json"] = canonical_json(receipt)
    value = evidence(tampered)
    assert not value.complete and positive(value) == []
    assert value.effects[0].reason == "slack_read_returned_field_mismatch:text"


def test_missing_ack_leaves_the_inventory_incomplete_and_validation_is_exact():
    source = material([READS["get"]()])
    validate_slack_reads(evidence(source), source, SlackReadSource())
    broken = copy.deepcopy(source)
    broken["state_write_receipts"] = []
    assert not evidence(broken).complete
    forged = evidence(source)
    with pytest.raises(ValueError, match="slack_read_raw_source_or_projection_mismatch"):
        validate_slack_reads(type(forged)(**{**asdict(forged), "complete": False}), source, SlackReadSource())


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def literal(value):
    return {"kind": "literal", "value": value}


POPULATION = {"adapter": "initial.records@1", "path": ["task_evidence", "initial", "slack", "messages"],
              "identity_paths": [["channel_id"], ["ts"]],
              "fields": {"Channel": ["channel_id"], "Ts": ["ts"], "Text": ["text"]},
              "key_fields": ["Channel", "Ts"]}
GUIDELINE_ROW = {"op": "all", "args": [{"op": "eq", "left": field("request", "Channel"), "right": literal(GUIDE[0])},
                                       {"op": "eq", "left": field("request", "Ts"), "right": literal(GUIDE[1])}]}


def post_contract(timing="before"):
    check = {"check_id": "post-after-guidelines", "signal_id": "marketing.guided_post", "role": "goal",
             "operator": "effects.required_when@1", "semantics": "new_occurrence",
             "population": "messages", "source": "posts", "required_when": GUIDELINE_ROW,
             "effect_match": {"op": "all", "args": [
                 {"op": "eq", "left": field("join", "guide"), "right": literal("matched")},
                 {"op": "eq", "left": field("effect", "channel_id"), "right": literal("Cmarketing")}]},
             "effect_joins": [{"alias": "guide", "source": "reads", "timing": timing, "match": "any",
                               "where": {"op": "eq", "left": field("joined", "native_record_id"),
                                         "right": field("candidate", "native_record_id")}}]}
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "slack-read-join", "revision": "1",
        "public_request": "Read the pinned brand guidelines, then post the launch in #marketing.",
        "sources": {"messages": POPULATION, "reads": {"adapter": "slack.message_reads@1", "kind": "read_message"},
                    "posts": {"adapter": "slack.messages@1", "kind": "channel_message"}},
        "checks": [check]}))


def read_contract():
    check = {"check_id": "read-guidelines", "signal_id": "marketing.read_guidelines", "role": "goal",
             "operator": "effects.required_when@1", "semantics": "new_occurrence",
             "population": "messages", "source": "reads", "required_when": GUIDELINE_ROW,
             "effect_match": {"op": "eq", "left": field("effect", "native_record_id"),
                              "right": field("candidate", "native_record_id")}}
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "slack-read-source", "revision": "1",
        "public_request": "Read the pinned brand guidelines.",
        "sources": {"messages": POPULATION, "reads": {"adapter": "slack.message_reads@1"}},
        "checks": [check]}))


def outcome(monkeypatch, declared, calls, missing_ack=None):
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, _, trace = native_fixture(run_operations(initial(), calls), missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    findings = []
    for batch in trace.assessment_batches:
        for receipt in batch.run.execution_evidence:
            body = json.loads(receipt.payload_json)
            if body.get("kind") == "finding" and body["status"] != "inapplicable":
                findings.append((body.get("instance_key"), body["status"], body["value"]))
    assert findings and len({item[1:] for item in findings}) == 1, findings
    return findings[0][1:]


def test_read_then_post_is_witnessed(monkeypatch):
    assert outcome(monkeypatch, post_contract(), [READS["get"](), post()]) == ("valid", 1)
    assert outcome(monkeypatch, post_contract(), [READS["find"](), post()]) == ("valid", 1)


def test_post_then_read_is_a_known_zero_with_before_timing(monkeypatch):
    assert outcome(monkeypatch, post_contract(), [post(), READS["list"]()]) == ("valid", 0)
    assert outcome(monkeypatch, post_contract("any"), [post(), READS["list"]()]) == ("valid", 1)


def test_reading_another_channel_is_a_known_zero(monkeypatch):
    assert outcome(monkeypatch, post_contract(), [read_other(), post()]) == ("valid", 0)


def test_missing_ack_leaves_the_post_unknown(monkeypatch):
    assert outcome(monkeypatch, post_contract(), [READS["get"](), post()], missing_ack=0)[0] == "abstained"


def test_reads_are_an_obligation_source(monkeypatch):
    assert outcome(monkeypatch, read_contract(), [READS["history"]()]) == ("valid", 1)
    assert outcome(monkeypatch, read_contract(), [read_other()]) == ("valid", 0)
    assert outcome(monkeypatch, read_contract(), [READS["get"]()], missing_ack=0)[0] == "abstained"


def test_slack_reads_cannot_be_a_guard_source_and_defaults_are_stable():
    raw = post_contract().model_dump(mode="json")
    assert raw["sources"]["reads"] == {"adapter": "slack.message_reads@1", "kind": "read_message"}
    raw["checks"] = [{"check_id": "g", "signal_id": "g", "role": "harm", "operator": "effects.prohibited_when@1",
                      "population": "messages", "source": "reads", "prohibited_when": GUIDELINE_ROW,
                      "effect_match": GUIDELINE_ROW}]
    with pytest.raises(ValidationError, match="slack_read_requires_obligation_check"):
        load_contract(canonical_json(raw))


def test_every_installed_slack_handler_is_classified_for_send_and_read_scope():
    from automationbench_v1.contracts import slack_reads
    from automationbench_v1.contracts.handler_scope import handler_footprints
    from automationbench_v1.contracts.slack_effects import _SLACK_READS

    slack = {name for name, footprint in handler_footprints().items() if footprint and "slack" in footprint}
    reads = (slack_reads._NO_MESSAGES | slack_reads._SEARCHES | set(slack_reads._GETS) | slack_reads._LISTINGS)
    assert reads == set(_SLACK_READS) and not reads & slack_reads._SLACK_WRITES
    assert slack == reads | slack_reads._SLACK_WRITES


def test_listing_channels_before_a_post_keeps_send_scope_closed():
    from automationbench.tools.zapier.slack.channels import slack_list_channels
    from automationbench_v1.contracts.slack_effects import SlackEffectSource, capture_slack_effects

    source = material([call("slack_list_channels", slack_list_channels), post()])
    sends = capture_slack_effects(source, SlackEffectSource(kind="channel_message"))
    assert sends.complete and len([fact for fact in sends.effects if fact.status == "qualified"]) == 1
    reads = evidence(source)
    assert reads.complete and positive(reads) == []
