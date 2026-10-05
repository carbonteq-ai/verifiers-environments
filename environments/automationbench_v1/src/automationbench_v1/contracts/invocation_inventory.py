"""Source-bound call coverage, never SDK/native attribution or temporal order.

Unique equal populations establish coverage only. Repeated indistinguishable
calls remain ambiguous; their observed native facts are retained independently.
"""

import base64
import hashlib
import inspect
import json
from collections import Counter
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import StrictBool, StrictInt, StrictStr
from verifiers.v1.assessments import SourceSnapshot
from verifiers.v1.interception.tool import ToolHookRequest
from verifiers.v1.mcp.execution import ToolServerReceipt
from verifiers.v1.trace import StateWriteReceipt, ToolExecutionEvent, ToolServerExecutionEvent

from ..capture import SnapshotStore, canonical_json, raw_action_envelopes
from ..effect_evidence import world_transitions
from ..effect_index import EffectIndex
from ..native_invocation_source import build_native_invocation_material
from ..notification_evidence import operation
from ..tools import AutomationBenchToolset
from .authored_outputs import AuthoredOutputSource, capture_authored_outputs
from .base import FrozenModel
from .tables import Digest


class InvocationEntry(FrozenModel):
    invocation_id: StrictStr
    origin: StrictStr
    outer_tool: StrictStr | None = None
    outer_arguments_json: StrictStr | None = None
    operation: StrictStr | None = None
    operation_arguments_json: StrictStr | None = None
    action_json: StrictStr | None = None
    before_json: StrictStr | None = None
    after_json: StrictStr | None = None
    result_json: StrictStr | None = None
    expected_revision: StrictInt | None = None
    applied_revision: StrictInt | None = None
    status: Literal["qualified", "unavailable"]
    reason: StrictStr


class SDKCoveragePair(FrozenModel):
    sdk_item_id: StrictStr
    native_invocation_id: StrictStr


class NativeCoveragePair(FrozenModel):
    native_invocation_id: StrictStr
    parent_execution_id: StrictStr
    node_index: StrictInt
    emitted_call_index: StrictInt
    transport_attempt_index: StrictInt


class InvocationInventory(FrozenModel):
    source_digest: Digest
    entries: tuple[InvocationEntry, ...] = ()
    closed: StrictBool
    reason: StrictStr
    sdk_coverage_pairs: tuple[SDKCoveragePair, ...] = ()
    native_coverage_pairs: tuple[NativeCoveragePair, ...] = ()
    native_snapshot_id: StrictStr | None = None


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _arguments(text):
    value = json.loads(text)
    if (
        not isinstance(value, dict)
        or set(value) != {"args", "kwargs"}
        or value["args"] != []
        or not isinstance(value["kwargs"], dict)
    ):
        raise ValueError("invocation_arguments_envelope_unsupported")
    return value["kwargs"]


def _entry(occurrence, receipts):
    action = occurrence.action
    values: dict[str, Any] = {
        "invocation_id": occurrence.invocation_id,
        "origin": occurrence.origin,
        "before_json": occurrence.before_json,
        "after_json": occurrence.after_json,
        "expected_revision": occurrence.expected_revision,
        "applied_revision": occurrence.applied_revision,
        "action_json": action.model_dump_json() if action is not None else None,
    }
    try:
        if (
            occurrence.evidence_status != "acknowledged"
            or action is None
            or occurrence.origin != "tool_server"
        ):
            raise ValueError(occurrence.reason)
        if (
            action.status != "returned"
            or action.error_json is not None
            or action.result_json is None
        ):
            raise ValueError("invocation_local_terminal_unavailable")
        if EffectIndex((occurrence,)).serial_chain().status != "qualified":
            raise ValueError("invocation_revision_unqualified")
        phases = receipts.get((occurrence.origin, occurrence.invocation_id), ())
        if len(phases) != 2 or [receipt.phase for receipt in phases] != ["dispatch", "returned"]:
            raise ValueError("invocation_dispatch_terminal_inventory_unavailable")
        dispatch, terminal = phases
        if (
            dispatch.tool_name != terminal.tool_name
            or dispatch.arguments_json != terminal.arguments_json
            or dispatch.state_read_revision != terminal.state_read_revision
            or terminal.tool_name != action.tool_name
            or terminal.error_json is not None
            or terminal.state_error_json is not None
            or terminal.result_json != action.result_json
        ):
            raise ValueError("invocation_native_local_terminal_mismatch")
        args = _arguments(terminal.arguments_json)
        if canonical_json(args) != canonical_json(json.loads(action.arguments_json)):
            raise ValueError("invocation_native_local_arguments_mismatch")
        name, inner = operation(action)
        values.update(
            outer_tool=terminal.tool_name,
            outer_arguments_json=canonical_json(args),
            operation=name,
            operation_arguments_json=canonical_json(_plain(inner)),
            result_json=terminal.result_json,
        )
        return InvocationEntry(**values, status="qualified", reason="qualified_native_invocation")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return InvocationEntry(**values, status="unavailable", reason=str(error))


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _sdk_pairs(source, entries):
    projection = source.get("task_evidence", {}).get("authored_outputs")
    if not isinstance(projection, dict) or projection.get("sdk_declared") is not True:
        return (), ["invocation_model_inventory_unavailable"]
    outputs = capture_authored_outputs(source, AuthoredOutputSource())
    if not outputs.closed:
        return (), ["invocation_sdk_lifecycle_unavailable:" + outputs.reason]
    payload = json.loads(base64.b64decode(projection["sdk_artifact_base64"], validate=True))
    reasons, inventories, completed, started = [], [], {}, {}
    for event in payload["events"]:
        if event.get("kind") == "mcp_inventory":
            inventories.append(event)
        if event.get("kind") != "event":
            continue
        wrapped = event["event"]
        if wrapped["method"] not in {"item/started", "item/completed"}:
            continue
        item = wrapped["params"].get("item")
        if not isinstance(item, dict) or item.get("type") != "mcpToolCall":
            continue
        ending = next(event for event in payload["events"] if event.get("kind") == "finished")
        if (
            wrapped["params"].get("threadId") != ending["thread_id"]
            or wrapped["params"].get("turnId") != ending["turn_id"]
        ):
            reasons.append("invocation_sdk_call_stream_mismatch")
        identity = item.get("id")
        if type(identity) is not str or not identity:
            reasons.append("invocation_sdk_call_identity_unavailable")
            continue
        if wrapped["method"] == "item/started":
            if identity in started and canonical_json(started[identity]) != canonical_json(item):
                reasons.append("invocation_sdk_started_call_conflict")
            started[identity] = item
        elif identity in completed and canonical_json(completed[identity]) != canonical_json(item):
            reasons.append("invocation_sdk_call_identity_conflict")
        else:
            completed[identity] = item
    if set(started) - set(completed):
        reasons.append("invocation_sdk_call_unfinished")
    for identity in set(started) & set(completed):
        if any(
            canonical_json(started[identity].get(key))
            != canonical_json(completed[identity].get(key))
            for key in ("server", "tool", "arguments")
        ):
            reasons.append("invocation_sdk_started_completed_mismatch")
        if (
            started[identity].get("status") != "inProgress"
            or started[identity].get("error") is not None
        ):
            reasons.append("invocation_sdk_started_call_unqualified")
    if len(inventories) != 1:
        return (), [*reasons, "invocation_sdk_server_inventory_unavailable"]
    servers = inventories[0].get("servers")
    if not isinstance(servers, list):
        return (), [*reasons, "invocation_sdk_server_inventory_unavailable"]
    aliases, approved = payload.get("server_aliases"), payload.get("approved_mcp_tools")
    namespace = AutomationBenchToolset.TOOL_PREFIX or ""
    expected_server = aliases.get(namespace) if isinstance(aliases, dict) else None
    approved_tools = (
        approved.get(expected_server)
        if isinstance(approved, dict) and type(expected_server) is str
        else None
    )
    if (
        type(expected_server) is not str
        or not expected_server
        or not isinstance(approved_tools, list)
        or any(
            type(tool) is not str or tool not in {"search_tools", "execute_tool"}
            for tool in approved_tools
        )
        or len(set(approved_tools)) != len(approved_tools)
    ):
        return (), [*reasons, "invocation_sdk_native_server_authority_unavailable"]
    declared = {}
    for server in servers:
        if (
            not isinstance(server, dict)
            or type(server.get("name")) is not str
            or not server["name"]
            or server.get("runtime_status") != "connected"
            or not isinstance(server.get("tool_names"), list)
            or any(type(name) is not str or not name for name in server["tool_names"])
            or len(set(server["tool_names"])) != len(server["tool_names"])
            or server["name"] in declared
            or server["name"] != expected_server
            or set(server["tool_names"]) != set(approved_tools)
        ):
            reasons.append("invocation_sdk_server_declaration_unavailable")
        else:
            declared[server["name"]] = set(server["tool_names"])
    native = {}
    for entry in entries:
        if entry.status == "qualified":
            key = canonical_json(
                [
                    entry.outer_tool,
                    json.loads(entry.outer_arguments_json),
                    json.loads(entry.result_json),
                ]
            )
            native.setdefault(key, []).append(entry.invocation_id)
    sdk = {}
    for identity, item in completed.items():
        try:
            if (
                item.get("status") != "completed"
                or item.get("error") is not None
                or type(item.get("server")) is not str
                or type(item.get("tool")) is not str
                or item["tool"] not in declared.get(item["server"], set())
                or not isinstance(item.get("arguments"), dict)
            ):
                raise ValueError("invocation_sdk_call_declaration_unqualified")
            args = dict(item["arguments"])
            if item["tool"] == "search_tools" and "top_k" not in args:
                default = (
                    inspect.signature(AutomationBenchToolset.search_tools)
                    .parameters["top_k"]
                    .default
                )
                if type(default) is not int or default != 5:
                    raise ValueError("invocation_installed_default_contract_changed")
                args["top_k"] = default
            if item["tool"] == "search_tools" and (
                type(args.get("query")) is not str or type(args.get("top_k")) is not int
            ):
                raise ValueError("invocation_sdk_search_arguments_unqualified")
            returned = item.get("result")
            content = returned.get("content") if isinstance(returned, dict) else None
            if (
                not isinstance(content, list)
                or len(content) != 1
                or not isinstance(content[0], dict)
                or content[0].get("type") != "text"
                or type(content[0].get("text")) is not str
                or returned.get("isError", False) is not False
            ):
                raise ValueError("invocation_sdk_result_shape_unsupported")
            structured = returned.get("structuredContent")
            if structured is not None and (
                not isinstance(structured, dict)
                or set(structured) != {"result"}
                or canonical_json(structured["result"]) != canonical_json(content[0]["text"])
            ):
                raise ValueError("invocation_sdk_result_channels_conflict")
            key = canonical_json([item["tool"], args, content[0]["text"]])
            sdk.setdefault(key, []).append(identity)
        except (ValueError, TypeError, KeyError) as error:
            reasons.append(str(error))
    pairs = []
    for key in set(native) | set(sdk):
        native_ids, sdk_ids = native.get(key, ()), sdk.get(key, ())
        if len(native_ids) == 1 and len(sdk_ids) == 1:
            pairs.append(
                SDKCoveragePair(sdk_item_id=sdk_ids[0], native_invocation_id=native_ids[0])
            )
        else:
            reasons.append("invocation_sdk_native_population_unmatched_or_ambiguous")
    return tuple(sorted(pairs, key=lambda pair: pair.native_invocation_id)), reasons


def _selected_material(raw):
    return {
        "task_evidence": raw.get("task_evidence"),
        "tool_execution_events": raw.get("tool_execution_events", []),
        "state_write_receipts": raw.get("state_write_receipts", []),
    }


def _native_pairs(source, entries, native_source):
    """Reconcile explicit host links, never result strings or provider IDs alone."""
    if native_source is None:
        return (), ["invocation_model_inventory_unavailable"], None
    native_source = SourceSnapshot.model_validate(
        native_source.model_dump(mode="python", warnings=False)
    )
    raw = json.loads(native_source.source_json)
    if canonical_json(_selected_material(raw)) != canonical_json(_selected_material(source)):
        raise ValueError("invocation_native_selected_source_mismatch")
    material = build_native_invocation_material(native_source)
    reasons, groups, pairs = [], {}, []
    if material.sdk_declared is not False or material.producer_complete is not True:
        reasons.append("invocation_native_producer_basis_unavailable")
    if material.terminal_inventory_status != "observed":
        reasons.append(material.terminal_inventory_reason)
    authored = capture_authored_outputs(source, AuthoredOutputSource())
    if not authored.closed:
        reasons.append("invocation_native_generation_inventory_unavailable:" + authored.reason)
    if any(node.status != "observed" for node in material.nodes):
        reasons.append("invocation_original_node_inventory_unavailable")
    expected = {
        (node.node_index, call.emitted_call_index): call
        for node in material.nodes
        if node.sampled is True and node.role == "assistant"
        for call in node.tool_calls
    }
    for event in source["tool_execution_events"]:
        if event.get("source") in {"harness", "interceptor"}:
            admitted = ToolExecutionEvent.model_validate(event)
            groups.setdefault(admitted.execution_id, []).append(admitted)
    coverage = {}
    for identity, events in groups.items():
        first = events[0]
        coordinates = (first.node_index, first.emitted_call_index)
        valid = (
            coordinates in expected
            and [event.phase for event in events] == ["before", "dispatch", "after"]
            and [event.event_index for event in events] == [0, 1, 2]
            and all((event.node_index, event.emitted_call_index) == coordinates for event in events)
        )
        hooks = [ToolHookRequest.model_validate_json(event.request_json) for event in events]
        if valid:
            original = json.loads(expected[coordinates].call_json)
            valid = (
                all(
                    hook.call is not None
                    and canonical_json(hook.call.model_dump(mode="json"))
                    == canonical_json(original)
                    for hook in hooks
                )
                and json.loads(events[0].decision_json).get("action") == "allow"
                and json.loads(events[1].decision_json).get("action") == "allow"
                and json.loads(events[2].decision_json).get("action") == "allow"
                and hooks[2].error is None
                and hooks[2].raw_result is not None
            )
        route = hooks[1].mcp_dispatch if len(hooks) == 3 else None
        ticket = (
            json.loads(events[1].decision_json).get("mcp_dispatch_ticket")
            if len(events) == 3
            else None
        )
        if (
            not valid
            or route is None
            or route.server_name != (AutomationBenchToolset.TOOL_PREFIX or "")
            or route.tool_name not in {"execute_tool", "search_tools"}
            or type(ticket) is not str
            or not ticket
        ):
            reasons.append("invocation_native_harness_lifecycle_or_route_unavailable")
            continue
        coverage.setdefault(coordinates, []).append(identity)
    if set(coverage) != set(expected) or any(
        len(identities) != 1 for identities in coverage.values()
    ):
        reasons.append("invocation_original_emitted_population_mismatch")
    resolved = {
        parent.execution.invocation_id: parent
        for parent in material.server_parents
        if parent.status == "resolved" and parent.parent is not None
    }
    if set(resolved) != {entry.invocation_id for entry in entries}:
        reasons.append("invocation_native_physical_population_unlinked")
    parent_attempts, used = {}, set()
    for entry in entries:
        proof = resolved.get(entry.invocation_id)
        if proof is None or proof.parent is None:
            continue
        parent = proof.parent.invocation_id
        events = groups.get(parent)
        if events is None or parent not in {
            identity for identities in coverage.values() for identity in identities
        }:
            reasons.append("invocation_native_parent_not_in_emitted_population")
            continue
        dispatch = next(
            (
                event
                for event in source["tool_execution_events"]
                if event.get("source") == "tool_server"
                and event.get("invocation_id") == entry.invocation_id
                and event.get("phase") == "dispatch"
            ),
            None,
        )
        if dispatch is None:
            reasons.append("invocation_native_physical_dispatch_missing")
            continue
        receipt = ToolServerReceipt.model_validate_json(dispatch["receipt_json"])
        attempt = receipt.transport_attempt_index
        if type(attempt) is not int or (parent, attempt) in used:
            reasons.append("invocation_native_transport_attempt_ambiguous")
            continue
        used.add((parent, attempt))
        parent_attempts.setdefault(parent, []).append(entry.invocation_id)
        pairs.append(
            NativeCoveragePair(
                native_invocation_id=entry.invocation_id,
                parent_execution_id=parent,
                node_index=events[0].node_index,
                emitted_call_index=events[0].emitted_call_index,
                transport_attempt_index=attempt,
            )
        )
    if set(parent_attempts) != {
        identity for identities in coverage.values() for identity in identities
    }:
        reasons.append("invocation_native_dispatched_parent_without_observed_attempt")
    for parent in parent_attempts:
        last = max(
            (pair for pair in pairs if pair.parent_execution_id == parent),
            key=lambda pair: pair.transport_attempt_index,
        )
        entry = next(entry for entry in entries if entry.invocation_id == last.native_invocation_id)
        hook = ToolHookRequest.model_validate_json(groups[parent][-1].request_json)
        if entry.result_json is None or canonical_json(
            json.loads(entry.result_json)
        ) != canonical_json(hook.raw_result):
            reasons.append("invocation_native_harness_terminal_result_mismatch")
    return tuple(pairs), reasons, native_source.snapshot_id


def capture_invocation_inventory(
    source: Mapping, *, native_source: SourceSnapshot | None = None
) -> InvocationInventory:
    source_id = _digest(source)
    reasons, entries, native_pairs, native_snapshot_id = [], [], (), None
    try:
        if any(
            not isinstance(source.get(key), (tuple, list))
            for key in ("tool_execution_events", "state_write_receipts")
        ):
            raise ValueError("invocation_native_inventory_missing")
        receipts, grouped_events = {}, {}
        for event in source["tool_execution_events"]:
            try:
                if event.get("source") in {"harness", "interceptor"}:
                    ToolExecutionEvent.model_validate(event)
                    continue
                if (
                    native_source is not None
                    and source.get("task_evidence", {})
                    .get("authored_outputs", {})
                    .get("sdk_declared")
                    is not True
                ):
                    ToolServerExecutionEvent.model_validate(event)
                raw = json.loads(event["receipt_json"])
                if (
                    raw.get("state_conflict") is not None
                    and type(raw["state_conflict"]) is not bool
                ):
                    raise ValueError("invocation_conflict_metadata_type_unavailable")
                receipt = ToolServerReceipt.model_validate(raw)
                if (
                    event.get("source") != "tool_server"
                    or event.get("invocation_id", receipt.invocation_id) != receipt.invocation_id
                    or event.get("phase", receipt.phase) != receipt.phase
                    or type(event.get("event_index", receipt.event_index)) is not int
                    or event.get("event_index", receipt.event_index) != receipt.event_index
                ):
                    raise ValueError("invocation_event_envelope_mismatch")
                key = (event["source"], receipt.invocation_id)
                receipts.setdefault(key, []).append(receipt)
                grouped_events.setdefault(key, []).append(event)
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                reasons.append(str(error))
        transitions = []
        # Each world's bytes are published once per trace, possibly by another
        # invocation's receipt, so resolve every group against the whole trace.
        store = SnapshotStore()
        for events in grouped_events.values():
            for event in events:
                try:
                    for envelope in raw_action_envelopes([json.loads(event["receipt_json"])]):
                        store.add(envelope)
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue  # corrupt material stays unavailable to its own group
        for key, group_events in grouped_events.items():
            try:
                acknowledgements = [
                    write
                    for write in source["state_write_receipts"]
                    if write.get("write_id") == key[1]
                ]
                if len(acknowledgements) != 1 or acknowledgements[0].get("conflict") is not False:
                    raise ValueError("invocation_acknowledgement_unqualified")
                StateWriteReceipt.model_validate(acknowledgements[0])
                group = world_transitions(
                    {
                        "tool_execution_events": group_events,
                        "state_write_receipts": acknowledgements,
                    },
                    store,
                )
                index_group = EffectIndex(group)
                transitions.extend(index_group.occurrences)
                entries.extend(_entry(item, receipts) for item in index_group.occurrences)
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                reasons.append(str(error))
                entries.append(
                    InvocationEntry(
                        invocation_id=key[1], origin=key[0], status="unavailable", reason=str(error)
                    )
                )
        index = EffectIndex(transitions)
        reasons.extend(entry.reason for entry in entries if entry.status != "qualified")
        task = source.get("task_evidence")
        if not isinstance(task, Mapping):
            task = {}
        if task.get("complete") is not True:
            reasons.append("invocation_task_finalization_unavailable")
        chain = index.serial_chain()
        if entries:
            if (
                chain.status != "qualified"
                or chain.revision_interval is None
                or chain.revision_interval[0] != 0
            ):
                reasons.append("invocation_complete_serial_inventory_unavailable")
            elif chain.ordered[-1].after_json is None or canonical_json(
                _plain(index.world(chain.ordered[-1].after_json))
            ) != canonical_json(task.get("final")):
                reasons.append("invocation_terminal_world_mismatch")
        elif not isinstance(task.get("initial"), Mapping) or canonical_json(
            task["initial"]
        ) != canonical_json(task.get("final")):
            reasons.append("invocation_empty_inventory_world_unreconciled")
        writes = source["state_write_receipts"]
        ids = [write.get("write_id") for write in writes]
        if Counter(ids) != Counter(entry.invocation_id for entry in entries):
            reasons.append("invocation_ack_population_mismatch")
        projection = task.get("authored_outputs")
        if isinstance(projection, Mapping) and projection.get("sdk_declared") is True:
            pairs, sdk_reasons = _sdk_pairs(source, entries)
            reasons.extend(sdk_reasons)
        else:
            pairs = ()
            native_pairs, native_reasons, native_snapshot_id = _native_pairs(
                source, entries, native_source
            )
            reasons.extend(native_reasons)
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        pairs = ()
        reasons.append(str(error))
    return InvocationInventory(
        source_digest=source_id,
        entries=tuple(entries),
        closed=not reasons,
        reason=reasons[0]
        if reasons
        else "native_authorized_invocation_population_coverage"
        if native_source is not None and native_snapshot_id is not None
        else "unique_sdk_native_invocation_population_coverage",
        sdk_coverage_pairs=pairs,
        native_coverage_pairs=native_pairs,
        native_snapshot_id=native_snapshot_id,
    )


def validate_invocation_inventory(
    inventory: InvocationInventory, source: Mapping, *, native_source: SourceSnapshot | None = None
) -> None:
    admitted = InvocationInventory.model_validate(
        inventory.model_dump(mode="python", warnings=False)
    )
    actual = capture_invocation_inventory(source, native_source=native_source)
    if canonical_json(admitted.model_dump(mode="json")) != canonical_json(
        actual.model_dump(mode="json")
    ):
        raise ValueError("invocation_inventory_raw_source_mismatch")
