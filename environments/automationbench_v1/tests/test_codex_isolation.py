"""Opt-in Codex transport isolation and authorized signed-in task qualification."""

import asyncio
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf

IMAGE = "python:3.12-slim@sha256:6b1f85a08c199d29d5b6d71ab9c27bd5b3b393492e01216a15758ff69c4be8b8"
LISTENER_IMAGE = (
    "python:3.11-alpine@sha256:f2cdc43fcddbabe870f53750cbdcc01ae4aa75b1959351252457fde88f91d20f"
)
NETWORK_IMAGE = (
    "alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8"
)


def test_collection_cli_requires_explicit_selection_and_limits():
    from automationbench_v1.calibration.cli import parser

    with pytest.raises(SystemExit):
        parser().parse_args([])


def test_collection_cli_resume_preserves_frozen_world_and_rejects_source_drift(
    monkeypatch, tmp_path
):
    pytest.importorskip("verifiers.v1.harnesses.codex_sdk")
    from automationbench_v1.calibration import cli

    auth = tmp_path / "qualification-auth.json"
    auth.write_text("qualification-only; not credentials")
    argv = [
        "--task",
        "simple.email_sf_contact_phone_update",
        "--task",
        "marketing.conversion_tracking",
        "--directory",
        str(tmp_path / "collection"),
        "--auth-file",
        str(auth),
        "--concurrency",
        "2",
        "--output-budget",
        "16384",
        "--sdk-timeout",
        "30",
        "--attempt-timeout",
        "60",
        "--total-timeout",
        "120",
    ]
    dispatched = []

    def source(snapshot=None):
        if snapshot:
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(b"fake source artifact for no-inference composition test")
        return {"test_source": "unchanged"}

    async def collect(*args, **kwargs):
        assert args[1].limits.max_concurrent == 2
        dispatched.append((args[0].digest, args[1].digest))
        return ()

    monkeypatch.setattr(cli, "source_identity", source)
    monkeypatch.setattr(cli, "run_collection_sdk", collect)
    args = cli.parser().parse_args(argv)
    first = asyncio.run(cli.run(args))
    config = cli.configuration(args)
    assert config.max_concurrent_agents == 1
    assert config.taskset.task.model_dump()["turn_budget"] is None
    assert config.taskset.task.model_dump()["world_time_context"] is False
    frozen_bytes = (args.directory / "inventory.json").read_bytes()
    monkeypatch.setattr(
        cli, "freeze_inventory", lambda *a, **k: pytest.fail("resume regenerated frozen worlds")
    )
    resumed = asyncio.run(cli.run(cli.parser().parse_args([*argv, "--resume"])))
    assert resumed == first
    assert dispatched[0] == dispatched[1]
    assert (args.directory / "inventory.json").read_bytes() == frozen_bytes
    with pytest.raises(ValueError, match="native configuration differs"):
        asyncio.run(cli.run(cli.parser().parse_args([*argv, "--resume", "--world-time-context"])))
    assert len(dispatched) == 2
    monkeypatch.setattr(cli, "source_identity", lambda: {"test_source": "changed"})
    with pytest.raises(ValueError, match="source identity changed"):
        asyncio.run(cli.run(cli.parser().parse_args([*argv, "--resume"])))
    assert len(dispatched) == 2


def test_unpaid_sdk_effective_catalog_and_hidden_input_exclusion(tmp_path):
    if os.environ.get("VF_RUN_CODEX_SDK_ISOLATION") != "1":
        pytest.skip("set VF_RUN_CODEX_SDK_ISOLATION=1 for unpaid native SDK qualification")
    pytest.importorskip("verifiers.v1.harnesses.codex_sdk")
    asyncio.run(_qualify_sdk(tmp_path))


def test_unpaid_sdk_tool_call_and_native_receipt_reload(tmp_path):
    if os.environ.get("VF_RUN_CODEX_SDK_ISOLATION") != "1":
        pytest.skip("set VF_RUN_CODEX_SDK_ISOLATION=1 for unpaid native SDK qualification")
    pytest.importorskip("verifiers.v1.harnesses.codex_sdk")
    asyncio.run(_qualify_sdk(tmp_path, joined=True))


def test_signed_in_luna_one_simple_task_debug(tmp_path):
    if os.environ.get("VF_RUN_CODEX_SIGNED_IN_DEBUG") != "1":
        pytest.skip("set VF_RUN_CODEX_SIGNED_IN_DEBUG=1 for authorized one-attempt Luna debug")
    pytest.importorskip("verifiers.v1.harnesses.codex_sdk")
    directory = Path(os.environ.get("VF_SDK_DEBUG_ARTIFACT_DIR", str(tmp_path)))
    directory.mkdir(parents=True, exist_ok=True)
    asyncio.run(_qualify_sdk(directory, signed_in=True))


def test_signed_in_luna_manifest_bound_native_collection():
    if os.environ.get("VF_RUN_CODEX_SIGNED_IN_COLLECTION") != "1":
        pytest.skip("set VF_RUN_CODEX_SIGNED_IN_COLLECTION=1 for authorized native collection")
    pytest.importorskip("verifiers.v1.harnesses.codex_sdk")
    location = os.environ.get("VF_SDK_COLLECTION_DIR")
    assert location, "an explicit fresh durable VF_SDK_COLLECTION_DIR is required"
    directory = Path(location)
    assert not directory.exists(), "new collection fixture requires a fresh explicit directory"
    asyncio.run(_qualify_sdk_collection(directory))


async def _qualify_sdk_collection(directory):
    from verifiers.v1.envs.single_agent.env import SingleAgentEnvConfig
    from verifiers.v1.utils.loaders import resolve_env_config

    import automationbench
    import automationbench_v1
    from automationbench_v1.calibration.collector import validate_episode
    from automationbench_v1.calibration.evidence import inspect_capture
    from automationbench_v1.calibration.inventory import content_digest, freeze_inventory
    from automationbench_v1.calibration.models import (
        CollectionLimits,
        TaskSelection,
        plan_collection,
    )
    from automationbench_v1.calibration.runner import native_binding
    from automationbench_v1.calibration.sdk_runner import (
        SIGNED_IN_ROUTE_IDENTITY,
        run_collection_sdk,
        sdk_client_config,
    )
    from automationbench_v1.calibration.verify import scorer_fingerprint
    from automationbench_v1.taskset import AutomationBenchConfig

    packages = {
        "verifiers_v1": Path(vf.__file__).resolve().parent,
        "automationbench_environment": Path(automationbench_v1.__file__).resolve().parent,
        "automationbench": Path(automationbench.__file__).resolve().parent,
    }
    source = {}
    for name, package in packages.items():
        files = {
            str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(package.rglob("*"))
            if path.is_file()
            and path.suffix in {".py", ".json"}
            and "__pycache__" not in path.parts
        }
        revision_result = await asyncio.to_thread(
            subprocess.run,
            ["git", "-C", str(package), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        revision = revision_result.stdout.strip()
        branch_result = await asyncio.to_thread(
            subprocess.run,
            ["git", "-C", str(package), "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        )
        branch = branch_result.stdout.strip()
        source[name] = {
            "git_revision": revision,
            "git_branch": branch,
            "source_files": files,
            "source_digest": content_digest(files),
        }
    scorer_digest = scorer_fingerprint()
    config = cast(
        SingleAgentEnvConfig,
        resolve_env_config(
            {
                "interception": {"type": "server"},
                "max_concurrent_agents": 1,
                "retries": {"max_retries": 0},
                "taskset": {
                    "id": "automationbench-v1",
                    "domains": ["simple"],
                    "task_names": ["simple.email_sf_contact_phone_update"],
                    "task": {
                        "capture_actions": True,
                        "tools": {"colocated": False, "runtime": {"type": "subprocess"}},
                    },
                },
                "agent": {
                    "max_turns": 1,
                    "max_output_tokens": 16384,
                    "retries": {"max_retries": 0},
                    "runtime": {"type": "subprocess"},
                    "timeout": {"setup": 300, "rollout": 180, "scoring": 60},
                    "harness": {
                        "id": "codex-sdk",
                        "auth_file": str(
                            Path(
                                os.environ.get("VF_SDK_AUTH_FILE", "~/.codex/auth.json")
                            ).expanduser()
                        ),
                        "timeout": 180,
                        "output_budget": 16384,
                        "approved_mcp_tools": {"": ["execute_tool", "search_tools"]},
                    },
                },
            }
        ),
    )
    inventory = freeze_inventory(
        cast(AutomationBenchConfig, config.taskset), source_identity=source
    )
    client, sampling = sdk_client_config(), vf.Sampling.model_validate({})
    manifest = plan_collection(
        inventory,
        selections=tuple(
            TaskSelection(
                task_name=task.task_name,
                task_digest=task.digest,
                family=task.task_name,
                split="development",
            )
            for task in inventory.tasks
        ),
        route_identity=SIGNED_IN_ROUTE_IDENTITY,
        native_config=native_binding(config, client, sampling),
        scorer_revision=scorer_digest,
        limits=CollectionLimits(
            max_concurrent=1,
            max_attempts_per_task=1,
            max_total_attempts=1,
            max_infrastructure_retries=0,
            max_elapsed_seconds=360,
            attempt_timeout_seconds=240,
            max_turns=1,
            max_output_tokens=16384,
            cost_measurement="unavailable",
        ),
    )
    events = await run_collection_sdk(
        inventory, manifest, config, client, sampling, directory, attempts_per_task=1
    )
    assert len(events) == 1
    event = events[0]
    assert event.episode_path
    episode, digest = validate_episode(Path(event.episode_path), inventory.tasks[0], event)
    assert digest == event.episode_digest
    inspection = inspect_capture(episode)
    summary = {
        "attempt": event.model_dump(mode="json"),
        "inventory_digest": inventory.digest,
        "manifest_digest": manifest.digest,
        "episode_digest": digest,
        "scorer_revision": scorer_digest,
        "episode_ok": episode.ok,
        "observed_invocations": inspection.observed_invocations,
        "observed_invocations_complete": inspection.observed_invocations_complete,
        "native_api": "run_collection_sdk -> Env.run_episode -> collect",
        "replayed_without_resubmission": False,
    }
    (directory / "qualification-summary.json").write_text(json.dumps(summary, indent=2))
    assert event.status == "retained", summary
    assert episode.ok
    assert inspection.observed_invocations_complete
    assert inspection.observed_invocations > 0
    journal = (directory / "attempts.jsonl").read_bytes()
    replay = await run_collection_sdk(
        inventory, manifest, config, client, sampling, directory, attempts_per_task=1
    )
    assert replay == events
    assert (directory / "attempts.jsonl").read_bytes() == journal
    summary["replayed_without_resubmission"] = True
    (directory / "qualification-summary.json").write_text(json.dumps(summary, indent=2))


def _sdk_catalog_functions(tools, namespace=None):
    for tool in tools:
        if tool["type"] == "namespace":
            yield from _sdk_catalog_functions(tool["tools"], tool["name"])
        else:
            name = tool["name"]
            if namespace and not name.startswith(f"{namespace}__"):
                name = f"{namespace}__{name}"
            yield {**tool, "name": name}


def _assert_sdk_catalog(tools, resource_admin_qualified=False):
    functions = list(_sdk_catalog_functions(tools))
    assert all(tool["type"] == "function" for tool in functions), tools
    required = {
        "mcp__automationbench__execute_tool",
        "mcp__automationbench__search_tools",
    }
    allowed = required | (
        {
            "functions__list_mcp_resources",
            "functions__list_mcp_resource_templates",
            "functions__read_mcp_resource",
        }
        if resource_admin_qualified
        else set()
    )
    names = {tool["name"] for tool in functions}
    assert required <= names <= allowed, tools


async def _qualify_sdk(tmp_path, joined=False, signed_in=False):
    import httpx
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    from verifiers.v1.clients import ModelContext
    from verifiers.v1.configs.client import EvalClientConfig
    from verifiers.v1.dialects.responses import ResponsesDialect
    from verifiers.v1.errors import HarnessError
    from verifiers.v1.interception.server import InterceptionServer
    from verifiers.v1.runtimes.subprocess import SubprocessConfig, SubprocessRuntime
    from verifiers.v1.session import RolloutSession

    from automationbench_v1.calibration.sdk_runner import SdkOnlyClient
    from automationbench_v1.taskset import AutomationBenchConfig, AutomationBenchTaskset
    from automationbench_v1.tools import AutomationBenchState

    sdk = pytest.importorskip("verifiers.v1.harnesses.codex_sdk")

    task = AutomationBenchTaskset(
        AutomationBenchConfig.model_validate(
            {"domains": ["simple"], "task": {"capture_actions": True}}
        )
    ).load()[0]
    trace_class = cast(Any, vf.Trace[vf.TaskData, AutomationBenchState, vf.AgentConfig])
    trace = trace_class(
        episode_id="unpaid-sdk-catalog",
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type="Task", data=task.data),
        state=AutomationBenchState(
            world=copy.deepcopy(task.data.initial_state), capture_actions=True
        ),
    )
    context = ModelContext("gpt-6-luna", EvalClientConfig())
    interception = cast(Any, InterceptionServer.__new__(InterceptionServer))
    interception.state_sessions = {"private-test": RolloutSession(context, trace)}
    interception.state_service_secrets = frozenset()
    interception.state_routes = {}
    shapes = []
    sdk_only = SdkOnlyClient()
    fallback_attempts = []
    resource_admin = {}

    async def provider(request):
        body = await request.json()
        if signed_in:
            fallback_attempts.append(request.path)
            await sdk_only.relay(ResponsesDialect(), body)
        encoded = json.dumps(body)
        # These values occur only in private task state, never the public request.
        if not shapes:
            assert "+1-555-0101" not in encoded
            assert "+1-555-0000" not in encoded
        assert "private-test" not in encoded
        assert "VF_STATE_SECRET" not in encoded
        assert "initial_state" not in encoded
        assert "assertions" not in encoded
        shapes.append(
            {
                "path": request.path,
                "catalogs": [
                    {"location": "tools", "tools": body.get("tools", [])},
                    *[
                        {"location": f"input[{index}].tools", "tools": item["tools"]}
                        for index, item in enumerate(body.get("input", []))
                        if item.get("type") == "additional_tools"
                    ],
                ],
                "tools": [
                    *body.get("tools", []),
                    *[
                        tool
                        for item in body.get("input", [])
                        if item.get("type") == "additional_tools"
                        for tool in item["tools"]
                    ],
                ],
                "input_roles": [item.get("role") for item in body.get("input", [])],
                "keys": sorted(body),
            }
        )
        if joined:
            # Gate the first synthetic response on the actual effective catalog.
            _assert_sdk_catalog(shapes[-1]["tools"], resource_admin_qualified=bool(resource_admin))
            response = {
                "id": f"resp_unpaid_{len(shapes)}",
                "object": "response",
                "created_at": 0,
                "model": "gpt-6-luna",
                "status": "completed",
                "error": None,
                "incomplete_details": None,
                "instructions": None,
                "metadata": {},
                "parallel_tool_calls": False,
                "temperature": 1,
                "top_p": 1,
                "tool_choice": "auto",
                "tools": [],
                "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
            }
            if len(shapes) == 1:
                call = {
                    "type": "function_call",
                    "id": "fc_unpaid",
                    "call_id": "call_unpaid",
                    "namespace": "mcp__automationbench",
                    "name": "execute_tool",
                    "status": "completed",
                    "arguments": json.dumps(
                        {
                            "tool_name": "salesforce_contact_update",
                            "arguments": json.dumps({"id": "003001", "phone": "sdk-unpaid-phone"}),
                        }
                    ),
                }
                response["output"] = [call]
                # Native function-call stream lifecycle, using the same item envelope
                # as the Responses SDK events; final text uses the native builder.
                events = [
                    {
                        "type": "response.created",
                        "response": {**response, "status": "in_progress", "output": []},
                    },
                    {
                        "type": "response.output_item.added",
                        "output_index": 0,
                        "item": {**call, "arguments": "", "status": "in_progress"},
                    },
                    {
                        "type": "response.function_call_arguments.delta",
                        "item_id": call["id"],
                        "output_index": 0,
                        "delta": call["arguments"],
                    },
                    {
                        "type": "response.function_call_arguments.done",
                        "item_id": call["id"],
                        "output_index": 0,
                        "arguments": call["arguments"],
                    },
                    {"type": "response.output_item.done", "output_index": 0, "item": call},
                    {"type": "response.completed", "response": response},
                ]
                chunks = [
                    f"data: {json.dumps({**event, 'sequence_number': index})}\n\n".encode()
                    for index, event in enumerate(events)
                ]
                chunks.append(b"data: [DONE]\n\n")
            else:
                assert len(shapes) == 2
                assert any(
                    item.get("type") == "function_call_output"
                    and item.get("call_id") == "call_unpaid"
                    for item in body["input"]
                )
                response["output"] = [
                    {
                        "type": "message",
                        "id": "msg_unpaid",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Synthetic fixture completed.",
                                "annotations": [],
                            }
                        ],
                    }
                ]
                chunks = ResponsesDialect().stream_events(response)
            return web.Response(body=b"".join(chunks), content_type="text/event-stream")
        return web.json_response(
            {
                "error": {
                    "message": "intentional unpaid catalog stop",
                    "type": "invalid_request_error",
                    "code": "model_error",
                }
            },
            status=400,
        )

    app = web.Application()
    app.router.add_get("/state", interception.handle_state_get)
    app.router.add_get("/task", interception.handle_task_get)
    app.router.add_put("/state", interception.handle_state_put)
    app.router.add_post("/tool-execution", interception.handle_tool_execution)
    app.router.add_post("/v1/responses", provider)
    async with TestServer(app) as server:
        port_file = tmp_path / "sdk-mcp-port"
        log = (tmp_path / "sdk-mcp.log").open("wb")
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
        runtime = SubprocessRuntime(SubprocessConfig())
        await runtime.start()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                for _ in range(150):
                    assert process.returncode is None, (tmp_path / "sdk-mcp.log").read_text()
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
                    pytest.fail("SDK qualification MCP subprocess never became ready")

                async def resource_rpc(method, params=None):
                    response = await client.post(
                        url,
                        json={
                            "jsonrpc": "2.0",
                            "id": method,
                            "method": method,
                            "params": params or {},
                        },
                        headers={
                            "Accept": "application/json, text/event-stream",
                            "MCP-Protocol-Version": "2025-06-18",
                        },
                    )
                    response.raise_for_status()
                    return response.json()

                resources = await resource_rpc("resources/list")
                templates = await resource_rpc("resources/templates/list")
                read = await resource_rpc("resources/read", {"uri": "file:///etc/hostname"})
                assert resources["result"]["resources"] == []
                assert templates["result"]["resourceTemplates"] == []
                assert "error" in read
                resource_admin.update(
                    resources_empty=True,
                    templates_empty=True,
                    local_uri_read_rejected=True,
                    configured_servers=["automationbench"],
                )
            harness_config: dict[str, Any] = {
                "timeout": 180 if signed_in else 90,
                "output_budget": 16384,
                "approved_mcp_tools": {"automationbench": ["execute_tool", "search_tools"]},
            }
            if signed_in:
                harness_config["auth_file"] = str(
                    Path(os.environ.get("VF_SDK_AUTH_FILE", "~/.codex/auth.json")).expanduser()
                )
            else:
                harness_config["qualification_endpoint"] = str(server.make_url("/v1"))
            harness = sdk.CodexSdkHarness(sdk.CodexSdkHarnessConfig.model_validate(harness_config))
            assert harness.NEEDS_CONTAINER  # No change to normal production admission.
            await harness.setup(runtime)
            await task.setup(trace, runtime)
            session = await harness.session(
                context, trace, runtime, "unused", "unused", {"automationbench": url}, task.data
            )
            error = None
            if joined or signed_in:
                try:
                    await session.turn()
                except HarnessError as caught:
                    error = caught
            else:
                with pytest.raises(HarnessError):
                    await session.turn()
            await session.close()
            if signed_in:
                await task.finalize(trace, runtime)
                trace.info["sdk_debug_result"] = {
                    "task_name": task.data.task_name,
                    "model": "gpt-6-luna",
                    "attempts": 1,
                    "partial_credit": await task.partial_credit(trace),
                    "outcome_metrics": await task.outcome_metrics(trace),
                    "ordinary_api_fallback_attempts": len(fallback_attempts),
                    "attempt_error": type(error).__name__ if error else None,
                }
            saved = tmp_path / "sdk-native-trace.json"
            saved.write_text(trace.model_dump_json())
            restored = trace_class.model_validate_json(saved.read_text())
            assert restored.info["codex_sdk"] == trace.info["codex_sdk"]
            events = restored.info["codex_sdk"]["events"]
            (tmp_path / "sdk-qualification.json").write_text(
                json.dumps(
                    {
                        "request_shapes": shapes,
                        "events": events,
                        "resource_admin_qualification": resource_admin,
                    },
                    indent=2,
                )
            )
            durable_root = os.environ.get("VF_SDK_QUALIFICATION_ARTIFACT_DIR")
            if durable_root:
                retained = Path(durable_root) / f"{tmp_path.parent.name}-{tmp_path.name}"
                retained.mkdir(parents=True, exist_ok=True)
                for name in ("sdk-native-trace.json", "sdk-qualification.json", "sdk-mcp.log"):
                    shutil.copyfile(tmp_path / name, retained / name)
            if signed_in:
                assert not fallback_attempts
                assert restored.info["sdk_debug_result"] == trace.info["sdk_debug_result"]
                if error:
                    raise error
                assert any(event["kind"] == "finished" and event["ok"] for event in events)
                return
            if error:
                raise error
            assert shapes, events
            assert len(shapes) == (2 if joined else 1)
            assert any(
                event["kind"] == "thread_started"
                and event["response"]["thread"]["environments"] == []
                for event in events
            )
            assert restored.info["codex_sdk"]["model_request_boundaries"] == "unavailable"
            _assert_sdk_catalog(shapes[0]["tools"], resource_admin_qualified=bool(resource_admin))
            if joined:
                assert trace.root_reply == "Synthetic fixture completed."
                assert trace.state.world["salesforce"]["contacts"][0]["phone"] == "sdk-unpaid-phone"
                assert restored.tool_execution_events == trace.tool_execution_events
                assert restored.state_write_receipts == trace.state_write_receipts
                terminal = [
                    json.loads(event.receipt_json)
                    for event in restored.tool_execution_events
                    if event.phase == "returned"
                ]
                assert len(terminal) == 1
                assert terminal[0]["state_persistence"] == "applied"
                assert terminal[0]["evidence_json"]
                assert restored.info["codex_sdk"]["mcp_item_execution_join"] == "unqualified"
            else:
                assert not trace.tool_execution_events
        finally:
            await sdk_only.close()
            await runtime.teardown()
            if process.returncode is None:
                process.terminate()
                await asyncio.wait_for(process.wait(), 10)
            log.close()


def test_unpaid_codex_clean_container_and_gateway(monkeypatch, tmp_path):
    if os.environ.get("VF_RUN_CODEX_ISOLATION") != "1":
        pytest.skip("set VF_RUN_CODEX_ISOLATION=1 for clean-container, unpaid integration")
    pytest.importorskip("verifiers.v1.mcp.execution")
    asyncio.run(_qualify(monkeypatch, tmp_path))


async def _qualify(monkeypatch, tmp_path):
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    from verifiers.v1.clients.client import Client
    from verifiers.v1.configs.client import EvalClientConfig
    from verifiers.v1.errors import model_error
    from verifiers.v1.harnesses.codex.harness import ACP_BIN, ACP_VERSION, CodexHarness
    from verifiers.v1.harnesses.node import NODE_BIN_DIR
    from verifiers.v1.utils.loaders import load_environment, resolve_env_config

    shapes = []
    isolation = []
    model_metadata_requests = []
    redactions = []
    acp_diagnostics = []
    helper_provenance = {}
    for image in (LISTENER_IMAGE, NETWORK_IMAGE):
        process = await asyncio.create_subprocess_exec(
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            "{{json .RepoDigests}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        helper_provenance[image] = {
            "observed_local_repo_digests": json.loads(stdout) if process.returncode == 0 else [],
            "source_pinning": "immutable_digest",
        }

    class UnpaidClient(Client):
        async def get_response(self, dialect, body, sampling, **kwargs):
            record(dialect, body)
            raise model_error("deliberate unpaid qualification stop", status_code=400)

        async def relay(self, dialect, body, **kwargs):
            record(dialect, body)
            raise model_error("deliberate unpaid qualification stop", status_code=400)

    def record(dialect, body):
        def tool_shape(item):
            shape = {"type": item.get("type"), "keys": sorted(item)}
            if isinstance(item.get("tools"), list):
                shape["members"] = [tool_shape(child) for child in item["tools"]]
            return shape

        shapes.append(
            {
                "dialect": type(dialect).__name__,
                "endpoint": dialect.upstream_path,
                "keys": sorted(body),
                "model": body.get("model"),
                "stream": body.get("stream"),
                "max_output_tokens": body.get("max_output_tokens"),
                "store": body.get("store"),
                "parallel_tool_calls": body.get("parallel_tool_calls"),
                "reasoning": body.get("reasoning"),
                "tool_choice": body.get("tool_choice"),
                "include": body.get("include"),
                "client_metadata_keys": sorted(body.get("client_metadata", {})),
                "client_metadata_value_types": {
                    key: type(value).__name__
                    for key, value in body.get("client_metadata", {}).items()
                },
                "prompt_cache_key_type": type(body.get("prompt_cache_key")).__name__,
                "request_json_bytes": len(json.dumps(body, ensure_ascii=False).encode()),
                "input_json_bytes": len(json.dumps(body.get("input"), ensure_ascii=False).encode()),
                "instructions_bytes": len(str(body.get("instructions", "")).encode()),
                "tools_json_bytes": len(
                    json.dumps(body.get("tools", []), ensure_ascii=False).encode()
                ),
                "tools": [item.get("type") for item in body.get("tools", [])],
                "tool_structure": [tool_shape(item) for item in body.get("tools", [])],
                "input_content_types": sorted(
                    {
                        part.get("type", "untyped")
                        for item in body.get("input", [])
                        if isinstance(item, dict) and isinstance(item.get("content"), list)
                        for part in item["content"]
                        if isinstance(part, dict)
                    }
                ),
                "provider": body.get("provider"),
                "input_shape": type(body.get("input")).__name__,
                "input_items": [
                    {"type": item.get("type"), "role": item.get("role")}
                    for item in body.get("input", [])
                    if isinstance(item, dict)
                ],
            }
        )

    original = CodexHarness.prepare_acp

    async def inspect(self, ctx, trace, runtime, endpoint, secret, mcp_urls, data):
        redactions.append(secret)
        config = await original(self, ctx, trace, runtime, endpoint, secret, mcp_urls, data)
        probe = r"""
import importlib.util, json, os, pathlib, urllib.request, urllib.error, urllib.parse
paths = ["/home/hammad/projects/verifiers-environments", "/home/hammad/projects/rl",
 "/home/hammad/.config/posttrain/config.toml", "/home/hammad/projects/ai-infra/.state/secrets",
 "/var/run/docker.sock"]
out = {"hidden_paths": {p: pathlib.Path(p).exists() for p in paths},
 "environment_package_importable": importlib.util.find_spec("automationbench_v1") is not None,
 "env_secret_keys": sorted(k for k in os.environ if k in {
 "OPENAI_API_KEY", "OPENROUTER_API_KEY", "VF_STATE_SECRET", "VF_STATE_URL"}),
 "private_routes": {}, "home_exists": pathlib.Path(os.environ["CODEX_HOME"]).exists()}
base = urllib.parse.urlsplit(os.environ["PROBE_ENDPOINT"])
origin = urllib.parse.urlunsplit((base.scheme, base.netloc, "", "", ""))
for route in ["/state", "/task", "/tool-execution"]:
 request = urllib.request.Request(origin + route,
  headers={"Authorization": "Bearer " + os.environ["PROBE_MODEL_BEARER"]},
  data=b"{}" if route == "/tool-execution" else None)
 try:
  with urllib.request.urlopen(request, timeout=10) as response:
   out["private_routes"][route] = response.status
 except urllib.error.HTTPError as error:
  out["private_routes"][route] = error.code
print(json.dumps(out))
"""
        result = await runtime.run(
            ["python", "-c", probe],
            {**config.env, "PROBE_ENDPOINT": endpoint, "PROBE_MODEL_BEARER": secret},
        )
        assert result.exit_code == 0, result.stderr
        inspected = json.loads(result.stdout)
        assert not any(inspected["hidden_paths"].values())
        assert not inspected["environment_package_importable"]
        assert inspected["env_secret_keys"] == []
        assert inspected["private_routes"] == {"/state": 401, "/task": 401, "/tool-execution": 401}
        assert inspected["home_exists"]
        isolation.append(inspected)
        if os.environ.get("VF_CODEX_ACP_DIAGNOSTICS") != "1":
            return config
        rpc_probe = r"""
import json, os, selectors, signal, subprocess, sys, time
p = subprocess.Popen(sys.argv[1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
 stderr=subprocess.DEVNULL, text=True, start_new_session=True)
selector = selectors.DefaultSelector()
selector.register(p.stdout, selectors.EVENT_READ)
out = []
try:
 for identifier, method, params in [
  (1, "initialize", {"protocolVersion":1, "clientCapabilities":{}}),
  (2, "session/new", {"cwd":os.getcwd(), "mcpServers":[]})]:
  p.stdin.write(json.dumps({"jsonrpc":"2.0", "id":identifier, "method":method, "params":params})+"\n")
  p.stdin.flush()
  deadline = time.monotonic()+20
  while time.monotonic()<deadline:
   if not selector.select(max(0, deadline-time.monotonic())):
    out.append({"id":identifier,"timeout":True}); break
   line=p.stdout.readline()
   if not line:
    out.append({"id":identifier,"eof":True}); break
   item=json.loads(line)
   if item.get("id")==identifier:
    out.append(item); break
  if out[-1].get("error") or out[-1].get("timeout") or out[-1].get("eof"):
   break
finally:
 selector.close()
 try: os.killpg(p.pid, signal.SIGTERM)
 except ProcessLookupError: pass
 try: p.wait(timeout=5)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid, signal.SIGKILL); p.wait()
print(json.dumps(out))
"""
        rpc = await runtime.run(
            [
                "python",
                "-c",
                rpc_probe,
                f"{NODE_BIN_DIR}/node",
                ACP_BIN.format(version=self.config.version, acp_version=ACP_VERSION),
            ],
            config.env,
        )
        assert rpc.exit_code == 0, rpc.stderr
        acp_diagnostics.extend(json.loads(rpc.stdout))
        return config

    monkeypatch.setattr(CodexHarness, "prepare_acp", inspect)
    config = resolve_env_config(
        {
            "interception": {"type": "server"},
            "taskset": {
                "id": "automationbench-v1",
                "domains": ["simple"],
                "task_names": ["simple.email_sf_contact_phone_update"],
                "task": {
                    "capture_actions": True,
                    "tools": {"colocated": False, "runtime": {"type": "subprocess"}},
                },
            },
            "agent": {
                "max_turns": 1,
                "harness": {"id": "codex", "version": "0.147.0", "multi_agent": False},
                "runtime": {
                    "type": "docker",
                    "image": IMAGE,
                    "listener_image": LISTENER_IMAGE,
                    "network_setup_image": NETWORK_IMAGE,
                    "allow": [],
                    "cpu": 2,
                    "memory": 2,
                },
                "timeout": {"setup": 300, "rollout": 90, "scoring": 60},
            },
        }
    )
    env = load_environment(config)

    async def models(request):
        model_metadata_requests.append({"method": request.method, "path": request.path})
        return web.json_response(
            {
                "object": "list",
                "data": [
                    {
                        "id": "openai/gpt-6-luna",
                        "object": "model",
                        "created": 0,
                        "owned_by": "qualification",
                        "max_model_len": 1050000,
                    }
                ],
            }
        )

    metadata_app = web.Application()
    metadata_app.router.add_get("/v1/models", models)
    async with TestServer(metadata_app) as metadata_server:
        context = vf.ModelContext(
            "openai/gpt-6-luna",
            EvalClientConfig(
                base_url=str(metadata_server.make_url("/v1")),
                api_key_var="VF_UNPAID_MISSING_API_KEY",
            ),
            vf.Sampling.model_validate(
                {
                    "max_tokens": 64,
                    "reasoning_effort": "low",
                    "extra_body": {
                        "store": False,
                        "parallel_tool_calls": False,
                        "provider": {
                            "only": ["openai"],
                            "order": ["openai"],
                            "allow_fallbacks": False,
                            "require_parameters": True,
                        },
                    },
                }
            ),
        )
        async with env.serving(client_factory=lambda config: UnpaidClient()):
            episode = await env.run_episode(next(iter(env.taskset.load())), context)
    error_messages = []
    for trace in episode.traces:
        for error in trace.errors:
            message = error.message
            for secret in redactions:
                message = message.replace(secret, "[REDACTED_MODEL_BEARER]")
            error_messages.append(re.sub(r"Bearer [^\s\"']+", "Bearer [REDACTED]", message))
    (tmp_path / "qualification.json").write_text(
        json.dumps(
            {
                "request_shapes": shapes[:1],
                "request_count": len(shapes),
                "isolation": isolation,
                "main_image": IMAGE,
                "helper_images": helper_provenance,
                "model_metadata_requests": model_metadata_requests,
                "redacted_trace_error_messages": error_messages,
                "acp_diagnostics": json.loads(
                    json.dumps(acp_diagnostics).replace(redactions[0], "[REDACTED_MODEL_BEARER]")
                )
                if redactions
                else acp_diagnostics,
                "episode_ok": episode.ok,
                "episode_error_count": len(episode.errors),
                "trace_error_types": [
                    [error.type for error in trace.errors] for trace in episode.traces
                ],
            },
            indent=2,
        )
    )
    assert isolation, (
        "Codex preparation never reached isolated execution",
        error_messages,
    )
    assert shapes, (
        "Actual Codex process never reached unpaid injected inference client",
        error_messages,
    )
    assert all(item["endpoint"] == "/responses" for item in shapes)
    assert all(item["model"] == "openai/gpt-6-luna" for item in shapes)
