"""Native returned Gmail fields; no claim about subsequent model conditioning."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict
from typing import Literal

from automationbench.tools.api.fetch import _url_to_internal_path
from automationbench.tools.api.routes.gmail import route_gmail

from ..capture import canonical_json
from ..effect_evidence import world_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation, result_payload
from .base import FrozenModel
from .effects import EffectEvidence, EffectFact
from .handler_scope import outside_service
from .service_hydration import public_service_matches


class GmailObservationSource(FrozenModel):
    adapter: Literal["gmail.message_reads@1"] = "gmail.message_reads@1"
    kind: Literal["read_message"] = "read_message"


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _equal(left, right):
    return canonical_json(_plain(left)) == canonical_json(_plain(right))


def _messages(world):
    service = world.get("gmail")
    if not isinstance(service, Mapping) or not isinstance(service.get("messages"), (list, tuple)):
        raise TypeError("gmail_observation_message_scope_unavailable")
    return service["messages"]


def _aliases(message, names, *, optional=False):
    values = [message[name] for name in names if name in message]
    if not values:
        if optional:
            return False, None
        raise ValueError("gmail_observation_returned_identity_missing")
    if (any(type(value) is not str or not value for value in values)
            or any(value != values[0] for value in values[1:])):
        raise ValueError("gmail_observation_alias_identity_conflict")
    return True, values[0]


# Installed Gmail handlers that write mailbox state and never count as reading
# an original message (their results describe the write, not a stored body).
_GMAIL_WRITES = frozenset({
    "gmail_send_email", "gmail_reply_to_email", "gmail_create_draft", "gmail_create_draft_reply",
    "gmail_create_label", "gmail_add_label_to_email", "gmail_remove_label_from_email",
    "gmail_remove_thread_label", "gmail_archive_email", "gmail_mark_as_read", "gmail_mark_as_unread",
    "gmail_star_messages", "gmail_trash_email",
})


def _returned(name, args, result):
    requested = None
    if name in {"gmail_find_email", "gmail_list_emails"}:
        if result.get("success") is not True or "error" in result:
            return (), None  # an acknowledged failed search returned nothing
        messages = result.get("messages")
        if (not isinstance(messages, (list, tuple)) or type(result.get("result_count")) is not int
                or result["result_count"] != len(messages) or type(result.get("total_count")) is not int
                or result["total_count"] < len(messages)):
            raise ValueError("gmail_observation_find_count_unavailable")
        requested = args.get("id")
    elif name == "gmail_get_email_by_id":
        if result.get("success") is not True or "error" in result:
            return (), None  # an acknowledged failed get returned nothing
        if not isinstance(result.get("message"), Mapping):
            raise ValueError("gmail_observation_get_result_unavailable")
        messages, requested = (result["message"],), args.get("message_id")
        if type(requested) is not str or not requested:
            raise ValueError("gmail_observation_requested_identity_unavailable")
    elif name == "api_fetch":
        method, url = args.get("method", "GET"), args.get("url")
        if type(method) is not str or method.upper() != "GET" or type(url) is not str:
            raise ValueError("gmail_observation_operation_unsupported")
        path, router = _url_to_internal_path(url)
        match = re.fullmatch(r"gmail/v1/users/[^/]+/messages(?:/([^/]+))?", path or "")
        if router is not route_gmail or match is None:
            raise ValueError("gmail_observation_operation_unsupported")
        if "error" in result:
            return (), None
        if match[1] is not None:
            messages, requested = (result,), match[1]
        else:
            messages = result.get("messages")
            if (not isinstance(messages, (list, tuple)) or type(result.get("resultSizeEstimate")) is not int
                    or result["resultSizeEstimate"] != len(messages)):
                raise ValueError("gmail_observation_api_list_count_unavailable")
    else:
        raise ValueError("gmail_observation_operation_unsupported")
    if requested is not None and (type(requested) is not str or not requested):
        raise ValueError("gmail_observation_requested_identity_unavailable")
    return messages, requested


def _projection(message, originals, requested):
    if not isinstance(message, Mapping):
        raise TypeError("gmail_observation_returned_message_unavailable")
    _, identity = _aliases(message, ("id", "message_id"))
    if requested is not None and identity != requested:
        raise ValueError("gmail_observation_requested_returned_id_mismatch")
    matches = [row for row in originals if isinstance(row, Mapping) and row.get("id") == identity]
    if len(matches) != 1 or type(matches[0].get("id")) is not str:
        raise ValueError("gmail_observation_before_identity_unavailable")
    original = matches[0]
    params = {"native_record_id": identity, "message_id": identity}
    found, thread = _aliases(message, ("thread_id", "threadId"), optional=True)
    if found:
        if original.get("thread_id") != thread:
            raise ValueError("gmail_observation_thread_mismatch")
        params["thread_id"] = thread
    found, sender = _aliases(message, ("from", "from_"), optional=True)
    if found:
        if type(original.get("from_")) is not str or original["from_"] != sender:
            raise ValueError("gmail_observation_sender_mismatch")
        params["from_"] = sender
    for field in ("subject", "body_plain", "body_html"):
        if field not in message:
            continue
        value = message[field]
        if (value is not None and type(value) is not str or field not in original
                or not _equal(value, original[field])):
            raise ValueError("gmail_observation_returned_field_mismatch:" + field)
        params[field] = value
    params["returned_fields"] = sorted(key for key in params if key != "native_record_id")
    return params


def capture_gmail_observations(source: Mapping, spec: GmailObservationSource) -> EffectEvidence:
    spec = GmailObservationSource.model_validate(spec.model_dump(mode="python", warnings=False))
    source_id, selector_id = _digest(source), _digest(spec.model_dump(mode="json"))
    facts, reasons = [], []
    try:
        if any(not isinstance(source.get(field), (list, tuple)) for field in ("tool_execution_events", "state_write_receipts")):
            raise ValueError("gmail_observation_execution_inventory_missing")
        index = EffectIndex(world_transitions(dict(source)))
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
                raise ValueError("gmail_observation_ack_or_capture_unavailable")
            action = occurrence.action
            if outside_service(operation(action)[0], "gmail",
                               index.world(occurrence.before_json), index.world(occurrence.after_json)):
                continue
            if operation(action)[0] in _GMAIL_WRITES:
                continue  # sends, drafts, labels and read-marks are not reads
            receipt = terminals[occurrence.origin, occurrence.invocation_id]
            native_arguments = json.loads(receipt.get("arguments_json", "null"))
            local_arguments = json.loads(action.arguments_json)
            if (receipt.get("tool_name") != action.tool_name or not isinstance(native_arguments, dict)
                    or set(native_arguments) != {"args", "kwargs"} or native_arguments["args"] != []
                    or not isinstance(native_arguments["args"], list)
                    or not _equal(native_arguments["kwargs"], local_arguments)):
                raise ValueError("gmail_observation_native_invocation_mismatch")
            if (action.status != "returned" or action.error_json is not None or action.result_json is None
                    or receipt.get("error_json") is not None or receipt.get("state_error_json") is not None
                    or receipt.get("result_json") != action.result_json):
                raise ValueError("gmail_observation_local_native_return_mismatch")
            before, after = index.world(occurrence.before_json), index.world(occurrence.after_json)
            originals = _messages(before)
            if not _equal(before["gmail"], after.get("gmail")):
                raise ValueError("gmail_observation_read_changed_scope")
            name, args = operation(action)
            result = result_payload(action)
            if result is None:
                raise ValueError("gmail_observation_result_unavailable")
            returned, requested = _returned(name, args, result)
            projections = [_projection(message, originals, requested) for message in returned]
            ids = [params["native_record_id"] for params in projections]
            if len(set(ids)) != len(ids):
                raise ValueError("gmail_observation_returned_identity_ambiguous")
            for params in projections:
                facts.append(EffectFact(_digest([occurrence.invocation_id, params["native_record_id"]]),
                    occurrence.invocation_id, "tool_server", spec.kind, canonical_json(params), "qualified",
                    "acknowledged_native_returned_gmail_fields", occurrence.expected_revision, occurrence.applied_revision))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            reasons.append(str(error))
            facts.append(EffectFact(None, occurrence.invocation_id, "tool_server", spec.kind, None,
                "unavailable", str(error), occurrence.expected_revision, occurrence.applied_revision))
    try:
        task = source["task_evidence"]
        if task.get("complete") is not True:
            raise ValueError("gmail_observation_finalization_unavailable")
        _messages(task["final"])
        expected = {item.invocation_id for item in index.occurrences}
        if len(source["state_write_receipts"]) != len(expected) or {item["write_id"] for item in source["state_write_receipts"]} != expected:
            raise ValueError("gmail_observation_ack_inventory_mismatch")
        if index.occurrences:
            chain = index.serial_chain()
            if chain.status != "qualified" or chain.revision_interval is None or chain.revision_interval[0] != 0:
                raise ValueError("gmail_observation_complete_chain_unavailable")
            first, last = chain.ordered[0], chain.ordered[-1]
            if first.before_json is None or last.after_json is None:
                raise ValueError("gmail_observation_boundary_capture_unavailable")
            if (not public_service_matches(task["initial"], "gmail", index.world(first.before_json)["gmail"])
                    or not _equal(task["final"]["gmail"], index.world(last.after_json)["gmail"])):
                raise ValueError("gmail_observation_initial_terminal_scope_mismatch")
        elif not public_service_matches(task["initial"], "gmail", task["final"]["gmail"]):
            raise ValueError("gmail_observation_unobserved_scope_change")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    return EffectEvidence(source_id, selector_id, tuple(facts), not reasons,
        reasons[0] if reasons else "reconciled_gmail_returned_message_inventory")


def validate_gmail_observations(evidence: EffectEvidence, source: Mapping, spec: GmailObservationSource) -> None:
    actual = capture_gmail_observations(source, spec)
    if canonical_json(asdict(evidence)) != canonical_json(asdict(actual)):
        raise ValueError("gmail_observation_raw_source_or_projection_mismatch")
