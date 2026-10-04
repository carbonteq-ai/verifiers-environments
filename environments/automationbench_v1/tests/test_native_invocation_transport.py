"""Real HTTP/state-ACK qualification with deterministic original model-call fixtures.

No inference is performed. Host-issued dispatch tickets and server receipts are
real; original sampled message/model-call records are explicit test inputs.
"""

import asyncio
import copy
import json
import os
import sys
from typing import Any, cast

import httpx
import verifiers.v1 as vf
from aiohttp import web
from aiohttp.test_utils import TestServer
from verifiers.v1.assessment_source import capture_trace_source
from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.client import EvalClientConfig
from verifiers.v1.interception.server import InterceptionServer
from verifiers.v1.interception.tool import MCPDispatch, ToolHookRequest
from verifiers.v1.session import RolloutSession
from verifiers.v1.types import AssistantMessage, ToolCall, ToolMessage

from automationbench.schema.world import WorldState
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.external_outputs import (
    ExternalOutputSource,
    capture_external_outputs,
)
from automationbench_v1.contracts.invocation_inventory import capture_invocation_inventory
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState


def test_actual_http_native_inventory_and_external_fields_survive_reload(tmp_path):
    asyncio.run(_qualify(tmp_path))


def _safe_material(source):
    raw = json.loads(source.source_json)
    return {
        key: raw[key] for key in ("task_evidence", "tool_execution_events", "state_write_receipts")
    }


async def _qualify(tmp_path):
    public = next(
        task
        for task in AutomationBenchTaskset(AutomationBenchConfig(domains=["simple"])).load()
        if task.data.task_name == "simple.email_sf_contact_assistant_update"
    )
    # Normalize initial schema defaults once so read-only equality is meaningful.
    initial = WorldState.model_validate(public.data.initial_state).model_dump(mode="json")
    data = public.data.model_copy(update={"initial_state": initial})
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    trace_class = cast(Any, vf.Trace[type(data), AutomationBenchState, vf.AgentConfig])
    trace = trace_class(
        episode_id="native-http-inventory",
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type="ManifestAssessmentTask", data=data),
        state=AutomationBenchState(
            world=copy.deepcopy(initial), initial_state=initial, capture_actions=True
        ),
    )
    session = RolloutSession(ModelContext("no-inference", EvalClientConfig()), trace)
    interception = cast(Any, InterceptionServer.__new__(InterceptionServer))
    interception.state_sessions = {"private-test": session}
    interception.state_service_secrets = frozenset()
    interception.state_routes = {}
    app = web.Application()
    app.router.add_get("/state", interception.handle_state_get)
    app.router.add_get("/task", interception.handle_task_get)
    app.router.add_put("/state", interception.handle_state_put)
    app.router.add_post("/tool-execution", interception.handle_tool_execution)
    async with TestServer(app) as server:
        port_file = tmp_path / "port"
        log_path = tmp_path / "mcp.log"
        with log_path.open("wb") as log:
            environment = {
                **os.environ,
                "VF_STATE_URL": str(server.make_url("/state")),
                "VF_STATE_SECRET": "private-test",
                "VF_CONFIG": "{}",
                "MCP_PORT_FILE": str(port_file),
            }
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "automationbench_v1.tools",
                env=environment,
                stdout=log,
                stderr=log,
            )
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    headers = {
                        "Accept": "application/json, text/event-stream",
                        "MCP-Protocol-Version": "2025-06-18",
                    }
                    for _ in range(150):
                        assert process.returncode is None, log_path.read_text()
                        if port_file.exists():
                            url = f"http://127.0.0.1:{port_file.read_text()}/mcp"
                            try:
                                await client.post(
                                    url,
                                    json={"jsonrpc": "2.0", "id": "ready", "method": "tools/list"},
                                    headers=headers,
                                )
                                break
                            except httpx.ConnectError:
                                pass
                        await asyncio.sleep(0.1)
                    else:
                        raise AssertionError("MCP subprocess did not become ready")

                    async def call(number, operation, params):
                        arguments = {"tool_name": operation, "arguments": canonical_json(params)}
                        original = ToolCall(
                            id=f"original-{number}",
                            name="execute_tool",
                            arguments=canonical_json(arguments),
                        )
                        node = len(trace.nodes)
                        trace.nodes.append(
                            vf.MessageNode(
                                parent=node - 1 if node else None,
                                message=AssistantMessage(content="", tool_calls=[original]),
                                sampled=True,
                            )
                        )
                        trace.calls.append(vf.ModelCall(node=node, finish_reason="tool_calls"))
                        message = ToolMessage(
                            tool_call_id=original.id, name=original.name, content=""
                        )
                        parent = f"parent-{number}"
                        for event_index, phase in enumerate(("before", "dispatch")):
                            decision = await session.handle_tool(
                                phase,
                                message,
                                request=ToolHookRequest(
                                    phase=phase,
                                    message=message,
                                    call=original,
                                    execution_id=parent,
                                    event_index=event_index,
                                    mcp_dispatch=MCPDispatch(
                                        server_name="",
                                        tool_name="execute_tool",
                                        arguments_json=canonical_json(arguments),
                                    )
                                    if phase == "dispatch"
                                    else None,
                                ),
                            )
                        response = await client.post(
                            url,
                            headers=headers,
                            json={
                                "jsonrpc": "2.0",
                                "id": number,
                                "method": "tools/call",
                                "params": {
                                    "name": "execute_tool",
                                    "arguments": arguments,
                                    "_meta": {
                                        "verifiers.execution": {
                                            "dispatch_ticket": decision["mcp_dispatch_ticket"],
                                            "parent_execution_id": parent,
                                            "transport_attempt_index": 0,
                                        }
                                    },
                                },
                            },
                        )
                        response.raise_for_status()
                        result = response.json()["result"]
                        assert not result.get("isError", False), result
                        # Independently bind the HTTP return and native receipt.
                        terminal = next(
                            event
                            for event in reversed(trace.tool_execution_events)
                            if event.source == "tool_server" and event.phase == "returned"
                        )
                        raw_result = json.loads(json.loads(terminal.receipt_json)["result_json"])
                        assert result["structuredContent"]["result"] == raw_result
                        await session.handle_tool(
                            "after",
                            message,
                            request=ToolHookRequest(
                                phase="after",
                                message=message,
                                call=original,
                                execution_id=parent,
                                event_index=2,
                                raw_result=raw_result,
                            ),
                        )

                    await call(
                        0, "gmail_get_email_by_id", {"message_id": "msg_3010", "format": "full"}
                    )
                    contacts = initial["salesforce"]["contacts"]
                    contact = next(row for row in contacts if row["first_name"] == "Rachel")
                    await call(
                        1,
                        "salesforce_contact_update",
                        {
                            "id": contact["id"],
                            "assistant_name": "Kevin Torres",
                            "assistant_email": "kevin.torres@ironclad.example.com",
                        },
                    )
            finally:
                if process.returncode is None:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), 10)
    trace.is_completed = True
    trace.ok = True
    sealed = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    raw = _safe_material(sealed)
    inventory = capture_invocation_inventory(raw, native_source=sealed)
    assert inventory.closed, inventory.reason
    assert len(inventory.entries) == len(inventory.native_coverage_pairs) == 2
    assert len({entry.invocation_id for entry in inventory.entries}) == 2
    external = capture_external_outputs(raw, ExternalOutputSource(), native_source=sealed)
    assert external.closed, external.reason
    assert {record.field: record.text for record in external.text_records} == {
        "assistant_name": "Kevin Torres",
        "assistant_email": "kevin.torres@ironclad.example.com",
    }
    assert len(external.action_relations) == 2
    assert all(relation.changed for relation in external.action_relations)
    assert {pair.parent_execution_id for pair in inventory.native_coverage_pairs} == {
        "parent-0",
        "parent-1",
    }
    assert all(pair.transport_attempt_index == 0 for pair in inventory.native_coverage_pairs)
    assert trace.tool_state_revision == len(trace.state_write_receipts) == 2
    saved = trace.model_dump_json()
    restored = trace_class.model_validate_json(saved)
    # Runtime state is deliberately not archived; restore the retained world
    # through its acknowledged action snapshot, without altering receipt bytes.
    terminal = next(
        event
        for event in reversed(restored.tool_execution_events)
        if event.source == "tool_server" and event.phase == "returned"
    )
    receipt = json.loads(terminal.receipt_json)
    capture = json.loads(receipt["evidence_json"][0])
    final = json.loads(capture["snapshots"][capture["action"]["after_digest"]])
    assert final == trace.state.world
    restored.state = AutomationBenchState(world=final, initial_state=initial)
    replay = capture_trace_source(restored, task_evidence=task.assessment_source(restored))
    replay_raw = _safe_material(replay)
    assert restored.tool_execution_events == trace.tool_execution_events
    assert capture_invocation_inventory(replay_raw, native_source=replay).closed
    assert (
        capture_external_outputs(
            replay_raw, ExternalOutputSource(), native_source=replay
        ).text_records
        == external.text_records
    )

    # An extra original call lacking host execution must keep closure open even
    # when every retained physical invocation is individually qualified.
    extra = ToolCall(
        id="unexecuted",
        name="execute_tool",
        arguments=canonical_json(
            {
                "tool_name": "gmail_get_email_by_id",
                "arguments": canonical_json({"message_id": "msg_3010"}),
            }
        ),
    )
    node = len(restored.nodes)
    restored.nodes.append(
        vf.MessageNode(
            parent=node - 1, sampled=True, message=AssistantMessage(content="", tool_calls=[extra])
        )
    )
    restored.calls.append(vf.ModelCall(node=node, finish_reason="tool_calls"))
    incomplete = capture_trace_source(restored, task_evidence=task.assessment_source(restored))
    incomplete_raw = _safe_material(incomplete)
    inventory = capture_invocation_inventory(incomplete_raw, native_source=incomplete)
    assert not inventory.closed
    assert all(entry.status == "qualified" for entry in inventory.entries)
    partial = capture_external_outputs(
        incomplete_raw, ExternalOutputSource(), native_source=incomplete
    )
    assert not partial.closed and partial.text_records == external.text_records
