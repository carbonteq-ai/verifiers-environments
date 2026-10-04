"""Small factual native-call projections derived from an executor-sealed source.

This does not declare invocation/output coverage. The native resolver proves
observed server parents; an environment adapter must still reconcile complete
sampled, harness and physical populations and qualify operation effects.
"""

import json
from collections import Counter
from collections.abc import Mapping
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr
from verifiers.v1.assessment_source import resolve_execution_parent
from verifiers.v1.assessments import ExecutionRef, SourceSnapshot, content_digest
from verifiers.v1.types import generated_arguments_equal

from .capture import canonical_json
from .contracts.base import FrozenModel
from .contracts.tables import Digest


class NativeEmittedCall(FrozenModel):
    emitted_call_index: StrictInt = Field(ge=0)
    call_json: StrictStr
    status: Literal["observed", "unavailable"]
    reason: StrictStr


class NativeGeneratedCoordinate(FrozenModel):
    attempt_index: StrictInt | None = Field(default=None, ge=0)
    emitted_call_index: StrictInt | None = Field(default=None, ge=0)
    status: Literal["observed", "unavailable"]
    reason: StrictStr


class NativeInvocationNode(FrozenModel):
    node_index: StrictInt = Field(ge=0)
    node_content_digest: Digest
    parent: StrictInt | None = Field(default=None, ge=0)
    sampled: StrictBool | None
    role: StrictStr | None
    tool_calls: tuple[NativeEmittedCall, ...] = ()
    generated_coordinates: tuple[NativeGeneratedCoordinate, ...] = ()
    status: Literal["observed", "unavailable"]
    reason: StrictStr


class NativeModelCallTerminal(FrozenModel):
    call_index: StrictInt = Field(ge=0)
    node_index: StrictInt | None = Field(default=None, ge=0)
    finish_reason: StrictStr | None = None
    failed: StrictBool | None = None
    status: Literal["observed", "unavailable"]
    reason: StrictStr


class NativeServerParent(FrozenModel):
    execution: ExecutionRef
    parent: ExecutionRef | None = None
    status: Literal["resolved", "unavailable"]
    reason: StrictStr


class NativeInvocationMaterial(FrozenModel):
    schema_version: Literal[1] = 1
    snapshot_id: StrictStr
    source_digest: Digest
    trace_id: StrictStr
    sdk_declared: StrictBool | None
    producer_complete: StrictBool | None
    nodes: tuple[NativeInvocationNode, ...]
    model_calls: tuple[NativeModelCallTerminal, ...]
    raw_model_call_count: StrictInt | None = Field(default=None, ge=0)
    terminal_inventory_status: Literal["observed", "unavailable"]
    terminal_inventory_reason: StrictStr
    server_parents: tuple[NativeServerParent, ...]


def _coordinate(value):
    return value if type(value) is int and value >= 0 else None


def _call(index, raw):
    valid = (
        isinstance(raw, Mapping)
        and set(raw) == {"id", "name", "type", "arguments"}
        and all(type(raw.get(key)) is str for key in ("id", "name", "arguments"))
        and type(raw.get("type")) is str
        and raw.get("type") in {"function", "custom"}
    )
    return NativeEmittedCall(
        emitted_call_index=index,
        call_json=canonical_json(raw),
        status="observed" if valid else "unavailable",
        reason="original_emitted_call" if valid else "native_emitted_call_shape_unavailable",
    )


def _node(index, raw, anchor):
    if not isinstance(raw, Mapping):
        return NativeInvocationNode(
            node_index=index,
            node_content_digest=anchor.node_content_digest,
            sampled=None,
            role=None,
            status="unavailable",
            reason="native_node_shape_unavailable",
        )
    parent = raw.get("parent")
    sampled = raw.get("sampled")
    message = raw.get("message")
    role = message.get("role") if isinstance(message, Mapping) else None
    reasons, calls, generated = [], [], []
    if parent is not None and (_coordinate(parent) is None or parent >= index):
        reasons.append("native_original_parent_unavailable")
    if type(sampled) is not bool or type(role) is not str:
        reasons.append("native_original_node_metadata_unavailable")
    if not isinstance(raw.get("mask"), list) or any(
        type(value) is not bool for value in raw["mask"]
    ):
        reasons.append("native_original_sampling_mask_unavailable")
    if sampled is True and role != "assistant":
        reasons.append("native_sampled_node_role_unsupported")
    if sampled is True and role == "assistant" and isinstance(message, Mapping):
        if "tool_calls" not in message:
            reasons.append("native_emitted_call_inventory_missing")
        elif message["tool_calls"] is not None:
            if not isinstance(message["tool_calls"], list):
                reasons.append("native_emitted_call_inventory_invalid")
            else:
                calls = [_call(ordinal, call) for ordinal, call in enumerate(message["tool_calls"])]
                reasons.extend(call.reason for call in calls if call.status == "unavailable")
                ids = [
                    call.get("id") for call in message["tool_calls"] if isinstance(call, Mapping)
                ]
                if any(
                    count > 1
                    for count in Counter(canonical_json(identity) for identity in ids).values()
                ):
                    reasons.append("native_same_node_provider_identity_ambiguous")
    attempts = raw.get("generated_calls", [])
    if not isinstance(attempts, list):
        reasons.append("native_generated_coordinate_inventory_invalid")
    else:
        attempt_counts = Counter(
            attempt.get("attempt_index")
            for attempt in attempts
            if isinstance(attempt, Mapping)
            and _coordinate(attempt.get("attempt_index")) is not None
        )
        emitted_counts = Counter(
            attempt.get("emitted_call_index")
            for attempt in attempts
            if isinstance(attempt, Mapping)
            and _coordinate(attempt.get("emitted_call_index")) is not None
        )
        for attempt in attempts:
            original = attempt.get("attempt_index") if isinstance(attempt, Mapping) else None
            emitted = attempt.get("emitted_call_index") if isinstance(attempt, Mapping) else None
            valid = (
                _coordinate(original) is not None
                and attempt_counts[original] == 1
                and (
                    emitted is None
                    or (
                        _coordinate(emitted) is not None
                        and emitted < len(calls)
                        and emitted_counts[emitted] == 1
                    )
                )
            )
            if valid and emitted is not None:
                emitted_call = json.loads(calls[emitted].call_json)
                valid = (
                    calls[emitted].status == "observed"
                    and attempt.get("parse_status") == "parsed"
                    and type(attempt.get("provider_call_id")) is str
                    and attempt["provider_call_id"] == emitted_call["id"]
                    and type(attempt.get("name")) is str
                    and attempt["name"] == emitted_call["name"]
                    and type(attempt.get("arguments")) is str
                    and generated_arguments_equal(attempt["arguments"], emitted_call["arguments"])
                )
            generated.append(
                NativeGeneratedCoordinate(
                    attempt_index=_coordinate(original),
                    emitted_call_index=_coordinate(emitted),
                    status="observed" if valid else "unavailable",
                    reason="original_generated_coordinate"
                    if valid
                    else "native_generated_coordinate_unavailable",
                )
            )
            if not valid:
                reasons.append("native_generated_coordinate_unavailable")
    return NativeInvocationNode(
        node_index=index,
        node_content_digest=anchor.node_content_digest,
        parent=_coordinate(parent),
        sampled=sampled if type(sampled) is bool else None,
        role=role if type(role) is str else None,
        tool_calls=tuple(calls),
        generated_coordinates=tuple(generated),
        status="observed" if not reasons else "unavailable",
        reason=reasons[0] if reasons else "original_node_metadata",
    )


def build_native_invocation_material(
    source: SourceSnapshot, *, trace_id: str | None = None
) -> NativeInvocationMaterial:
    """Project the sealed source only, never an alternate mutable current trace.

    Native snapshot top-level model calls omit terminal flags. The authenticated
    task producer's authored-output terminal projection is reused only when its
    original call ordinals/nodes exactly agree with the raw native call list.
    Missing or contradictory terminal facts remain explicit unavailable facts.
    Place this value in working material after sealing; embedding its source
    digest into its own source would create an invalid recursive identity.
    """
    source = SourceSnapshot.model_validate(source.model_dump(mode="python", warnings=False))
    raw = json.loads(source.source_json)
    if trace_id is None:
        if len(source.trace_ids) != 1:
            raise ValueError("native_invocation_projection_requires_one_selected_trace")
        trace_id = source.trace_ids[0]
    if trace_id not in source.trace_ids:
        raise ValueError("native_invocation_projection_trace_not_in_source")
    if "traces" in raw:
        matches = [
            child
            for child in raw["traces"]
            if isinstance(child, dict) and child.get("trace_id") == trace_id
        ]
        if len(matches) != 1:
            raise ValueError("native_invocation_projection_trace_ambiguous")
        raw = matches[0]
    if raw.get("trace_id") != trace_id or not isinstance(raw.get("nodes"), list):
        raise ValueError("native_invocation_projection_nodes_unavailable")
    anchors = {anchor.node_index: anchor for anchor in source.nodes if anchor.trace_id == trace_id}
    if set(anchors) != set(range(len(raw["nodes"]))):
        raise ValueError("native_invocation_projection_node_anchor_inventory_mismatch")
    if any(
        content_digest(node) != anchors[index].node_content_digest
        for index, node in enumerate(raw["nodes"])
    ):
        raise ValueError("native_invocation_projection_node_anchor_digest_mismatch")
    nodes = tuple(_node(index, node, anchors[index]) for index, node in enumerate(raw["nodes"]))
    task = raw.get("task_evidence")
    task = task if isinstance(task, Mapping) else {}
    projection = task.get("authored_outputs")
    projection = projection if isinstance(projection, Mapping) else {}
    declared = projection.get("native_calls")
    calls = raw.get("calls")
    reconciled = (
        isinstance(calls, list)
        and isinstance(declared, list)
        and len(calls) == len(declared)
        and projection.get("trace_id") == trace_id
        and type(projection.get("schema_version")) is int
        and projection.get("schema_version") == 1
    )
    terminals = []
    for index, call in enumerate(calls if isinstance(calls, list) else []):
        reported = declared[index] if reconciled and isinstance(declared, list) else None
        node = call.get("node") if isinstance(call, Mapping) else None
        reported_node = reported.get("node") if isinstance(reported, Mapping) else None
        valid = (
            reconciled
            and isinstance(call, Mapping)
            and "node" in call
            and isinstance(reported, Mapping)
            and set(reported) == {"node", "finish_reason", "failed"}
            and canonical_json(node) == canonical_json(reported_node)
            and (node is None or (_coordinate(node) is not None and node < len(nodes)))
            and type(reported.get("failed")) is bool
            and (
                reported.get("finish_reason") is None or type(reported.get("finish_reason")) is str
            )
        )
        terminal = (
            valid
            and isinstance(reported, Mapping)
            and (
                reported["failed"] is True
                or (
                    node is not None
                    and nodes[node].sampled is True
                    and nodes[node].role == "assistant"
                    and reported["finish_reason"] in {"stop", "tool_calls"}
                )
            )
        )
        terminals.append(
            NativeModelCallTerminal(
                call_index=index,
                node_index=_coordinate(node),
                finish_reason=reported["finish_reason"]
                if valid and isinstance(reported, Mapping)
                else None,
                failed=reported["failed"] if valid and isinstance(reported, Mapping) else None,
                status="observed" if terminal else "unavailable",
                reason="sealed_producer_terminal_projection"
                if terminal
                else "native_model_terminal_projection_unavailable",
            )
        )
    selected_nodes = [
        node.node_index for node in nodes if node.sampled is True and node.role == "assistant"
    ]
    committed_nodes = [call.node_index for call in terminals if call.node_index is not None]
    observed = (
        reconciled
        and all(call.status == "observed" for call in terminals)
        and Counter(selected_nodes) == Counter(committed_nodes)
    )
    parents = []
    for execution in source.executions:
        if execution.trace_id != trace_id or execution.origin != "tool_server":
            continue
        try:
            parent = resolve_execution_parent(source, execution)
            reason = (
                "native_authorized_dispatch_parent"
                if parent is not None
                else "native_server_parent_unlinked"
            )
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            parent, reason = None, str(error)
        parents.append(
            NativeServerParent(
                execution=execution,
                parent=parent,
                status="resolved" if parent is not None else "unavailable",
                reason=reason,
            )
        )
    return NativeInvocationMaterial(
        snapshot_id=source.snapshot_id,
        source_digest=source.source_digest,
        trace_id=trace_id,
        sdk_declared=projection.get("sdk_declared")
        if type(projection.get("sdk_declared")) is bool
        else None,
        producer_complete=task.get("complete") if type(task.get("complete")) is bool else None,
        nodes=nodes,
        model_calls=tuple(terminals),
        raw_model_call_count=len(calls) if isinstance(calls, list) else None,
        terminal_inventory_status="observed" if observed else "unavailable",
        terminal_inventory_reason="sealed_producer_terminal_inventory"
        if observed
        else "native_model_terminal_inventory_unavailable",
        server_parents=tuple(parents),
    )


def validate_native_invocation_material(
    material: NativeInvocationMaterial, source: SourceSnapshot
) -> None:
    admitted = NativeInvocationMaterial.model_validate(
        material.model_dump(mode="python", warnings=False)
    )
    actual = build_native_invocation_material(source, trace_id=admitted.trace_id)
    if canonical_json(admitted.model_dump(mode="json")) != canonical_json(
        actual.model_dump(mode="json")
    ):
        raise ValueError("native_invocation_projection_raw_source_mismatch")
