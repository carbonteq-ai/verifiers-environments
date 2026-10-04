"""Host-authenticated dispatches around real simulator effects.

State acknowledgements here are validated manufactured envelopes. The sibling
transport suite exercises the real HTTP MCP server and state controller.
"""

import asyncio
import copy
import json

import pytest
import verifiers.v1 as vf
from test_contact_record_evidence import public, update
from test_manifest_invocation_inventory import source as sdk_source
from test_native_invocation_source import resealed
from test_notification_evidence import run_operations
from verifiers.v1.assessment_source import capture_trace_source
from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.client import EvalClientConfig
from verifiers.v1.interception.tool import MCPDispatch, ToolHookRequest
from verifiers.v1.session import RolloutSession

from automationbench_v1.authored_output_source import build_authored_output_material
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.invocation_inventory import (
    InvocationInventory,
    capture_invocation_inventory,
    validate_invocation_inventory,
)


def safe(source):
    raw = json.loads(source.source_json)
    return {
        key: raw.get(key, [])
        for key in ("task_evidence", "tool_execution_events", "state_write_receipts")
    }


async def linked(
    *,
    omitted=False,
    repeated=False,
    physical_retry=False,
    after_error=False,
    wrong_result=False,
    policy=None,
):
    material = run_operations(
        public(), [update(), update()] if repeated or physical_retry else [update()]
    )
    trace = vf.Trace(
        episode_id="native-call-coverage-interface",
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type="Task", data=vf.TaskData(prompt="update")),
        nodes=[vf.MessageNode(message=vf.UserMessage(content="update"))],
    )
    session = RolloutSession(ModelContext("no-inference", EvalClientConfig()), trace)
    for index, reduced in enumerate(material["tool_execution_events"]):
        local = json.loads(reduced["receipt_json"])
        action = json.loads(local["evidence_json"][0])["action"]
        args = json.loads(action["arguments_json"])
        call = vf.ToolCall(
            id="same-provider-id", name="execute_tool", arguments=canonical_json(args)
        )
        if not physical_retry or index == 0:
            trace.nodes.append(
                vf.MessageNode(
                    parent=len(trace.nodes) - 1,
                    message=vf.AssistantMessage(content=None, tool_calls=[call]),
                    sampled=True,
                )
            )
            trace.calls.append(vf.ModelCall(node=len(trace.nodes) - 1, finish_reason="tool_calls"))
        message = vf.ToolMessage(tool_call_id=call.id, name=call.name, content="")
        parent = "parent-0" if physical_retry else f"parent-{index}"
        if not physical_retry or index == 0:
            for ordinal, phase in enumerate(("before", "dispatch")):
                decision = await session.handle_tool(
                    phase,
                    message,
                    request=ToolHookRequest(
                        phase=phase,
                        message=message,
                        execution_id=parent,
                        call=call,
                        event_index=ordinal,
                        mcp_dispatch=MCPDispatch(
                            server_name="",
                            tool_name="execute_tool",
                            arguments_json=canonical_json(args),
                        )
                        if phase == "dispatch"
                        else None,
                    ),
                )
        dispatch = vf.ToolServerReceipt(
            invocation_id=local["invocation_id"],
            event_index=0,
            phase="dispatch",
            tool_name="execute_tool",
            arguments_json=canonical_json({"args": [], "kwargs": args}),
            state_read_revision=index,
            parent_execution_id=parent,
            dispatch_ticket=decision["mcp_dispatch_ticket"],
            transport_attempt_index=index if physical_retry else 0,
            server_name="",
        )
        session.retain_tool_server_receipt(dispatch)
        trace.state_write_receipts += (
            vf.StateWriteReceipt(
                **material["state_write_receipts"][index], body_digest=action["after_digest"]
            ),
        )
        session.state_revision = index + 1
        session.retain_tool_server_receipt(
            dispatch.model_copy(
                update={
                    "event_index": 1,
                    "phase": "returned",
                    "result_json": action["result_json"],
                    "evidence_json": tuple(local["evidence_json"]),
                    "state_write_revision": index + 1,
                    "state_persistence": "applied",
                    "state_conflict": False,
                }
            )
        )
        if physical_retry and index == 0:
            continue
        await session.handle_tool(
            "raised" if after_error else "after",
            message,
            request=ToolHookRequest(
                phase="raised" if after_error else "after",
                message=message,
                execution_id=parent,
                call=call,
                event_index=2,
                raw_result=None
                if after_error
                else "unrelated result"
                if wrong_result
                else json.loads(action["result_json"]),
                error="reported execution failure" if after_error else None,
            ),
        )
    if omitted:
        trace.nodes.append(
            vf.MessageNode(
                parent=len(trace.nodes) - 1,
                message=vf.AssistantMessage(content=None, tool_calls=[call]),
                sampled=True,
            )
        )
        trace.calls.append(vf.ModelCall(node=len(trace.nodes) - 1, finish_reason="tool_calls"))
    trace.is_completed = True
    trace.ok = True
    if policy is not None:
        material["task_evidence"]["prompt"] = [{"role": "system", "content": policy}]
    material["task_evidence"]["authored_outputs"] = build_authored_output_material(trace)
    return capture_trace_source(trace, task_evidence=material["task_evidence"])


@pytest.fixture
def native_source():
    return asyncio.run(linked())


def test_original_native_call_and_physical_execution_populations_close(native_source):
    value = safe(native_source)
    result = capture_invocation_inventory(value, native_source=native_source)
    assert result.closed, result.reason
    assert len(result.entries) == len(result.native_coverage_pairs) == 1
    pair = result.native_coverage_pairs[0]
    assert pair.node_index == 1 and pair.emitted_call_index == 0
    assert pair.parent_execution_id == "parent-0" and pair.native_invocation_id == "execution-0"
    assert not result.sdk_coverage_pairs
    validate_invocation_inventory(
        InvocationInventory.model_validate_json(result.model_dump_json()),
        value,
        native_source=vf.SourceSnapshot.model_validate_json(native_source.model_dump_json()),
    )


def test_extra_sampled_call_without_dispatch_keeps_known_effect_but_opens_coverage():
    source = asyncio.run(linked(omitted=True))
    result = capture_invocation_inventory(safe(source), native_source=source)
    assert not result.closed and result.reason == "invocation_original_emitted_population_mismatch"
    assert len(result.entries) == 1 and result.entries[0].status == "qualified"


def test_same_safe_projection_with_extra_original_call_cannot_borrow_closed_population(
    native_source,
):
    other = asyncio.run(linked(omitted=True))
    # Authored terminal metadata itself is part of the selected safe source.
    with pytest.raises(ValueError, match="inventory_raw_source_mismatch"):
        validate_invocation_inventory(
            capture_invocation_inventory(safe(native_source), native_source=native_source),
            safe(native_source),
            native_source=other,
        )


def test_repeated_provider_ids_on_distinct_original_nodes_remain_distinct():
    source = asyncio.run(linked(repeated=True))
    result = capture_invocation_inventory(safe(source), native_source=source)
    assert result.closed, result.reason
    assert {pair.node_index for pair in result.native_coverage_pairs} == {1, 2}
    assert {pair.parent_execution_id for pair in result.native_coverage_pairs} == {
        "parent-0",
        "parent-1",
    }


def test_two_physical_retries_cover_one_original_call_without_sdk_ambiguity():
    source = asyncio.run(linked(physical_retry=True))
    result = capture_invocation_inventory(safe(source), native_source=source)
    assert result.closed, result.reason
    assert len(result.entries) == len(result.native_coverage_pairs) == 2
    assert all(entry.status == "qualified" for entry in result.entries)
    assert {pair.native_invocation_id for pair in result.native_coverage_pairs} == {
        "execution-0",
        "execution-1",
    }
    assert {pair.parent_execution_id for pair in result.native_coverage_pairs} == {"parent-0"}
    assert {pair.node_index for pair in result.native_coverage_pairs} == {1}
    assert {pair.emitted_call_index for pair in result.native_coverage_pairs} == {0}
    assert {pair.transport_attempt_index for pair in result.native_coverage_pairs} == {0, 1}
    assert not result.sdk_coverage_pairs


def test_missing_sealed_source_never_claims_native_model_population(native_source):
    result = capture_invocation_inventory(safe(native_source))
    assert not result.closed and len(result.entries) == 1


@pytest.mark.parametrize(
    "field", ["task_evidence", "tool_execution_events", "state_write_receipts"]
)
def test_selected_material_cannot_be_changed_under_authentic_native_source(native_source, field):
    value = safe(native_source)
    if field == "task_evidence":
        value[field]["complete"] = False
    else:
        value[field] = []
    result = capture_invocation_inventory(value, native_source=native_source)
    assert not result.closed


def test_optional_native_source_does_not_change_historical_sdk_branch(native_source):
    value = sdk_source()
    assert capture_invocation_inventory(
        value, native_source=native_source
    ) == capture_invocation_inventory(value)


def test_forged_native_pairs_rejected_by_raw_rederivation(native_source):
    value = safe(native_source)
    result = capture_invocation_inventory(value, native_source=native_source)
    pair = result.native_coverage_pairs[0].model_copy(update={"node_index": True})
    with pytest.raises(ValueError):
        validate_invocation_inventory(
            result.model_copy(update={"native_coverage_pairs": (pair,)}),
            value,
            native_source=native_source,
        )


@pytest.mark.parametrize("kind", ["after_error", "wrong_result"])
def test_harness_terminal_error_or_inconsistent_result_cannot_close(kind):
    source = asyncio.run(linked(**{kind: True}))
    result = capture_invocation_inventory(safe(source), native_source=source)
    assert not result.closed
    assert len(result.entries) == 1 and result.entries[0].status == "qualified"


def test_different_snapshot_same_safe_inputs_with_extra_emitted_node_cannot_close(native_source):
    def mutate(raw):
        raw["nodes"].append(copy.deepcopy(raw["nodes"][1]))
        raw["nodes"][-1]["parent"] = 1
        raw["calls"].append(copy.deepcopy(raw["calls"][0]))
        raw["calls"][-1]["node"] = 2

    expanded = resealed(native_source, mutate)
    assert safe(expanded) == safe(native_source)
    result = capture_invocation_inventory(safe(expanded), native_source=expanded)
    assert not result.closed and result.entries[0].status == "qualified"


def test_no_model_call_inventory_never_proves_native_silence(native_source):
    def mutate(raw):
        raw["calls"] = []
        raw["task_evidence"]["authored_outputs"]["native_calls"] = []

    empty = resealed(native_source, mutate)
    result = capture_invocation_inventory(safe(empty), native_source=empty)
    assert not result.closed and result.entries[0].status == "qualified"
