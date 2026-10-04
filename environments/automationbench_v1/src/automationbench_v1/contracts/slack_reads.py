"""Native returned Slack messages; no claim about subsequent model conditioning.

One fact per message an acknowledged read call returned (``read_message``),
identified like Slack sends by native (channel, timestamp). The returned message
must exist in the pre-call world with the same text, author and thread, so a
forged or coherently rewritten result cannot invent a read. Failed or empty
reads return nothing. Slack writes (sends, edits, reactions, channel changes)
are not reads and are skipped; calls whose static footprint excludes Slack and
which left it unchanged are skipped. Any other operation (``api_fetch``,
unknown tools) leaves the inventory incomplete.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict
from typing import Literal

from ..capture import canonical_json
from ..effect_evidence import observation_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation, result_payload
from .base import FrozenModel
from .effects import EffectEvidence, EffectFact
from .handler_scope import outside_service
from .service_hydration import public_service_matches
from .slack_effects import _channel, _collection, _equal, _plain, _text


class SlackReadSource(FrozenModel):
    adapter: Literal["slack.message_reads@1"] = "slack.message_reads@1"
    kind: Literal["read_message"] = "read_message"


# Installed Slack handlers that write state; never a read of a stored message.
_SLACK_WRITES = frozenset({
    "slack_send_channel_message", "slack_send_direct_message", "slack_edit_message", "slack_delete_message",
    "slack_add_reaction", "slack_create_channel", "slack_invite_to_channel", "slack_archive_conversation",
    "slack_set_channel_topic", "slack_set_status",
})
# Audited Slack reads whose results carry no message (users, channel metadata).
_NO_MESSAGES = frozenset({
    "slack_find_user_by_name", "slack_find_user_by_email", "slack_get_conversation",
    "slack_get_conversation_members", "slack_list_channels",
})
_SEARCHES = frozenset({"slack_find_message", "slack_find_message_in_channel"})
_GETS = {"slack_get_message": "latest", "slack_get_message_reactions": "timestamp"}
_LISTINGS = frozenset({"slack_list_channel_messages", "slack_get_channel_messages", "slack_get_thread_replies"})


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _count(result, key, messages, *, at_least=False):
    value = result.get(key)
    if type(value) is not int or (value < len(messages) if at_least else value != len(messages)):
        raise ValueError("slack_read_result_count_unavailable")


def _returned(name, args, result, channels):
    """Returned message displays plus the (channel, ts or thread) they must belong to."""
    if type(result.get("success")) is not bool:
        raise ValueError("slack_read_result_success_unavailable")
    if result["success"] is not True or "error" in result:
        return (), None, None  # an acknowledged failed read returned nothing
    if name in _NO_MESSAGES:
        return (), None, None
    channel = thread = None
    if name in _GETS:
        message = result.get("message")
        if not isinstance(message, Mapping):
            raise ValueError("slack_read_get_result_unavailable")
        requested = (args.get("channel"), args.get(_GETS[name]))
        if not _text(requested[0]) or not _text(requested[1]):
            raise ValueError("slack_read_requested_identity_unavailable")
        if (message.get("channel"), message.get("ts")) != requested:
            raise ValueError("slack_read_requested_returned_identity_mismatch")
        return (message,), requested[0], None
    messages = result.get("messages")
    if not isinstance(messages, (list, tuple)):
        raise ValueError("slack_read_messages_unavailable")  # noqa: TRY004
    if name in _SEARCHES:
        _count(result, "count", messages)
        _count(result, "total_count", messages, at_least=True)
        if name == "slack_find_message_in_channel" and args.get("channel") is not None:
            record = _channel(channels, args.get("channel"))
            if record is None:
                raise ValueError("slack_read_requested_channel_unresolved")
            channel = record["id"]
        return messages, channel, None
    if name not in _LISTINGS:
        raise ValueError("slack_read_operation_unsupported")
    record = _channel(channels, args.get("channel"))
    if record is None or result.get("channel") != record["id"]:
        raise ValueError("slack_read_requested_channel_mismatch")
    if name == "slack_get_thread_replies":
        thread = args.get("thread_ts")
        if not _text(thread) or result.get("thread_ts") != thread:
            raise ValueError("slack_read_requested_thread_mismatch")
    else:
        _count(result, "count", messages)
    return messages, record["id"], thread


def _projection(message, originals, channels, name, channel, thread):
    if not isinstance(message, Mapping):
        raise TypeError("slack_read_returned_message_unavailable")
    channel_id, ts = message.get("channel"), message.get("ts")
    if not _text(channel_id) or not _text(ts):
        raise ValueError("slack_read_returned_identity_missing")
    if channel is not None and channel_id != channel:
        raise ValueError("slack_read_returned_channel_mismatch")
    matches = [row for row in originals if row["channel_id"] == channel_id and row["ts"] == ts]
    if len(matches) != 1:
        raise ValueError("slack_read_before_identity_unavailable")
    original = matches[0]
    returned_thread = message.get("thread_ts")
    if (returned_thread if "thread_ts" in message else None) != (original.get("thread_ts") or None):
        raise ValueError("slack_read_thread_mismatch")
    if thread is not None and returned_thread != thread:
        raise ValueError("slack_read_requested_thread_mismatch")
    params = {"native_record_id": canonical_json([channel_id, ts]), "channel_id": channel_id,
              "message_ts": ts, "thread_ts": original.get("thread_ts") or None}
    for field, stored in (("text", "text"), ("user", "user_id")):
        if field not in message:
            continue
        if type(message[field]) is not str or not _equal(message[field], original.get(stored)):
            raise ValueError("slack_read_returned_field_mismatch:" + field)
        params[stored] = message[field]
    params["returned_fields"] = sorted(key for key in params if key != "native_record_id")
    # World-derived context, not returned by the call.
    names = [record.get("name") for record in channels if record["id"] == channel_id]
    if len(names) == 1 and type(names[0]) is str:
        params["channel_name"] = names[0]
    if type(original.get("is_deleted")) is bool:
        params["is_deleted"] = original["is_deleted"]
    params["operation"] = name
    return params


def capture_slack_reads(source: Mapping, spec: SlackReadSource) -> EffectEvidence:
    spec = SlackReadSource.model_validate(spec.model_dump(mode="python", warnings=False))
    source_id, selector_id = _digest(source), _digest(spec.model_dump(mode="json"))
    facts, reasons = [], []
    try:
        if any(not isinstance(source.get(field), (list, tuple)) for field in ("tool_execution_events", "state_write_receipts")):
            raise ValueError("slack_read_execution_inventory_missing")
        index = EffectIndex(observation_transitions(dict(source)))
        terminals = {}
        for event in source["tool_execution_events"]:
            receipt = json.loads(event["receipt_json"])
            if receipt["phase"] != "dispatch":
                terminals[event["source"], receipt["invocation_id"]] = receipt
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return EffectEvidence(source_id, selector_id, (), False, str(error))
    for occurrence in index.occurrences:
        try:
            if (occurrence.origin != "tool_server" or occurrence.action is None or occurrence.before_json is None
                    or occurrence.after_json is None or EffectIndex((occurrence,)).serial_chain().status != "qualified"):
                raise ValueError("slack_read_ack_or_capture_unavailable")
            action = occurrence.action
            before, after = index.world(occurrence.before_json), index.world(occurrence.after_json)
            name, args = operation(action)
            if name in _SLACK_WRITES or outside_service(name, "slack", before, after):
                continue  # writes and calls that cannot reach Slack are not reads
            receipt = terminals[occurrence.origin, occurrence.invocation_id]
            native_arguments = json.loads(receipt.get("arguments_json", "null"))
            if (receipt.get("tool_name") != action.tool_name or not isinstance(native_arguments, dict)
                    or set(native_arguments) != {"args", "kwargs"} or native_arguments["args"] != []
                    or not _equal(native_arguments["kwargs"], json.loads(action.arguments_json))):
                raise ValueError("slack_read_native_invocation_mismatch")
            if (action.status != "returned" or action.error_json is not None or action.result_json is None
                    or receipt.get("error_json") is not None or receipt.get("state_error_json") is not None
                    or receipt.get("result_json") != action.result_json):
                raise ValueError("slack_read_local_native_return_mismatch")
            if name not in _NO_MESSAGES and name not in _SEARCHES and name not in _GETS and name not in _LISTINGS:
                raise ValueError("slack_read_operation_unsupported")
            if not _equal(before.get("slack"), after.get("slack")):
                raise ValueError("slack_read_changed_scope")
            originals, channels = _collection(before, "messages"), _collection(before, "channels")
            result = result_payload(action)
            if result is None:
                raise ValueError("slack_read_result_unavailable")
            returned, channel, thread = _returned(name, args, result, channels)
            projections = [_projection(message, originals, channels, name, channel, thread) for message in returned]
            ids = [params["native_record_id"] for params in projections]
            if len(set(ids)) != len(ids):
                raise ValueError("slack_read_returned_identity_ambiguous")
            for params in projections:
                facts.append(EffectFact(_digest([occurrence.invocation_id, params["native_record_id"]]),
                    occurrence.invocation_id, "tool_server", spec.kind, canonical_json(params), "qualified",
                    "acknowledged_native_returned_slack_message", occurrence.expected_revision,
                    occurrence.applied_revision))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            reasons.append(str(error))
            facts.append(EffectFact(None, occurrence.invocation_id, "tool_server", spec.kind, None,
                "unavailable", str(error), occurrence.expected_revision, occurrence.applied_revision))
    try:
        task = source["task_evidence"]
        if task.get("complete") is not True:
            raise ValueError("slack_read_finalization_unavailable")
        _collection(task["final"], "messages")
        expected = {item.invocation_id for item in index.occurrences}
        if len(source["state_write_receipts"]) != len(expected) or {item["write_id"] for item in source["state_write_receipts"]} != expected:
            raise ValueError("slack_read_ack_inventory_mismatch")
        if index.occurrences:
            chain = index.serial_chain()
            if chain.status != "qualified" or chain.revision_interval is None or chain.revision_interval[0] != 0:
                raise ValueError("slack_read_complete_chain_unavailable")
            first, last = chain.ordered[0], chain.ordered[-1]
            if first.before_json is None or last.after_json is None:
                raise ValueError("slack_read_boundary_capture_unavailable")
            if (not public_service_matches(task["initial"], "slack", index.world(first.before_json)["slack"])
                    or not _equal(task["final"]["slack"], index.world(last.after_json)["slack"])):
                raise ValueError("slack_read_initial_terminal_scope_mismatch")
        elif not public_service_matches(task["initial"], "slack", task["final"]["slack"]):
            raise ValueError("slack_read_unobserved_scope_change")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    return EffectEvidence(source_id, selector_id, tuple(facts), not reasons,
        reasons[0] if reasons else "reconciled_slack_returned_message_inventory")


def validate_slack_reads(evidence: EffectEvidence, source: Mapping, spec: SlackReadSource) -> None:
    actual = capture_slack_reads(source, spec)
    if canonical_json(_plain(asdict(evidence))) != canonical_json(asdict(actual)):
        raise ValueError("slack_read_raw_source_or_projection_mismatch")
