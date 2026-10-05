"""Unpaid qualification of real package MCP subprocess and native receipt HTTP."""

import asyncio
import copy
import hashlib
import json
import os
import sys
from typing import Any, cast

import pytest
import verifiers.v1 as vf

from automationbench_v1.calibration.evidence import inspect_capture
from automationbench_v1.capture import SnapshotStore, raw_action_envelopes, trace_snapshot_store
from automationbench_v1.taskset import AutomationBenchConfig, AutomationBenchTaskset
from automationbench_v1.tools import AutomationBenchState


def test_package_subprocess_retains_failed_and_concurrent_action_evidence(tmp_path):
    pytest.importorskip("verifiers.v1.mcp.execution")
    asyncio.run(_qualify(tmp_path))


async def _qualify(tmp_path):
    import httpx
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    from verifiers.v1.clients import ModelContext
    from verifiers.v1.configs.client import EvalClientConfig
    from verifiers.v1.interception.server import InterceptionServer
    from verifiers.v1.session import RolloutSession

    task = AutomationBenchTaskset(AutomationBenchConfig(domains=["simple"])).load()[0]
    trace_class = cast(Any, vf.Trace[vf.TaskData, AutomationBenchState, vf.AgentConfig])
    trace = trace_class(
        episode_id="automationbench-subprocess",
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type="Task", data=vf.TaskData(prompt="qualification")),
        state=AutomationBenchState(
            world=copy.deepcopy(task.data.initial_state), capture_actions=True
        ),
    )
    session = RolloutSession(ModelContext("no-inference", EvalClientConfig()), trace)
    interception = cast(Any, InterceptionServer.__new__(InterceptionServer))
    interception.state_sessions = {"private-test": session}
    interception.state_service_secrets = frozenset()
    interception.state_routes = {}
    app = web.Application()
    barrier = asyncio.Event()
    concurrent_gets = 0
    synchronize = False

    async def get(request):
        nonlocal concurrent_gets
        response = await interception.handle_state_get(request)
        if synchronize and response.status == 200:
            concurrent_gets += 1
            if concurrent_gets == 2:
                barrier.set()
            await asyncio.wait_for(barrier.wait(), 10)
        return response

    app.router.add_get("/state", get)
    app.router.add_get("/task", interception.handle_task_get)
    app.router.add_put("/state", interception.handle_state_put)
    app.router.add_post("/tool-execution", interception.handle_tool_execution)
    async with TestServer(app) as server:
        port_file = tmp_path / "port"
        log = (tmp_path / "mcp.log").open("wb")
        environment = dict(os.environ)
        environment.update(
            VF_STATE_URL=str(server.make_url("/state")),
            VF_STATE_SECRET="private-test",
            VF_CONFIG="{}",
            MCP_PORT_FILE=str(port_file),
        )
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
                for _ in range(150):
                    assert process.returncode is None, (tmp_path / "mcp.log").read_text()
                    if port_file.exists():
                        url = f"http://127.0.0.1:{port_file.read_text()}/mcp"
                        try:
                            await client.post(
                                url,
                                json={"jsonrpc": "2.0", "id": "ready", "method": "tools/list"},
                                headers={"Accept": "application/json, text/event-stream"},
                            )
                            break
                        except httpx.ConnectError:
                            pass
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("MCP subprocess did not become ready")

                async def call(identifier, arguments):
                    response = await client.post(
                        url,
                        json={
                            "jsonrpc": "2.0",
                            "id": identifier,
                            "method": "tools/call",
                            "params": {"name": "execute_tool", "arguments": arguments},
                        },
                        headers={
                            "Accept": "application/json, text/event-stream",
                            "MCP-Protocol-Version": "2025-06-18",
                        },
                    )
                    response.raise_for_status()
                    return response.json()["result"]

                def update(phone):
                    return {
                        "tool_name": "salesforce_contact_update",
                        "arguments": json.dumps({"id": "003001", "phone": phone}),
                    }

                assert not (await call(1, update("first"))).get("isError", False)
                retained_count = len(trace.tool_execution_events)
                rejected = await call("schema-rejected", {"tool_name": "salesforce_contact_update"})
                assert rejected["isError"]
                # MCP parameter validation rejects before the native tool wrapper.
                # Observed invocation coverage cannot prove coverage of all agent calls.
                assert len(trace.tool_execution_events) == retained_count
                baseline = copy.deepcopy(trace.state.world)
                failure = await call(
                    2, {"tool_name": "salesforce_contact_update", "arguments": "{"}
                )
                assert failure["isError"]
                assert trace.state.world == baseline
                synchronize = True
                results = await asyncio.wait_for(
                    asyncio.gather(call(3, update("left")), call(4, update("right"))), 20
                )
                assert all(not result.get("isError", False) for result in results)
                assert trace.tool_state_revision == 3
                terminal = [
                    json.loads(event.receipt_json)
                    for event in trace.tool_execution_events
                    if event.phase != "dispatch"
                ]
                assert len(terminal) == 4
                assert len({receipt["invocation_id"] for receipt in terminal}) == 4
                failed = next(receipt for receipt in terminal if receipt["phase"] == "raised")
                assert failed["state_persistence"] == "not_attempted"
                parallel = [
                    receipt
                    for receipt in terminal
                    if receipt["state_read_revision"] == 1 and receipt["phase"] == "returned"
                ]
                assert len(parallel) == 2
                assert sorted(receipt["state_conflict"] for receipt in parallel) == [False, True]
                assert sorted(receipt["state_write_revision"] for receipt in parallel) == [2, 3]
                indices = []
                store = SnapshotStore(raw_action_envelopes(terminal))
                for receipt in terminal:
                    assert len(receipt["evidence_json"]) == 1
                    material = json.loads(receipt["evidence_json"][0])
                    assert material["kind"] == "automationbench_raw_action"
                    action = material["action"]
                    assert action["status"] == (
                        "raised" if receipt["phase"] == "raised" else "returned"
                    )
                    assert action["result_json"] == receipt["result_json"]
                    if receipt["phase"] == "raised":
                        assert json.loads(action["error_json"])["type"] == "JSONDecodeError"
                    assert (
                        json.loads(action["arguments_json"])
                        == json.loads(receipt["arguments_json"])["kwargs"]
                    )
                    # Each world travels once per rollout (full or as a verified patch).
                    assert set(material["snapshots"]) | set(material.get("patches", {})) <= {
                        action["before_digest"],
                        action["after_digest"],
                    }
                    for digest, encoded in material["snapshots"].items():
                        assert hashlib.sha256(encoded.encode()).hexdigest() == digest
                    for digest in (action["before_digest"], action["after_digest"]):
                        assert store.text(digest) is not None
                    if receipt in parallel:
                        indices.append(action["occurrence_index"])
                assert indices == [1, 1]  # Local occurrence collisions are not invocation identity.
                last = next(receipt for receipt in parallel if receipt["state_write_revision"] == 3)
                after = json.loads(last["evidence_json"][0])
                assert trace.state.world == json.loads(store.text(after["action"]["after_digest"]))
                saved = tmp_path / "native-trace.json"
                saved.write_text(trace.model_dump_json())
                restored = trace_class.model_validate_json(saved.read_text())
                assert restored.tool_execution_events == trace.tool_execution_events
                assert restored.state_write_receipts == trace.state_write_receipts
                wire_episode = vf.WireEpisode.model_validate(
                    {
                        "task": trace.task.model_dump(mode="json"),
                        "traces": [restored.model_dump(mode="json")],
                    }
                )
                inspection = inspect_capture(wire_episode)
                assert inspection.observed_invocations_complete
                assert inspection.observed_invocations == 4
                assert len(inspection.actions) == 4
                assert len({item.invocation_id for item in inspection.actions}) == 4
                # Native runtime state is intentionally excluded from serialization;
                # exact action snapshots remain in the independently retained receipts.
                retained_last = next(
                    json.loads(event.receipt_json)
                    for event in restored.tool_execution_events
                    if event.phase == "returned"
                    and json.loads(event.receipt_json)["state_write_revision"] == 3
                )
                restored_material = json.loads(retained_last["evidence_json"][0])
                restored_store = trace_snapshot_store(restored.tool_execution_events)
                assert (
                    json.loads(restored_store.text(restored_material["action"]["after_digest"]))
                    == trace.state.world
                )
                forged = json.loads(saved.read_text())
                forged["state_write_receipts"] = []
                with pytest.raises(ValueError):
                    trace_class.model_validate(forged)
        finally:
            if process.returncode is None:
                process.terminate()
                await asyncio.wait_for(process.wait(), 10)
            log.close()
