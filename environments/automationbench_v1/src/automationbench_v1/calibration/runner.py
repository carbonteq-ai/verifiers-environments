"""Host composition for a manifest-bound, guarded Luna reference collection."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import verifiers.v1 as vf
from verifiers.v1.configs.client import EvalClientConfig
from verifiers.v1.envs.single_agent.env import SingleAgentEnvConfig
from verifiers.v1.utils.loaders import load_environment

from .collector import _write_native, collect
from .cost import CostLedger, CostPolicy, GuardedEvalClient
from .inventory import TaskInventory, content_digest
from .models import CalibrationManifest


def validate_price_snapshot(
    path: Path, policy: CostPolicy, per_response_cap: int, *, now: datetime | None = None
) -> dict:
    """Bind public endpoint metadata to conservative billing bounds before launch.

    This verifies a snapshot, not account access or provider enforcement. Sum the
    largest prompt/read/write rates rather than assuming their token categories
    are exclusive. Paid provider tools remain forbidden by the dispatch guard.
    """
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != policy.price_provenance:
        raise ValueError("price snapshot bytes differ from policy provenance")
    record = json.loads(raw)
    if not isinstance(record, dict):
        raise TypeError("price snapshot must be an object")
    endpoint = record.get("endpoint")
    if (
        record.get("model_id") != policy.model
        or record.get("source_url")
        != "https://openrouter.ai/api/v1/models/openai/gpt-6-luna/endpoints"
        or not isinstance(endpoint, dict)
        or endpoint.get("model_id") != policy.model
        or endpoint.get("tag") != "openai"
        or endpoint.get("provider_name") != "OpenAI"
        or endpoint.get("status") != 0
        or type(endpoint.get("context_length")) is not int
        or endpoint["context_length"] != policy.context_token_ceiling
    ):
        raise ValueError("price snapshot differs from exact standard OpenAI endpoint")
    collected = datetime.fromisoformat(record["collected_at"])
    current = now or datetime.now(UTC)
    if (
        collected.tzinfo is None
        or current.tzinfo is None
        or not (timedelta(0) <= current - collected <= timedelta(hours=1))
    ):
        raise ValueError("price snapshot must be timezone-aware and at most one hour old")
    if (
        type(per_response_cap) is not int
        or per_response_cap <= 0
        or type(endpoint.get("max_completion_tokens")) is not int
        or per_response_cap > endpoint["max_completion_tokens"]
    ):
        raise ValueError("response cap exceeds documented provider completion limit")
    pricing = endpoint.get("pricing")
    if not isinstance(pricing, dict):
        raise TypeError("missing endpoint pricing")
    overrides = pricing.get("overrides", [])
    if not isinstance(overrides, list) or any(not isinstance(tier, dict) for tier in overrides):
        raise ValueError("invalid price tiers")
    fields = {"prompt", "completion", "input_cache_read", "input_cache_write"}
    tiers = [pricing, *overrides]
    maximum = {key: Decimal(0) for key in fields}
    for tier in tiers:
        if set(tier) - fields - {"overrides", "discount", "min_prompt_tokens", "web_search"}:
            raise ValueError("unqualified billing category in endpoint pricing")
        for key in fields:
            value = tier.get(key, pricing.get(key, "0"))
            if type(value) is not str:
                raise ValueError("token prices must be decimal strings")
            rate = Decimal(value)
            if not rate.is_finite() or rate < 0:
                raise ValueError("token prices must be finite and nonnegative")
            maximum[key] = max(maximum[key], rate)
    input_bound = sum((maximum[key] for key in fields - {"completion"}), Decimal(0)) * 10**6
    output_bound = maximum["completion"] * 10**6
    if (
        Decimal(policy.input_usd_per_million) < input_bound
        or Decimal(policy.output_usd_per_million) < output_bound
    ):
        raise ValueError("policy rates do not cover all documented input/output categories")
    return {"metadata": record, "raw_utf8": raw.decode("utf-8"), "sha256": policy.price_provenance}


def native_binding(
    env_config: SingleAgentEnvConfig,
    client: EvalClientConfig,
    sampling: vf.Sampling,
) -> dict:
    """Resolved values; API key names are retained, values never belong here."""
    return {
        "env": env_config.model_dump(mode="json"),
        "client": client.model_dump(mode="json"),
        "sampling": sampling.model_dump(mode="json"),
    }


def validate_binding(
    inventory: TaskInventory,
    manifest: CalibrationManifest,
    env_config: SingleAgentEnvConfig,
    client: EvalClientConfig,
    sampling: vf.Sampling,
    policy: CostPolicy,
) -> None:
    """Fail before creating runtimes or dispatching inference on mismatched limits."""
    manifest.validate_inventory(inventory)
    if not isinstance(env_config, SingleAgentEnvConfig):
        raise TypeError("calibration requires a native single-agent config")
    if native_binding(env_config, client, sampling) != manifest.native_config:
        raise ValueError("resolved native binding differs from manifest")
    if (
        manifest.provider_model_id != policy.model
        or client.base_url.rstrip("/") + "/responses" != policy.url
    ):
        raise ValueError("model or endpoint differs from guarded route")
    if manifest.limits.cost_measurement != "priced_usage" or (
        Decimal(str(manifest.limits.cost_ceiling_usd)) != Decimal(policy.max_usd)
    ):
        raise ValueError("manifest and enforced cost ceiling differ")
    if policy.max_output_tokens_per_session != manifest.limits.max_output_tokens:
        raise ValueError("hard output reservation differs from episode budget")
    if manifest.source_identity.get("price_snapshot_digest") != policy.price_provenance:
        raise ValueError("price provenance differs from frozen collection inputs")
    if env_config.id or env_config.taskset.id != "automationbench-v1":
        raise ValueError("calibration requires AutomationBench single-agent environment")
    if env_config.max_concurrent_agents != 1 or env_config.retries.max_retries != 0:
        raise ValueError("calibration cannot hide extra agent or episode attempts")
    agent = env_config.agent
    if (
        agent.retries.max_retries != 0
        or agent.model is not None
        or agent.client is not None
        or agent.sampling is not None
    ):
        raise ValueError("agent overrides or retries bypass the collection binding")
    if (
        agent.max_turns != manifest.limits.max_turns
        or agent.max_output_tokens != manifest.limits.max_output_tokens
    ):
        raise ValueError("native agent limits differ from manifest")
    if agent.harness is None or agent.harness.id != "codex":
        raise ValueError("Luna reference collection requires the qualified Codex harness")
    harness = agent.harness.model_dump(mode="json")
    if (
        harness.get("version") != "0.147.0"
        or harness.get("multi_agent") is not False
        or harness.get("env")
    ):
        raise ValueError("unqualified harness revision, fan-out or forwarded environment")
    runtime = agent.runtime.model_dump(mode="json")
    if runtime.get("type") != "docker" or runtime.get("allow") != []:
        raise ValueError("calibration requires a restricted clean Docker runtime")
    for key in ("image", "listener_image", "network_setup_image"):
        image = runtime.get(key, "")
        if not isinstance(image, str) or re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", image) is None:
            raise ValueError("all runtime images must use immutable digest selections")
    if client.api_key_var != "OPENROUTER_API_KEY" or any(
        key.lower() not in {"x-openrouter-metadata", "http-referer", "x-openrouter-title"}
        for key in client.headers
    ):
        raise ValueError("credential values cannot be retained in client configuration")
    # Exercise the same strict request policy used at actual native dispatch.
    from verifiers.v1.dialects.responses import ResponsesDialect

    body = ResponsesDialect().apply_overrides(
        {"model": "untrusted", "input": "binding-check", "stream": True},
        policy.model,
        sampling,
    )
    policy.validate_request(policy.url, body)
    if sampling.max_tokens is None or sampling.max_tokens > manifest.limits.max_output_tokens:
        raise ValueError("per-response cap exceeds reserved output budget")
    tasks = {task.task_name: task for task in inventory.tasks}
    for selected in manifest.tasks:
        config = tasks[selected.task_name].config
        tools = config.get("tools", {})
        if (
            config.get("capture_actions") is not True
            or tools.get("colocated") is not False
            or tools.get("runtime", {}).get("type") != "subprocess"
            or tools.get("url") is not None
        ):
            raise ValueError("frozen tasks require independent host-owned action capture")
        if config.get("judges") or config.get("assessments") or config.get("credit_rules"):
            raise ValueError(
                "reference collection cannot introduce unqualified auxiliary inference"
            )


def persist_inputs(
    directory: Path, inventory: TaskInventory, manifest: CalibrationManifest, policy: CostPolicy
) -> None:
    """Reopening requires identical input bytes; never overwrite campaign inputs."""
    for name, record in (
        ("inventory.json", inventory.model_dump(mode="json")),
        ("manifest.json", manifest.model_dump(mode="json")),
        ("cost-policy.json", asdict(policy)),
    ):
        path = directory / name
        if path.exists():
            import json

            if content_digest(json.loads(path.read_bytes())) != content_digest(record):
                raise ValueError("persisted collection inputs changed")
        else:
            _write_native(path, record)


async def run_collection(
    inventory: TaskInventory,
    manifest: CalibrationManifest,
    env_config: SingleAgentEnvConfig,
    client: EvalClientConfig,
    sampling: vf.Sampling,
    policy: CostPolicy,
    directory: Path,
    *,
    price_snapshot: Path,
    attempts_per_task: int = 1,
) -> tuple:
    """Credentials are host environment inputs; native serving owns client cleanup.

    Caller must additionally qualify source identities, live pricing, sandbox and
    observed provider compatibility. This binding check alone is not readiness.
    """
    validate_binding(inventory, manifest, env_config, client, sampling, policy)
    if sampling.max_tokens is None:
        raise ValueError("a response token cap is required")
    price_record = validate_price_snapshot(price_snapshot, policy, sampling.max_tokens)
    directory = directory.resolve()
    persist_inputs(directory, inventory, manifest, policy)
    price_path = directory / "price-snapshot-source.json"
    if price_path.exists():
        if content_digest(json.loads(price_path.read_bytes())) != content_digest(price_record):
            raise ValueError("persisted price snapshot changed")
    else:
        _write_native(price_path, price_record)
    env = load_environment(env_config)
    ctx = vf.ModelContext(manifest.provider_model_id, client, sampling)
    with CostLedger(directory / "cost.jsonl", policy) as ledger:

        def factory(config):
            if config.model_dump(mode="json") != client.model_dump(mode="json"):
                raise ValueError("unqualified inference client requested")
            return GuardedEvalClient(config, ledger=ledger)

        async with env.serving(client_factory=factory):
            return await collect(
                env,
                ctx,
                inventory,
                manifest,
                directory,
                attempts_per_task=attempts_per_task,
            )
