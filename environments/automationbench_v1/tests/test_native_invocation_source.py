"""Factual projection through genuine host dispatch admission; no paid models."""

import asyncio
import copy
import json

import pytest
import verifiers.v1 as vf
from test_external_output_source import actual, material
from verifiers.v1.assessment_source import capture_trace_source
from verifiers.v1.assessments import NodeRef, SourceSnapshot, content_digest
from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.client import EvalClientConfig
from verifiers.v1.interception.tool import MCPDispatch, ToolHookRequest
from verifiers.v1.session import RolloutSession

from automationbench_v1.authored_output_source import build_authored_output_material
from automationbench_v1.native_invocation_source import (
    NativeInvocationMaterial,
    build_native_invocation_material,
    validate_native_invocation_material,
)


async def _linked_source():
    call = vf.ToolCall(id="repeated-provider-id", name="counter_bump", arguments="{}")
    trace = vf.Trace(
        episode_id="native-projection",
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type="Task", data=vf.TaskData(prompt="bump")),
        nodes=[
            vf.MessageNode(message=vf.UserMessage(content="request")),
            vf.MessageNode(
                parent=0,
                message=vf.AssistantMessage(content="not duplicated", tool_calls=[call]),
                sampled=True,
                token_ids=[101, 102],
                mask=[True, True],
            ),
        ],
        calls=[vf.ModelCall(node=1, finish_reason="tool_calls")],
    )
    session = RolloutSession(ModelContext("model", EvalClientConfig()), trace)
    message = vf.ToolMessage(tool_call_id=call.id, name=call.name, content="")
    for index, phase in enumerate(("before", "dispatch")):
        decision = await session.handle_tool(
            phase,
            message,
            request=ToolHookRequest(
                phase=phase,
                message=message,
                execution_id="parent",
                call=call,
                event_index=index,
                mcp_dispatch=MCPDispatch(
                    server_name="counter", tool_name="bump", arguments_json="{}"
                )
                if phase == "dispatch"
                else None,
            ),
        )
    # Transport attempts need not be contiguous to preserve their exact parents.
    for attempt in (0, 3):
        receipt = vf.ToolServerReceipt(
            invocation_id=f"physical-{attempt}",
            event_index=0,
            phase="dispatch",
            tool_name="bump",
            arguments_json='{"args":[],"kwargs":{}}',
            parent_execution_id="parent",
            dispatch_ticket=decision["mcp_dispatch_ticket"],
            transport_attempt_index=attempt,
            server_name="counter",
        )
        session.retain_tool_server_receipt(receipt)
        session.retain_tool_server_receipt(
            receipt.model_copy(
                update={"event_index": 1, "phase": "returned", "result_json": '"observed"'}
            )
        )
    await session.handle_tool(
        "after",
        message,
        request=ToolHookRequest(
            phase="after",
            message=message,
            execution_id="parent",
            call=call,
            event_index=2,
            raw_result="observed",
        ),
    )
    trace.is_completed = True
    return capture_trace_source(
        trace,
        task_evidence={"complete": True, "authored_outputs": build_authored_output_material(trace)},
    )


@pytest.fixture
def linked_source():
    return asyncio.run(_linked_source())


def resealed(source, mutate):
    raw = json.loads(source.source_json)
    mutate(raw)
    nodes = tuple(
        NodeRef(
            trace_id=raw["trace_id"], node_index=index, node_content_digest=content_digest(node)
        )
        for index, node in enumerate(raw["nodes"])
    )
    return SourceSnapshot.capture(
        raw,
        episode_id=source.episode_id,
        trace_ids=source.trace_ids,
        nodes=nodes,
        executions=source.executions,
    )


def unlinked_resealed(source, mutate):
    raw = json.loads(source.source_json)
    raw.pop("tool_execution_events", None)
    mutate(raw)
    return SourceSnapshot.capture(
        raw,
        episode_id=source.episode_id,
        trace_ids=source.trace_ids,
        nodes=tuple(
            NodeRef(
                trace_id=raw["trace_id"], node_index=index, node_content_digest=content_digest(node)
            )
            for index, node in enumerate(raw["nodes"])
        ),
    )


def test_projection_uses_original_calls_terminal_inventory_and_public_parent_resolver(
    linked_source,
):
    material = build_native_invocation_material(linked_source)
    assert material.terminal_inventory_status == "observed" and material.raw_model_call_count == 1
    assert (
        material.model_calls[0].node_index == 1
        and material.model_calls[0].finish_reason == "tool_calls"
    )
    assert material.nodes[1].tool_calls[0].emitted_call_index == 0
    assert json.loads(material.nodes[1].tool_calls[0].call_json)["id"] == "repeated-provider-id"
    assert len(material.server_parents) == 2
    assert all(
        parent.status == "resolved"
        and parent.parent is not None
        and parent.parent.invocation_id == "parent"
        for parent in material.server_parents
    )
    payload = material.model_dump(mode="json")
    assert "token_ids" not in json.dumps(payload) and "not duplicated" not in json.dumps(payload)
    assert "closed" not in payload
    validate_native_invocation_material(
        NativeInvocationMaterial.model_validate_json(material.model_dump_json()), linked_source
    )
    assert (
        build_native_invocation_material(
            SourceSnapshot.model_validate_json(linked_source.model_dump_json())
        )
        == material
    )


@pytest.mark.parametrize("change", ["missing", "count", "node", "failed-bool", "schema-bool"])
def test_missing_or_invalid_terminal_projection_preserves_original_inventory(linked_source, change):
    def mutate(raw):
        projection = raw["task_evidence"]["authored_outputs"]
        if change == "missing":
            projection.pop("native_calls")
        elif change == "count":
            projection["native_calls"] = []
        elif change == "node":
            projection["native_calls"][0]["node"] = True
        elif change == "failed-bool":
            projection["native_calls"][0]["failed"] = 0
        else:
            projection["schema_version"] = True

    material = build_native_invocation_material(resealed(linked_source, mutate))
    assert material.terminal_inventory_status == "unavailable" and len(material.model_calls) == 1
    assert material.nodes[1].tool_calls and len(material.server_parents) == 2


@pytest.mark.parametrize("change", ["sampled", "mask", "duplicate-provider"])
def test_invalid_original_metadata_cannot_become_qualified_sampling(linked_source, change):
    # Remove linked receipts before deliberately introducing a malformed sampled
    # node; the source's native parent validator independently rejects those.
    def mutate(raw):
        raw.pop("tool_execution_events")
        if change == "sampled":
            raw["nodes"][1]["sampled"] = 1
        elif change == "mask":
            raw["nodes"][1]["mask"] = [1, 1]
        else:
            calls = raw["nodes"][1]["message"]["tool_calls"]
            calls.append(copy.deepcopy(calls[0]))

    raw = json.loads(linked_source.source_json)
    mutate(raw)
    source = SourceSnapshot.capture(
        raw,
        episode_id=linked_source.episode_id,
        trace_ids=linked_source.trace_ids,
        nodes=tuple(
            NodeRef(
                trace_id=raw["trace_id"], node_index=i, node_content_digest=content_digest(node)
            )
            for i, node in enumerate(raw["nodes"])
        ),
    )
    assert build_native_invocation_material(source).nodes[1].status == "unavailable"


@pytest.mark.parametrize("change", ["digest", "node-bool", "call", "parent"])
def test_copied_projection_cannot_override_current_sealed_source(linked_source, change):
    material = build_native_invocation_material(linked_source)
    if change == "digest":
        forged = material.model_copy(update={"source_digest": "0" * 64})
    elif change == "node-bool":
        forged = material.model_copy(
            update={
                "nodes": (
                    material.nodes[0],
                    material.nodes[1].model_copy(update={"node_index": True}),
                )
            }
        )
    elif change == "call":
        node = material.nodes[1]
        forged = material.model_copy(
            update={
                "nodes": (
                    material.nodes[0],
                    node.model_copy(
                        update={
                            "tool_calls": (
                                node.tool_calls[0].model_copy(update={"call_json": "{}"}),
                            )
                        }
                    ),
                )
            }
        )
    else:
        forged = material.model_copy(
            update={
                "server_parents": (
                    material.server_parents[0].model_copy(update={"parent": None}),
                    material.server_parents[1],
                )
            }
        )
    with pytest.raises(ValueError):
        validate_native_invocation_material(forged, linked_source)


def test_actual_legacy_sdk_is_not_retroactively_given_native_parent_links():
    _, original_bytes, _, _, trace, task = actual()
    before = material(trace, task)
    source = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    projection = build_native_invocation_material(source)
    assert projection.sdk_declared is True
    assert len(projection.server_parents) == 7
    assert all(
        parent.status == "unavailable" and parent.parent is None
        for parent in projection.server_parents
    )
    assert trace.info["codex_sdk"]["mcp_item_execution_join"] == "unqualified"
    assert material(trace, task) == before
    path, after_bytes, _, _, _, _ = actual()
    assert path.read_bytes() == original_bytes == after_bytes


@pytest.mark.parametrize("bad_type", [[], {}])
def test_unhashable_emitted_call_type_preserves_unavailable_fact(linked_source, bad_type):
    source = unlinked_resealed(
        linked_source, lambda raw: raw["nodes"][1]["message"]["tool_calls"][0].update(type=bad_type)
    )
    projection = build_native_invocation_material(source)
    assert projection.nodes[1].status == "unavailable"
    assert projection.nodes[1].tool_calls[0].status == "unavailable"


@pytest.mark.parametrize(
    "change", ["attempt-duplicate", "emitted-duplicate", "range", "owner", "bool"]
)
def test_generated_coordinate_relation_is_not_qualified_by_individual_integers(
    linked_source, change
):
    def mutate(raw):
        call = raw["nodes"][1]["message"]["tool_calls"][0]
        coordinate = {
            "attempt_index": 1,
            "emitted_call_index": 0,
            "parse_status": "parsed",
            "provider_call_id": call["id"],
            "name": call["name"],
            "arguments": call["arguments"],
        }
        attempts = [coordinate]
        if change in {"attempt-duplicate", "emitted-duplicate"}:
            attempts.append(
                {**coordinate, "attempt_index": 1 if change == "attempt-duplicate" else 3}
            )
        elif change == "range":
            coordinate["emitted_call_index"] = 9
        elif change == "owner":
            coordinate["provider_call_id"] = "unrelated-provider-call"
        else:
            coordinate["attempt_index"] = True
        raw["nodes"][1]["generated_calls"] = attempts

    projection = build_native_invocation_material(unlinked_resealed(linked_source, mutate))
    assert projection.nodes[1].status == "unavailable"
    assert all(
        coordinate.status == "unavailable"
        for coordinate in projection.nodes[1].generated_coordinates
    )


@pytest.mark.parametrize("change", ["nonterminal", "missing-generated-node", "duplicate-node"])
def test_incomplete_model_call_inventory_never_looks_observed_empty(linked_source, change):
    def mutate(raw):
        terminals = raw["task_evidence"]["authored_outputs"]["native_calls"]
        if change == "nonterminal":
            raw["calls"][0]["node"] = None
            terminals[0].update(node=None, finish_reason=None, failed=False)
        elif change == "missing-generated-node":
            raw["calls"] = []
            raw["task_evidence"]["authored_outputs"]["native_calls"] = []
        else:
            raw["calls"].append(copy.deepcopy(raw["calls"][0]))
            terminals.append(copy.deepcopy(terminals[0]))

    projection = build_native_invocation_material(resealed(linked_source, mutate))
    assert projection.terminal_inventory_status == "unavailable"
    assert projection.nodes[1].tool_calls
