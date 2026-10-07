"""Source-bound assistant text inventories, without content or policy verdicts."""

import base64
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr

from ..capture import canonical_json
from .base import FrozenModel
from .populations import Path
from .tables import Digest

# Frozen vocabulary for this retained transport revision, independent of the
# installed worker. This metadata neither supplies authored text nor proves
# task/guard compliance. Historical streams need not contain it.
_ISOLATION_FEATURES = frozenset({
    "image_generation", "browser_use", "browser_use_external",
    "browser_use_full_cdp_access", "computer_use", "in_app_browser",
    "shell_tool", "view_image", "js_repl", "apps", "plugins",
    "multi_agent", "sleep_tool", "goals",
})


class AuthoredOutputSource(FrozenModel):
    adapter: Literal["assistant.outputs@1"] = "assistant.outputs@1"
    kind: Literal["assistant_text"] = "assistant_text"


class AuthoredOutputFact(FrozenModel):
    output_id: StrictStr
    origin: Literal["native_node", "sdk_item"]
    text: StrictStr
    channel: StrictStr | None = None
    source_path: Path


class AuthoredOutputEvidence(FrozenModel):
    source_digest: Digest
    selector_digest: Digest
    trace_id: StrictStr | None
    records: tuple[AuthoredOutputFact, ...] = ()
    closed: StrictBool
    status: Literal["qualified", "partial", "unavailable"]
    reason: StrictStr


class _Node(FrozenModel):
    node: StrictInt = Field(ge=0)
    parent: StrictInt | None = Field(default=None, ge=0)
    sampled: StrictBool
    role: StrictStr
    content: Any


class _Call(FrozenModel):
    node: StrictInt | None = Field(default=None, ge=0)
    finish_reason: StrictStr | None
    failed: StrictBool


class _Projection(FrozenModel):
    schema_version: Literal[1]
    trace_id: StrictStr = Field(min_length=1)
    complete: StrictBool
    sdk_declared: StrictBool
    sdk_info: dict | None
    sdk_artifact_base64: StrictStr | None
    sdk_artifact_sha256: Digest | None
    native_nodes: tuple[_Node, ...]
    native_calls: tuple[_Call, ...]


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("authored_output_sdk_duplicate_json_key")
        result[key] = value
    return result


def _text(content):
    if content is None:
        return None
    if type(content) is str:
        return content
    if isinstance(content, list) and all(isinstance(part, dict) and set(part) == {"type", "text"}
            and part["type"] == "text" and type(part["text"]) is str for part in content):
        return "".join(part["text"] for part in content)
    raise ValueError("authored_output_native_content_unsupported")


def _native(projection):
    # Unlinked sampled text is retained raw material, not proof of closed generation.
    records, reasons = [], []
    nodes = {node.node: node for node in projection.native_nodes}
    misplaced = {node.node for index, node in enumerate(projection.native_nodes) if node.node != index}
    if misplaced:
        reasons.append("authored_output_native_original_index_mismatch")
    duplicate = {key for key, count in Counter(node.node for node in projection.native_nodes).items() if count > 1}
    if duplicate:
        reasons.append("authored_output_native_node_identity_ambiguous")
    if not projection.native_calls:
        reasons.append("authored_output_native_call_inventory_unavailable")
    calls = Counter(call.node for call in projection.native_calls if call.node is not None)
    for call in projection.native_calls:
        node = nodes.get(call.node)
        if (call.failed or call.finish_reason not in {"stop", "tool_calls"} or node is None
                or not node.sampled or node.role != "assistant" or calls[call.node] != 1 or call.node in misplaced):
            reasons.append("authored_output_native_generation_unavailable")
    for index, node in enumerate(projection.native_nodes):
        if node.parent is not None and (node.parent not in nodes or node.parent >= node.node):
            reasons.append("authored_output_native_parent_unavailable")
        if not node.sampled or node.role != "assistant" or node.node in duplicate or node.node != index:
            continue
        if calls[node.node] != 1:
            reasons.append("authored_output_native_generated_node_unlinked")
        try:
            text = _text(node.content)
            if text is not None and text != "":
                records.append(AuthoredOutputFact(output_id=f"native-node:{node.node}", origin="native_node", text=text,
                    source_path=("task_evidence", "authored_outputs", "native_nodes", index, "content")))
        except ValueError as error:
            reasons.append(str(error))
    return records, reasons


def _sdk(projection):
    records, reasons = {}, []
    text, expected = projection.sdk_artifact_base64, projection.sdk_artifact_sha256
    if text is None or expected is None:
        return [], ["authored_output_sdk_artifact_unavailable"]
    try:
        raw = base64.b64decode(text, validate=True)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("authored_output_sdk_artifact_digest_mismatch")
        payload = json.loads(raw, object_pairs_hook=_unique_object)
        if not isinstance(payload, dict):
            raise TypeError("authored_output_sdk_artifact_shape_invalid")
        canonical_json(payload)  # Reject non-finite raw artifact JSON too.
        if projection.sdk_info is not None and canonical_json(payload) != canonical_json(projection.sdk_info):
            raise ValueError("authored_output_sdk_info_artifact_mismatch")
        events = payload.get("events")
        if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
            raise ValueError("authored_output_sdk_events_unavailable")
    except (ValueError, TypeError) as error:
        return [], [str(error)]
    finished, turns, observed_turns, observed_threads, conflicts, started = [], [], set(), set(), set(), set()
    declared_threads, isolation_seen, turn_started = set(), False, False
    for index, event in enumerate(events):
        if event.get("kind") == "finished":
            finished.append(event)
            continue
        if event.get("kind") != "event":
            kind = event.get("kind")
            # These are controller-emitted startup/discovery diagnostics in the
            # native SDK worker, not additional authored-output channels.
            if kind == "thread_started":
                response = event.get("response")
                thread = response.get("thread") if isinstance(response, dict) else None
                identity = thread.get("id") if isinstance(thread, dict) else None
                if type(identity) is str and identity:
                    observed_threads.add(identity)
                    declared_threads.add(identity)
                else:
                    reasons.append("authored_output_sdk_started_thread_unavailable")
            elif kind == "turn_started":
                turn_started = True
                response = event.get("response")
                turn = response.get("turn") if isinstance(response, dict) else None
                identity = turn.get("id") if isinstance(turn, dict) else None
                if type(identity) is str and identity:
                    observed_turns.add(identity)
                else:
                    reasons.append("authored_output_sdk_started_turn_unavailable")
            elif kind == "builtin_tool_isolation":
                features = event.get("disabled_features")
                identity = event.get("thread_id")
                if (isolation_seen or turn_started or observed_turns or finished
                        or set(event) != {"kind", "revision", "scope", "thread_id", "disabled_features"}
                        or event.get("revision") != "codex-declared-tools-only@1"
                        or event.get("scope") != "loaded_thread"
                        or type(identity) is not str or not identity
                        or declared_threads != {identity}
                        or type(features) is not dict or set(features) != _ISOLATION_FEATURES
                        or any(value is not False for value in features.values())):
                    reasons.append("authored_output_sdk_isolation_metadata_unavailable")
                else:
                    observed_threads.add(identity)
                isolation_seen = True
            elif kind == "initialized":
                if not isinstance(event.get("response"), dict) or type(event.get("sdk_version")) is not str:
                    reasons.append("authored_output_sdk_initialization_unavailable")
            elif kind == "mcp_inventory":
                if event.get("scope") != "thread_bound" or not isinstance(event.get("servers"), list):
                    reasons.append("authored_output_sdk_inventory_unavailable")
            elif kind == "capability_catalog":
                if not isinstance(event.get("changes"), dict) or not isinstance(event.get("previous"), dict):
                    reasons.append("authored_output_sdk_catalog_unavailable")
            elif kind != "authenticated":
                reasons.append("authored_output_sdk_event_kind_unsupported")
            continue
        wrapped = event.get("event")
        if not isinstance(wrapped, dict):
            reasons.append("authored_output_sdk_event_shape_invalid")
            continue
        method, params = wrapped.get("method"), wrapped.get("params")
        if type(method) is not str or not isinstance(params, dict):
            reasons.append("authored_output_sdk_event_params_unavailable")
            continue
        if method not in {"turn/started", "turn/completed", "item/started", "item/completed",
                "rawResponse/completed", "thread/tokenUsage/updated", "item/agentMessage/delta", "error"}:
            reasons.append("authored_output_sdk_method_unsupported")
            continue
        if method in {"rawResponse/completed", "thread/tokenUsage/updated", "turn/started"}:
            for key, inventory in (("turnId", observed_turns), ("threadId", observed_threads)):
                if key == "turnId" and method == "turn/started":
                    turn = params.get("turn")
                    identity = turn.get("id") if isinstance(turn, dict) else None
                else:
                    identity = params.get(key)
                if type(identity) is str and identity:
                    inventory.add(identity)
                else:
                    reasons.append("authored_output_sdk_metadata_stream_unavailable")
            if method == "rawResponse/completed":
                if (type(params.get("responseId")) is not str or not params["responseId"]
                        or not isinstance(params.get("usage"), dict)
                        or not set(params) <= {"responseId", "threadId", "turnId", "usage", "usageMetadata"}):
                    reasons.append("authored_output_sdk_response_metadata_unavailable")
            elif method == "thread/tokenUsage/updated":
                if (not isinstance(params.get("tokenUsage"), dict)
                        or not set(params) <= {"threadId", "turnId", "tokenUsage"}):
                    reasons.append("authored_output_sdk_token_metadata_unavailable")
            else:
                turn = params.get("turn")
                if (not isinstance(turn, dict) or turn.get("status") != "inProgress"
                        or turn.get("error") is not None):
                    reasons.append("authored_output_sdk_turn_start_unavailable")
        if method == "turn/completed":
            turns.append(params)
        if method == "error":
            reasons.append("authored_output_sdk_stream_error")
        if method == "item/agentMessage/delta":
            identity = params.get("itemId")
            if type(identity) is str and identity:
                started.add(identity)
            else:
                reasons.append("authored_output_sdk_delta_identity_unavailable")
            for key, inventory in (("turnId", observed_turns), ("threadId", observed_threads)):
                value = params.get(key)
                if type(value) is str and value:
                    inventory.add(value)
                else:
                    reasons.append("authored_output_sdk_delta_stream_identity_unavailable")
        if method == "item/started":
            item = params.get("item")
            if not isinstance(item, dict) or type(item.get("type")) is not str:
                reasons.append("authored_output_sdk_started_item_unavailable")
            elif item["type"] == "agentMessage":
                identity = item.get("id")
                if type(identity) is str and identity:
                    started.add(identity)
                else:
                    reasons.append("authored_output_sdk_started_item_unavailable")
                for key, inventory in (("turnId", observed_turns), ("threadId", observed_threads)):
                    if key in params:
                        value = params[key]
                        if type(value) is str and value:
                            inventory.add(value)
                        else:
                            reasons.append("authored_output_sdk_started_stream_identity_unavailable")
            elif item["type"] not in {"userMessage", "reasoning", "mcpToolCall"}:
                reasons.append("authored_output_sdk_started_item_type_unsupported")
        if method != "item/completed":
            continue
        item = params.get("item")
        if not isinstance(item, dict):
            reasons.append("authored_output_sdk_completed_item_unavailable")
            continue
        if item.get("type") != "agentMessage":
            if type(item.get("type")) is not str or item["type"] not in {"userMessage", "reasoning", "mcpToolCall"}:
                reasons.append("authored_output_sdk_completed_item_type_unsupported")
            continue
        identity, body, channel = item.get("id"), item.get("text"), item.get("channel")
        if (type(identity) is not str or not identity or type(body) is not str
                or channel is not None and type(channel) is not str):
            reasons.append("authored_output_sdk_message_fields_unavailable")
            continue
        if "turnId" in params:
            if type(params["turnId"]) is not str or not params["turnId"]:
                reasons.append("authored_output_sdk_message_turn_unavailable")
            else:
                observed_turns.add(params["turnId"])
        if "threadId" in params:
            if type(params["threadId"]) is not str or not params["threadId"]:
                reasons.append("authored_output_sdk_message_thread_unavailable")
            else:
                observed_threads.add(params["threadId"])
        fact = AuthoredOutputFact(output_id=identity, origin="sdk_item", text=body, channel=channel,
            source_path=("task_evidence", "authored_outputs", "sdk_artifact_base64", "events", index, "event", "params", "item"))
        previous = records.get(identity)
        if previous is not None and (previous.text != body or previous.channel != channel):
            conflicts.add(identity)
            reasons.append("authored_output_sdk_message_identity_conflict")
        else:
            records.setdefault(identity, fact)
    if (len(finished) != 1 or finished[0].get("ok") is not True or finished[0].get("status") != "completed"):
        reasons.append("authored_output_sdk_completion_unavailable")
    else:
        ending = finished[0]
        if any(type(ending.get(key)) is not str or not ending[key] for key in ("turn_id", "thread_id")):
            reasons.append("authored_output_sdk_terminal_identity_unavailable")
        if "thread_id" in ending and (type(ending["thread_id"]) is not str or not ending["thread_id"]
                or any(thread != ending["thread_id"] for thread in observed_threads)):
            reasons.append("authored_output_sdk_thread_identity_mismatch")
        if "turn_id" in ending:
            if type(ending["turn_id"]) is not str or not ending["turn_id"]:
                reasons.append("authored_output_sdk_finished_turn_unavailable")
            elif any(turn != ending["turn_id"] for turn in observed_turns):
                reasons.append("authored_output_sdk_turn_identity_mismatch")
        for params in turns:
            turn = params.get("turn")
            if (not isinstance(turn, dict) or turn.get("status") != "completed" or turn.get("error") is not None
                    or type(turn.get("id")) is not str
                    or "turn_id" in ending and turn["id"] != ending["turn_id"]
                    or "thread_id" in ending and params.get("threadId") != ending["thread_id"]):
                reasons.append("authored_output_sdk_terminal_turn_mismatch")
            elif any(identity != turn["id"] for identity in observed_turns):
                reasons.append("authored_output_sdk_turn_identity_mismatch")
            if isinstance(turn, dict) and "items" in turn:
                items = turn["items"]
                if not isinstance(items, list):
                    reasons.append("authored_output_sdk_turn_items_unavailable")
                else:
                    for item in items:
                        if not isinstance(item, dict):
                            reasons.append("authored_output_sdk_turn_item_unavailable")
                        elif item.get("type") == "agentMessage":
                            matched = records.get(item["id"]) if type(item.get("id")) is str else None
                            if matched is None or item.get("text") != matched.text:
                                reasons.append("authored_output_sdk_turn_message_unreconciled")
                        elif type(item.get("type")) is not str or item["type"] not in {"userMessage", "reasoning", "mcpToolCall"}:
                            reasons.append("authored_output_sdk_terminal_item_type_unsupported")
        if (len(turns) != 1 or not isinstance(turns[0].get("turn"), dict)
                or turns[0]["turn"].get("id") != ending.get("turn_id")):
            reasons.append("authored_output_sdk_completed_turn_unavailable")
    if started - set(records):
        reasons.append("authored_output_sdk_incomplete_authored_item")
    return [fact for identity, fact in records.items() if identity not in conflicts], reasons


def capture_authored_outputs(source: Mapping, spec: AuthoredOutputSource) -> AuthoredOutputEvidence:
    spec = AuthoredOutputSource.model_validate(spec.model_dump(mode="python", warnings=False))
    base: dict[str, Any] = {"source_digest": _digest(source), "selector_digest": _digest(spec.model_dump(mode="json"))}
    task = source.get("task_evidence")
    raw = task.get("authored_outputs") if isinstance(task, Mapping) else None
    try:
        if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int:
            raise ValueError("authored_output_projection_unavailable")
        projection = _Projection.model_validate(raw)
    except ValueError as error:
        return AuthoredOutputEvidence(**base, trace_id=None, closed=False, status="unavailable", reason=str(error))
    records, reasons = _sdk(projection) if projection.sdk_declared else _native(projection)
    if not projection.sdk_declared and any(value is not None for value in (
            projection.sdk_info, projection.sdk_artifact_base64, projection.sdk_artifact_sha256)):
        reasons.append("authored_output_undeclared_sdk_material")
    if not projection.complete:
        reasons.append("authored_output_trace_finalization_unavailable")
    return AuthoredOutputEvidence(**base, trace_id=projection.trace_id, records=tuple(records), closed=not reasons,
        status="qualified" if not reasons else "partial" if records else "unavailable",
        reason=reasons[0] if reasons else "authored_output_inventory_closed")


def validate_authored_outputs(evidence: AuthoredOutputEvidence, source: Mapping, spec: AuthoredOutputSource) -> None:
    admitted = AuthoredOutputEvidence.model_validate(evidence.model_dump(mode="python", warnings=False))
    actual = capture_authored_outputs(source, spec)
    if canonical_json(admitted.model_dump(mode="json")) != canonical_json(actual.model_dump(mode="json")):
        raise ValueError("authored_output_raw_source_or_projection_mismatch")
