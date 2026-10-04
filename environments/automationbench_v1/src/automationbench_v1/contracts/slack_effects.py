"""Acknowledged Slack sends; no claim about the meaning of their text.

Messages use native (channel, timestamp) identity. Later edits/deletions do not
undo an observed send, and unsupported operations cannot prove absence of sends.
"""

import hashlib
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any, Literal

from ..capture import canonical_json
from ..effect_evidence import persisted_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation, result_payload
from .base import FrozenModel
from .effects import EffectEvidence, EffectFact
from .handler_scope import outside_service
from .service_hydration import public_collection, public_service_matches

# Slack-touching handlers audited as read-only (slack search.py, users.py,
# conversation getters and their schema lookups); they close send scope only
# when the Slack service is also observed unchanged.
_SLACK_READS = frozenset({
    "slack_find_message", "slack_find_message_in_channel", "slack_get_message",
    "slack_get_message_reactions", "slack_list_channel_messages", "slack_get_channel_messages",
    "slack_get_thread_replies", "slack_find_user_by_name", "slack_find_user_by_email",
    "slack_get_conversation", "slack_get_conversation_members", "slack_list_channels",
})


class SlackEffectSource(FrozenModel):
    adapter: Literal["slack.messages@1"] = "slack.messages@1"
    kind: Literal["channel_message", "direct_message"]


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _plain(value) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _equal(left, right):
    return canonical_json(_plain(left)) == canonical_json(_plain(right))


def _text(value):
    return type(value) is str and bool(value.strip())


def _collection(world, name):
    # Sparse public state may omit a collection (or Slack): it is then the
    # schema default (empty), as public_service_matches hydrates it.
    records = public_collection(world, "slack", name)
    if not isinstance(records, (list, tuple)):
        raise TypeError("slack_collection_unavailable:" + name)
    if any(not isinstance(record, Mapping) for record in records):
        raise ValueError("slack_record_schema_unavailable")
    if name == "messages":
        identities = [(record.get("channel_id"), record.get("ts")) for record in records]
        if any(not _text(channel) or not _text(ts) for channel, ts in identities):
            raise ValueError("slack_message_identity_unavailable")
    else:
        identities = [record.get("id") for record in records]
        if any(not _text(identity) for identity in identities):
            raise ValueError("slack_record_identity_unavailable")
    if len(set(identities)) != len(identities):
        raise ValueError("slack_duplicate_native_identity")
    return records


def _scope(world):
    return {name: _collection(world, name) for name in ("channels", "users", "messages")}


def _unique(records, stages):
    # Native handlers use ordered ID/name fallbacks. A duplicate at the chosen
    # stage remains unresolved rather than accepting the handler's first match.
    for predicate in stages:
        matches = [record for record in records if predicate(record)]
        if len(matches) > 1:
            raise ValueError("slack_requested_identity_ambiguous")
        if matches:
            return matches[0]
    return None


def _channel(records, requested):
    if not _text(requested):
        raise ValueError("slack_requested_channel_unavailable")
    return _unique(records, (
        lambda record: record["id"] == requested,
        lambda record: type(record.get("name")) is str
        and record["name"].lower() == requested.lower().lstrip("#")))


def _user(records, requested):
    if not _text(requested):
        raise ValueError("slack_requested_user_unavailable")
    lower = requested.lower()
    return _unique(records, (
        lambda record: record["id"] == requested,
        lambda record: type(record.get("username")) is str
        and record["username"].lower() == lower.lstrip("@"),
        lambda record: type(record.get("email")) is str and record["email"].lower() == lower,
        lambda record: type(record.get("name")) is str and record["name"].lower() == lower,
        lambda record: type(record.get("name")) is str and lower in record["name"].lower()))


def _send(before, after, name, args, returned):
    old, new = _scope(before), _scope(after)
    if type(returned.get("success")) is not bool:
        raise ValueError("slack_result_success_unavailable")
    if returned["success"] is False:
        if not _equal(before["slack"], after["slack"]):
            raise ValueError("slack_failed_operation_changed_scope")
        return None
    if args.get("post_at") is not None:
        raise ValueError("slack_scheduled_send_unsupported")
    bot = args.get("as_bot", True)
    if type(bot) is not bool:
        raise ValueError("slack_sender_type_unavailable")
    target_user = None
    if name == "slack_send_channel_message":
        channel = _channel(old["channels"], args.get("channel") or args.get("channel_name"))
        text = args.get("text") or args.get("message") or ""
        thread = args.get("thread_ts")
        if channel is None or channel.get("is_archived") is not False:
            raise ValueError("slack_channel_not_qualified_for_send")
        if not _equal(old["channels"], new["channels"]):
            raise ValueError("slack_channel_send_rewrote_channels")
    else:
        target_user = _user(old["users"], args.get("user"))
        if target_user is None:
            raise ValueError("slack_recipient_unresolved")
        candidates = [channel for channel in old["channels"] if channel.get("channel_type") == "dm"
                      and isinstance(channel.get("member_ids"), (list, tuple))
                      and target_user["id"] in channel["member_ids"]]
        if len(candidates) > 1:
            raise ValueError("slack_dm_channel_ambiguous")
        text, thread = args.get("text"), None
        if candidates:
            channel = candidates[0]
            if not _equal(old["channels"], new["channels"]):
                raise ValueError("slack_existing_dm_rewrote_channels")
        else:
            if len(new["channels"]) != len(old["channels"]) + 1 or not _equal(new["channels"][:-1], old["channels"]):
                raise ValueError("slack_new_dm_append_unqualified")
            channel = new["channels"][-1]
            if (channel.get("name") != "dm-" + str(target_user.get("username"))
                    or channel.get("is_private") is not True):
                raise ValueError("slack_new_dm_attributes_mismatch")
        members = channel.get("member_ids")
        if (channel.get("channel_type") != "dm" or not isinstance(members, (list, tuple))
                or any(type(member) is not str for member in members) or len(set(members)) != len(members)
                or set(members) != {target_user["id"], "UAUTHUSER"}):
            raise ValueError("slack_dm_recipient_membership_unqualified")
    if type(text) is not str or thread is not None and type(thread) is not str:
        raise ValueError("slack_requested_text_or_thread_unavailable")
    if not _equal(old["users"], new["users"]):
        raise ValueError("slack_send_rewrote_users")
    if len(new["messages"]) != len(old["messages"]) + 1:
        raise ValueError("slack_message_append_unqualified")
    appended = new["messages"][-1]
    channel_id, ts = channel["id"], appended["ts"]
    if (appended.get("channel_id") != channel_id or appended.get("text") != text
            or appended.get("thread_ts") != thread or appended.get("is_deleted") is not False
            or appended.get("is_bot") is not bot
            or appended.get("user_id") != ("USLACKBOT" if bot else "UAUTHUSER")):
        raise ValueError("slack_requested_persisted_message_mismatch")
    prior = list(_plain(old["messages"]))
    if thread:
        parents = [record for record in prior if record["channel_id"] == channel_id and record["ts"] == thread]
        if parents:
            parent = parents[0]
            if type(parent.get("reply_count")) is not int:
                raise ValueError("slack_parent_reply_count_unavailable")
            parent["reply_count"] += 1
    if not _equal(prior, new["messages"][:-1]):
        raise ValueError("slack_send_rewrote_prior_messages")
    display = returned.get("message")
    if (not isinstance(display, Mapping) or returned.get("ts") != ts or returned.get("channel") != channel_id
            or display.get("ts") != ts or display.get("channel") != channel_id
            or display.get("text") != text or display.get("user") != appended["user_id"]
            or display.get("thread_ts") != thread or display.get("type") != "message"):
        raise ValueError("slack_result_persisted_message_mismatch")
    return {"channel_id": channel_id, "message_ts": ts, "text": text, "thread_ts": thread,
            "recipient_user_id": target_user["id"] if target_user else None,
            "sender_user_id": appended["user_id"], "operation": name}


def capture_slack_effects(source: Mapping, spec: SlackEffectSource) -> EffectEvidence:
    spec = SlackEffectSource.model_validate(spec.model_dump(mode="python", warnings=False))
    source_id, selector_id = _digest(source), _digest(spec.model_dump(mode="json"))
    facts, reasons = [], []
    kinds = {"slack_send_channel_message": "channel_message", "slack_send_direct_message": "direct_message"}

    def result():
        return EffectEvidence(source_id, selector_id, tuple(facts), not reasons,
                              reasons[0] if reasons else "reconciled_slack_send_inventory")

    try:
        if any(not isinstance(source.get(field), (list, tuple)) for field in ("tool_execution_events", "state_write_receipts")):
            raise ValueError("slack_execution_inventory_missing")
        index = EffectIndex(persisted_transitions(dict(source)))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
        return result()
    for occurrence in index.occurrences:
        try:
            if (occurrence.origin != "tool_server" or occurrence.before_json is None or occurrence.after_json is None
                    or occurrence.action is None or EffectIndex((occurrence,)).serial_chain().status != "qualified"):
                raise ValueError("slack_occurrence_capture_or_ack_unavailable")
            name, args = operation(occurrence.action)
            if name not in kinds and outside_service(
                name, "slack", index.world(occurrence.before_json), index.world(occurrence.after_json)
            ):
                continue
            if occurrence.action.status != "returned" or occurrence.action.error_json is not None:
                raise ValueError("slack_local_action_result_unqualified")
            if name not in kinds:
                before_slack = index.world(occurrence.before_json).get("slack")
                if name in _SLACK_READS and _equal(before_slack, index.world(occurrence.after_json).get("slack")):
                    continue
                raise ValueError("slack_operation_scope_unsupported")
            returned = result_payload(occurrence.action)
            if returned is None:
                raise ValueError("slack_result_unavailable")
            params = _send(index.world(occurrence.before_json), index.world(occurrence.after_json), name, args, returned)
            if params is not None and kinds[name] == spec.kind:
                facts.append(EffectFact(canonical_json([params["channel_id"], params["message_ts"]]),
                    occurrence.invocation_id, "tool_server", spec.kind, canonical_json(params), "qualified",
                    "acknowledged_slack_message_append", occurrence.expected_revision, occurrence.applied_revision))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            reasons.append(str(error))
            facts.append(EffectFact(None, occurrence.invocation_id, "tool_server", spec.kind, None,
                "unavailable", str(error), occurrence.expected_revision, occurrence.applied_revision))
    try:
        task = source["task_evidence"]
        initial, final = task["initial"], task["final"]
        _scope(initial)
        _scope(final)
        if task.get("complete") is not True:
            raise ValueError("slack_task_finalization_unavailable")
        expected = {item.invocation_id for item in index.occurrences if item.origin == "tool_server"}
        writes = source["state_write_receipts"]
        if len(writes) != len(expected) or {item["write_id"] for item in writes} != expected:
            raise ValueError("slack_ack_inventory_mismatch")
        if not index.occurrences:
            if not public_service_matches(initial, "slack", final["slack"]):
                raise ValueError("slack_unobserved_scope_change")
        else:
            chain = index.serial_chain()
            if chain.status != "qualified" or chain.revision_interval is None or chain.revision_interval[0] != 0:
                raise ValueError("slack_complete_revision_chain_unavailable")
            first, last = chain.ordered[0], chain.ordered[-1]
            if first.before_json is None or last.after_json is None:
                raise ValueError("slack_boundary_capture_unavailable")
            if (not public_service_matches(initial, "slack", index.world(first.before_json)["slack"])
                    or not _equal(final["slack"], index.world(last.after_json)["slack"])):
                raise ValueError("slack_initial_terminal_scope_mismatch")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    return result()


def restore_slack_effects(value: Mapping, source: Mapping, spec: SlackEffectSource) -> EffectEvidence:
    """Return freshly captured facts only after exact typed wire agreement."""
    actual = capture_slack_effects(source, spec)
    if canonical_json(_plain(value)) != canonical_json(asdict(actual)):
        raise ValueError("slack_raw_source_or_projection_mismatch")
    return actual


def validate_slack_effects(evidence: EffectEvidence, source: Mapping, spec: SlackEffectSource) -> None:
    restore_slack_effects(asdict(evidence), source, spec)
