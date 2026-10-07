"""Signed-in SDK composition helpers; ordinary inference is deliberately absent."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import verifiers.v1 as vf
from verifiers.v1.clients import Client
from verifiers.v1.clients.client import RelayReply
from verifiers.v1.configs.client import EvalClientConfig
from verifiers.v1.dialects import Dialect
from verifiers.v1.envs.single_agent.env import SingleAgentEnvConfig
from verifiers.v1.graph import PendingTurn
from verifiers.v1.types import Response, SamplingConfig
from verifiers.v1.utils.loaders import harness_class, load_environment

from ..taskset import AutomationBenchTask, AutomationBenchTaskConfig
from .collector import _write_native, collect
from .inventory import TaskInventory, content_digest
from .models import CalibrationManifest
from .runner import native_binding

SIGNED_IN_ROUTE_IDENTITY = "codex-sdk:chatgpt"


def sdk_client_config() -> EvalClientConfig:
    """An inert native context identity, never a model endpoint or credential."""
    return EvalClientConfig(base_url="http://127.0.0.1/sdk-only", api_key_var="VF_SDK_NO_API")


def validate_sdk_binding(
    inventory: TaskInventory,
    manifest: CalibrationManifest,
    env_config: SingleAgentEnvConfig,
    client: EvalClientConfig,
    sampling: vf.Sampling,
) -> dict:
    """Bind SDK execution without claiming intercepted model-call limits.

    Native compile/pairing checks still apply, including NEEDS_CONTAINER. The
    controller owns signed-in authentication; ordinary inference is prohibited.
    Source/tool-catalog/account qualification remains a separate release gate.
    """
    manifest = CalibrationManifest.model_validate(manifest.model_dump())
    inventory = TaskInventory.model_validate(inventory.model_dump())
    manifest.validate_inventory(inventory)
    if not isinstance(env_config, SingleAgentEnvConfig):
        raise TypeError("SDK calibration requires a native single-agent environment")
    if env_config.id or env_config.taskset.id != "automationbench-v1":
        raise ValueError("SDK collection requires the AutomationBench single-agent composition")
    if native_binding(env_config, client, sampling) != manifest.native_config:
        raise ValueError("resolved SDK native binding differs from manifest")
    if (
        manifest.provider_model_id != "gpt-6-luna"
        or manifest.route_identity != SIGNED_IN_ROUTE_IDENTITY
    ):
        raise ValueError("SDK collection requires the exact signed-in Luna route")
    if manifest.limits.max_output_tokens != 16_384:
        raise ValueError("SDK reference collection requires the declared 16384 output threshold")
    if client.model_dump(mode="json") != sdk_client_config().model_dump(mode="json"):
        raise ValueError("SDK context must use the inert client identity")
    if sampling.model_dump(exclude_none=True):
        raise ValueError("SDK sampling is harness-owned; ordinary provider overrides are refused")
    if (
        manifest.limits.cost_measurement != "unavailable"
        or manifest.limits.cost_ceiling_usd is not None
    ):
        raise ValueError("subscription usage cannot claim an API currency ceiling")
    agent = env_config.agent
    if (
        env_config.retries.max_retries != 0
        or agent.retries.max_retries != 0
        or agent.model is not None
        or agent.client is not None
        or agent.sampling is not None
    ):
        raise ValueError("SDK collection refuses model overrides and hidden attempt retries")
    if env_config.max_concurrent_agents != 1 or env_config.interception.type != "server":
        raise ValueError("SDK collection requires one solver and native host interception")
    if (
        agent.max_turns != manifest.limits.max_turns
        or agent.max_output_tokens != manifest.limits.max_output_tokens
    ):
        raise ValueError("SDK configured limits differ from manifest")
    harness = agent.harness
    if harness is None or harness.id != "codex-sdk":
        raise ValueError("SDK collection requires the native codex-sdk harness")
    values = harness.model_dump(mode="json")
    if (
        not isinstance(values.get("auth_file"), str)
        or not values["auth_file"]
        or values.get("qualification_endpoint") is not None
        or harness.env
        or harness.forward_env
        or harness.skills
        or harness.disabled_tools
    ):
        raise ValueError("SDK collection requires exclusive protected auth and fixed capabilities")
    if not Path(values["auth_file"]).is_absolute():
        raise ValueError("protected SDK auth file must use an absolute controller path")
    if values.get("output_budget") != manifest.limits.max_output_tokens:
        raise ValueError("SDK output threshold differs from manifest")
    timeout = values.get("timeout")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout <= 0
        or timeout > manifest.limits.attempt_timeout_seconds
    ):
        raise ValueError("SDK timeout exceeds the bounded attempt duration")
    runtime = agent.runtime.model_dump(mode="json")
    if runtime.get("type") not in {"subprocess", "docker"}:
        raise ValueError("SDK controller runtime must be explicit local subprocess or Docker")
    needs_container = harness_class(harness.id).NEEDS_CONTAINER
    if needs_container and runtime["type"] == "subprocess":
        raise ValueError("SDK NEEDS_CONTAINER admission is not yet qualified for host execution")
    tasks = {task.task_name: task for task in inventory.tasks}
    for selected in manifest.tasks:
        config = tasks[selected.task_name].config
        if config.get("toolset", "zapier") != "zapier":
            raise ValueError("SDK reference collection currently qualifies the zapier toolset only")
        servers = AutomationBenchTask.toolsets(AutomationBenchTaskConfig.model_validate(config))
        expected_approvals = {
            server.server_name: ("execute_tool", "search_tools") for server in servers
        }
        if values.get("approved_mcp_tools") != {
            name: list(names) for name, names in expected_approvals.items()
        }:
            raise ValueError("SDK approval policy differs from actual benchmark MCP server names")
        tools = config.get("tools", {})
        if (
            config.get("capture_actions") is not True
            or tools.get("colocated") is not False
            or tools.get("runtime", {}).get("type") != "subprocess"
            or tools.get("url") is not None
        ):
            raise ValueError("SDK collection requires host-owned benchmark MCP action capture")
        if any(
            config.get(key)
            for key in ("judges", "assessments", "credit_rules", "rewards", "metrics", "stops")
        ):
            raise ValueError("SDK reference collection refuses auxiliary inference")
    return {
        "route_identity": SIGNED_IN_ROUTE_IDENTITY,
        "sdk_version_required": "0.160.0",
        "runtime_version_required": "0.160.0",
        "billing": "existing_subscription_allowance_or_credits_service_selected",
        "automatic_purchase_or_reset": False,
        "ordinary_api_inference": "refused",
        "output_limit": {
            "value": manifest.limits.max_output_tokens,
            "enforcement": "observed_sdk_thread_threshold_with_possible_overshoot",
        },
        "native_max_turns": {
            "configured": agent.max_turns,
            "model_call_enforcement": "unavailable",
            "sdk_agent_turns_per_attempt": 1,
        },
        "controller_requires_container": needs_container,
    }


async def run_collection_sdk(
    inventory: TaskInventory,
    manifest: CalibrationManifest,
    env_config: SingleAgentEnvConfig,
    client: EvalClientConfig,
    sampling: vf.Sampling,
    directory: Path,
    *,
    attempts_per_task: int = 1,
    stop_on_execution_error: bool = False,
) -> tuple:
    """Reuse native serving and the durable collector; never copy its scheduler."""
    policy = validate_sdk_binding(inventory, manifest, env_config, client, sampling)
    directory = directory.resolve()
    for name, value in (
        ("inventory.json", inventory.model_dump(mode="json")),
        ("manifest.json", manifest.model_dump(mode="json")),
        ("sdk-execution-policy.json", policy),
    ):
        path = directory / name
        if path.exists():
            import json

            if content_digest(json.loads(path.read_bytes())) != content_digest(value):
                raise ValueError("persisted SDK collection inputs changed")
        else:
            _write_native(path, value)
    env = load_environment(env_config)
    ctx = vf.ModelContext(manifest.provider_model_id, client, sampling)

    def factory(config):
        if config.model_dump(mode="json") != client.model_dump(mode="json"):
            raise ValueError("SDK collection requested an unqualified inference client")
        return SdkOnlyClient()

    async with env.serving(client_factory=factory):
        return await collect(
            env,
            ctx,
            inventory,
            manifest,
            directory,
            attempts_per_task=attempts_per_task,
            stop_on_execution_error=stop_on_execution_error,
        )


class SdkOnlyClient(Client):
    """Reject accidental policy/judge/API relay; SDK owns account authentication.

    Native interception still hosts task state and benchmark tool receipts. Its
    inference interface must never silently dispatch through another provider.
    This client owns no credentials, HTTP connection or fallback implementation.
    """

    async def get_response(
        self,
        dialect: Dialect,
        body: dict,
        sampling: SamplingConfig,
        session_id: str | None = None,
        turn: PendingTurn | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        raise RuntimeError("signed-in SDK collection refuses ordinary model inference")

    async def relay(
        self,
        dialect: Dialect,
        body: dict,
        session_id: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> RelayReply:
        raise RuntimeError("signed-in SDK collection refuses API relay")

    async def relay_aux(
        self,
        dialect: Dialect,
        route: str,
        body: dict,
        headers: Mapping[str, str] | None = None,
    ) -> dict:
        raise RuntimeError("signed-in SDK collection refuses auxiliary API inference")

    async def close(self) -> None:
        pass
