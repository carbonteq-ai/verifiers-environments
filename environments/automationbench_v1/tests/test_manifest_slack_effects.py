"""Genuine Slack sends, exact native identities, and adversarial capture gaps."""

import copy
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.slack.messaging import (
    slack_delete_message,
    slack_edit_message,
    slack_send_channel_message,
    slack_send_direct_message,
)
from automationbench_v1.contracts.slack_effects import (
    SlackEffectSource,
    capture_slack_effects,
    restore_slack_effects,
    validate_slack_effects,
)


def initial():
    return {"slack": {"channels": [{"id": "Cproduct", "name": "product", "channel_type": "public"}],
        "users": [{"id": "Usarah", "name": "Sarah Jones", "username": "sarah", "email": "sarah@example.com"}],
        "messages": []}}


def channel(**changes):
    args: dict[str, Any] = {"channel": "Cproduct", "text": "Exact announcement", **changes}
    return zapier("slack_send_channel_message", args, lambda world: slack_send_channel_message(world, **args))


def dm(**changes):
    args: dict[str, Any] = {"user": "Usarah", "text": "Exact reminder", **changes}
    return zapier("slack_send_direct_message", args, lambda world: slack_send_direct_message(world, **args))


def capture(source, kind="channel_message"):
    return capture_slack_effects(source, SlackEffectSource.model_validate({"kind": kind}))


def qualified(evidence):
    return [fact for fact in evidence.effects if fact.status == "qualified"]


def params(fact):
    return json.loads(fact.params_json)


@pytest.mark.parametrize("args", [{"channel": "Cproduct"}, {"channel": "product"}, {"channel": "#PRODUCT"},
    {"channel": None, "channel_name": "#product", "text": None, "message": "Alias announcement"}])
def test_channel_id_and_native_aliases_bind_result_append_and_exact_text(args):
    source = run_operations(initial(), [channel(**args)])
    evidence = capture(source)
    assert evidence.complete and len(qualified(evidence)) == 1
    fact = qualified(evidence)[0]
    value = params(fact)
    appended = source["task_evidence"]["final"]["slack"]["messages"][-1]
    assert value["channel_id"] == "Cproduct" and value["message_ts"] == appended["ts"]
    assert fact.effect_id is not None and json.loads(fact.effect_id) == ["Cproduct", appended["ts"]]
    assert appended["id"] is None and fact.invocation_id == "execution-0"
    assert (fact.expected_revision, fact.applied_revision) == (0, 1)
    assert value["text"] == appended["text"] and value["recipient_user_id"] is None


@pytest.mark.parametrize("user", ["Usarah", "sarah", "@SARAH", "SARAH@example.com", "Sarah Jones", "Sarah"])
@pytest.mark.parametrize("existing", [False, True])
def test_direct_recipient_id_email_username_name_and_new_or_existing_dm(user, existing):
    data = initial()
    if existing:
        data["slack"]["channels"].append({"id": "Dexisting", "name": "arbitrary-label", "channel_type": "dm",
            "is_private": True, "member_ids": ["Usarah", "UAUTHUSER"]})
    source = run_operations(data, [dm(user=user)])
    evidence = capture(source, "direct_message")
    assert evidence.complete and len(qualified(evidence)) == 1
    value = params(qualified(evidence)[0])
    assert value["recipient_user_id"] == "Usarah" and value["text"] == "Exact reminder"
    assert value["channel_id"] == ("Dexisting" if existing else source["task_evidence"]["final"]["slack"]["channels"][-1]["id"])


def test_thread_reply_only_changes_native_parent_count_and_retains_exact_thread():
    data = initial()
    data["slack"]["messages"] = [{"channel_id": "Cproduct", "ts": "100.123456", "user_id": "Usarah", "text": "Parent"}]
    source = run_operations(data, [channel(thread_ts="100.123456")])
    evidence = capture(source)
    assert evidence.complete and params(qualified(evidence)[0])["thread_ts"] == "100.123456"
    assert source["task_evidence"]["final"]["slack"]["messages"][0]["reply_count"] == 1


@pytest.mark.parametrize("mode", ["channel_id", "channel_name", "user_id", "user_email", "user_name", "dm_channel", "dm_extra_recipient"])
def test_ambiguous_native_scope_cannot_be_resolved_from_first_record_or_dm_label(mode):
    data = initial()
    call, kind = channel(), "channel_message"
    if mode == "channel_id":
        data["slack"]["channels"].append(copy.deepcopy(data["slack"]["channels"][0]))
    elif mode == "channel_name":
        data["slack"]["channels"].append({"id": "Cother", "name": "product"})
        call = channel(channel="product")
    elif mode.startswith("user"):
        duplicate = copy.deepcopy(data["slack"]["users"][0])
        duplicate["id"] = "Usarah" if mode == "user_id" else "Uother"
        data["slack"]["users"].append(duplicate)
        call, kind = dm(user={"user_id": "Usarah", "user_email": "sarah@example.com", "user_name": "Sarah Jones"}[mode]), "direct_message"
    else:
        data["slack"]["channels"].append({"id": "Dexisting", "name": "dm-sarah", "channel_type": "dm",
            "member_ids": ["Usarah", "UAUTHUSER"] + (["Uother"] if mode == "dm_extra_recipient" else [])})
        if mode == "dm_channel":
            data["slack"]["channels"].append({"id": "Danother", "name": "another", "channel_type": "dm", "member_ids": ["Usarah", "UAUTHUSER"]})
        call, kind = dm(), "direct_message"
    evidence = capture(run_operations(data, [call]), kind)
    assert not evidence.complete and not qualified(evidence)


@pytest.mark.parametrize("field,value", [("ts", "wrong.123456"), ("channel", "Cother"), ("success", 1), ("message", {})])
def test_wrong_native_returned_identity_or_success_cannot_qualify_persisted_send(field, value):
    args: dict[str, Any] = {"channel": "Cproduct", "text": "Exact"}
    def handler(world):
        returned = json.loads(slack_send_channel_message(world, **args))
        returned[field] = value
        return json.dumps(returned)
    source = run_operations(initial(), [zapier("slack_send_channel_message", args, handler)])
    assert not qualified(capture(source)) and not capture(source).complete


@pytest.mark.parametrize("mutation", ["channel", "text", "sender", "prior_message", "duplicate_ts"])
def test_persisted_identity_content_and_prior_record_rewrites_reject(mutation):
    data = initial()
    data["slack"]["messages"] = [{"channel_id": "Cproduct", "ts": "100.123456", "user_id": "Usarah", "text": "Original"}]
    args: dict[str, Any] = {"channel": "Cproduct", "text": "Exact"}
    def handler(world):
        returned = slack_send_channel_message(world, **args)
        if mutation == "channel":
            world.slack.messages[-1].channel_id = "Cwrong"
        elif mutation == "text":
            world.slack.messages[-1].text = "Wrong"
        elif mutation == "sender":
            world.slack.messages[-1].user_id = "Uwrong"
        elif mutation == "prior_message":
            world.slack.messages[0].text = "Rewritten"
        else:
            world.slack.messages[-1].ts = world.slack.messages[0].ts
        return returned
    evidence = capture(run_operations(data, [zapier("slack_send_channel_message", args, handler)]))
    assert not evidence.complete and not qualified(evidence)


def test_failed_archived_channel_and_unknown_user_are_acknowledged_no_send():
    data = initial()
    data["slack"]["channels"][0]["is_archived"] = True
    source = run_operations(data, [channel(), dm(user="nobody@example.com")])
    assert capture(source).complete and not capture(source).effects
    assert capture(source, "direct_message").complete and not capture(source, "direct_message").effects


def test_missing_ack_never_qualifies_but_independent_prior_send_survives():
    source = run_operations(initial(), [channel(), channel(text="Another")])
    receipt = json.loads(source["tool_execution_events"][1]["receipt_json"])
    receipt.update(state_write_revision=None, state_persistence="unknown", state_conflict=None)
    source["tool_execution_events"][1]["receipt_json"] = json.dumps(receipt)
    source["state_write_receipts"] = source["state_write_receipts"][:1]
    evidence = capture(source)
    assert not evidence.complete and len(qualified(evidence)) == 1
    assert qualified(evidence)[0].invocation_id == "execution-0"


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("mutation", ["raised", "error"])
def test_local_action_error_or_raised_status_cannot_establish_send_or_acknowledged_no_send(failure, mutation):
    data = initial()
    data["slack"]["channels"][0]["is_archived"] = failure
    source = run_operations(data, [channel()])
    receipt = json.loads(source["tool_execution_events"][0]["receipt_json"])
    payload = json.loads(receipt["evidence_json"][0])
    if mutation == "raised":
        payload["action"]["status"] = "raised"
    else:
        payload["action"]["error_json"] = json.dumps({"type": "RuntimeError", "message": "captured failure"})
    receipt["evidence_json"][0] = json.dumps(payload)
    source["tool_execution_events"][0]["receipt_json"] = json.dumps(receipt)
    evidence = capture(source)
    assert not evidence.complete and not qualified(evidence)
    assert evidence.effects[0].reason == "slack_local_action_result_unqualified"


@pytest.mark.parametrize("mode", ["edit", "delete", "unknown", "api"])
def test_later_mutations_and_unsupported_actions_do_not_erase_observed_send(mode):
    def handler(world):
        message = world.slack.messages[-1]
        if mode == "edit":
            return slack_edit_message(world, message.channel_id, message.ts, "Edited")
        if mode == "delete":
            return slack_delete_message(world, message.channel_id, message.ts)
        return json.dumps({"success": True})
    name = {"edit": "slack_edit_message", "delete": "slack_delete_message", "unknown": "custom_mutation", "api": "api_fetch"}[mode]
    evidence = capture(run_operations(initial(), [channel(), zapier(name, {}, handler)]))
    assert not evidence.complete and len(qualified(evidence)) == 1
    assert params(qualified(evidence)[0])["text"] == "Exact announcement"


def test_repeated_sends_keep_distinct_occurrences_and_other_send_kind_is_not_rewarded():
    source = run_operations(initial(), [channel(), channel(), dm(), dm()])
    channels, directs = capture(source), capture(source, "direct_message")
    assert channels.complete and directs.complete
    assert len(qualified(channels)) == len(qualified(directs)) == 2
    assert {fact.invocation_id for fact in channels.effects} == {"execution-0", "execution-1"}
    assert len({fact.effect_id for fact in channels.effects}) == 2


def test_scheduled_argument_is_unsupported_even_when_handler_immediately_appends():
    source = run_operations(initial(), [channel(post_at="2027-01-01T00:00:00Z")])
    assert not qualified(capture(source)) and not capture(source).complete


def test_empty_explicit_inventory_is_closed_but_missing_material_is_not_empty():
    source = run_operations(initial(), [])
    assert capture(source).complete and not capture(source).effects
    # An omitted public collection is its schema default (empty): it closes
    # only when the native world agrees, never by assuming emptiness.
    del source["task_evidence"]["initial"]["slack"]["messages"]
    assert capture(source).complete
    populated = initial()
    populated["slack"]["messages"] = [{"channel_id": "Cproduct", "ts": "1.0", "user_id": "Usarah", "text": "Old"}]
    source = run_operations(populated, [])
    del source["task_evidence"]["initial"]["slack"]["messages"]
    assert not capture(source).complete
    source["task_evidence"]["initial"].pop("slack")
    assert not capture(source).complete


def test_wire_reload_and_copied_metadata_rederive_exact_raw_source():
    source = run_operations(initial(), [channel()])
    spec = SlackEffectSource(kind="channel_message")
    evidence = capture_slack_effects(source, spec)
    wire = json.loads(json.dumps(asdict(evidence)))
    assert restore_slack_effects(wire, source, spec) == evidence
    validate_slack_effects(evidence, source, spec)
    for changed in ({"complete": 1}, {"source_digest": "0" * 64}, {"selector_digest": "0" * 64}):
        with pytest.raises(ValueError, match="raw_source_or_projection"):
            validate_slack_effects(replace(evidence, **changed), source, spec)
    fact = evidence.effects[0]
    value = params(fact)
    value["recipient_user_id"] = "Uinvented"
    with pytest.raises(ValueError):
        validate_slack_effects(replace(evidence, effects=(replace(fact, params_json=json.dumps(value)),)), source, spec)
    changed = copy.deepcopy(source)
    changed["task_evidence"]["final"]["slack"]["messages"][0]["text"] = "Changed"
    with pytest.raises(ValueError):
        validate_slack_effects(evidence, changed, spec)
    with pytest.raises(ValueError):
        capture_slack_effects(source, spec.model_copy(update={"kind": True}))


@pytest.mark.parametrize("task_name,kind", [("simple.slack_dm_meeting_reminder", "direct_message"),
    ("simple.feature_launch_slack", "channel_message")])
def test_actual_sha_bound_development_luna_trace_preserves_native_send_without_claiming_text_meaning(task_name, kind):
    path = Path("/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate/cross-category-selection.json")
    if not path.exists():
        pytest.skip("selected development source index unavailable")
    selected = next(item for item in json.loads(path.read_text())["tasks"] if item["task_name"] == task_name)
    raw = Path(selected["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == selected["source_episode_sha256"]
    episode = json.loads(raw)
    trace = episode["traces"][0]
    source = {"task_evidence": {"initial": episode["task"]["data"]["initial_state"],
        "final": trace["info"]["automationbench"]["end_state"], "complete": trace["is_completed"]},
        "tool_execution_events": trace["tool_execution_events"], "state_write_receipts": trace["state_write_receipts"]}
    evidence = capture(source, kind)
    assert qualified(evidence)
    assert all(params(fact)["operation"].startswith("slack_send_") for fact in qualified(evidence))
    # Discovery and Asana calls cannot touch Slack (static handler footprint)
    # and leave it unchanged, so the send inventory now closes.
    assert evidence.complete
    assert Path(selected["source_episode_path"]).read_bytes() == raw
