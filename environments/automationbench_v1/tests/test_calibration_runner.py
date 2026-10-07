"""Resolved native configuration admission, without credentials or provider calls."""

import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
import verifiers.v1 as vf
from verifiers.v1.envs.single_agent.env import SingleAgentEnvConfig
from verifiers.v1.utils.loaders import resolve_env_config

from automationbench_v1.calibration.budgets import (
    output_budget_eligibility,
    reconcile_sdk_responses,
    retain_sdk_budget,
    summarize_sdk_usage,
)
from automationbench_v1.calibration.cost import CostPolicy
from automationbench_v1.calibration.inventory import content_digest, freeze_inventory
from automationbench_v1.calibration.models import CollectionLimits, TaskSelection, plan_collection
from automationbench_v1.calibration.runner import (
    native_binding,
    persist_inputs,
    validate_binding,
    validate_price_snapshot,
)
from automationbench_v1.calibration.sdk_runner import (
    SIGNED_IN_ROUTE_IDENTITY,
    SdkOnlyClient,
    run_collection_sdk,
    sdk_client_config,
    validate_sdk_binding,
)
from automationbench_v1.taskset import AutomationBenchConfig


def test_sdk_client_refuses_policy_and_auxiliary_api_dispatch():
    from verifiers.v1.dialects.responses import ResponsesDialect

    async def exercise():
        client = SdkOnlyClient()
        dialect = ResponsesDialect()
        with pytest.raises(RuntimeError, match="ordinary model inference"):
            await client.get_response(dialect, {}, vf.Sampling(max_tokens=16384))
        with pytest.raises(RuntimeError, match="API relay"):
            await client.relay(dialect, {})
        with pytest.raises(RuntimeError, match="auxiliary API inference"):
            await client.relay_aux(dialect, "/count_tokens", {})
        await client.close()

    asyncio.run(exercise())


@pytest.fixture
def sdk_binding(binding):
    pytest.importorskip("verifiers.v1.harnesses.codex_sdk")
    inventory, original, config, _client, _sampling, _policy = binding
    data = config.model_dump(mode="json")
    data["agent"]["harness"] = {
        "id": "codex-sdk",
        "auth_file": "/protected/auth.json",
        "timeout": original.limits.attempt_timeout_seconds / 2,
        "output_budget": 16384,
        "approved_mcp_tools": {"": ("execute_tool", "search_tools")},
    }
    data["agent"]["max_output_tokens"] = 16384
    config = cast(SingleAgentEnvConfig, resolve_env_config(data))
    client, sampling = sdk_client_config(), vf.Sampling.model_validate({})
    body = original.model_dump(mode="json", exclude={"digest"})
    body.update(
        provider_model_id="gpt-6-luna",
        route_identity=SIGNED_IN_ROUTE_IDENTITY,
        native_config=native_binding(config, client, sampling),
    )
    body["limits"].update(
        max_output_tokens=16384, cost_measurement="unavailable", cost_ceiling_usd=None
    )
    manifest = type(original).model_validate({**body, "digest": content_digest(body)})
    return inventory, manifest, config, client, sampling


def test_sdk_binding_distinguishes_observed_limits_and_container_admission(
    sdk_binding, monkeypatch
):
    CodexSdkHarness = pytest.importorskip("verifiers.v1.harnesses.codex_sdk").CodexSdkHarness

    inventory, manifest, config, client, sampling = sdk_binding
    result = validate_sdk_binding(inventory, manifest, config, client, sampling)
    assert result["ordinary_api_inference"] == "refused"
    assert result["output_limit"]["enforcement"].endswith("possible_overshoot")
    assert result["native_max_turns"]["model_call_enforcement"] == "unavailable"
    data = config.model_dump(mode="json")
    data["agent"]["runtime"] = {"type": "subprocess"}
    host = cast(SingleAgentEnvConfig, resolve_env_config(data))
    body = manifest.model_dump(mode="json", exclude={"digest"})
    body["native_config"] = native_binding(host, client, sampling)
    host_manifest = type(manifest).model_validate({**body, "digest": content_digest(body)})
    monkeypatch.setattr(CodexSdkHarness, "NEEDS_CONTAINER", True)
    with pytest.raises(ValueError, match="NEEDS_CONTAINER"):
        validate_sdk_binding(inventory, host_manifest, host, client, sampling)


@pytest.mark.parametrize(
    "change",
    [
        "route",
        "model",
        "retries",
        "auxiliary",
        "output",
        "client",
        "sampling",
        "forward_env",
        "mcp_name",
        "threshold",
    ],
)
def test_sdk_binding_rejects_bypasses_before_serving(sdk_binding, change):
    inventory, manifest, config, client, sampling = sdk_binding
    body = manifest.model_dump(mode="json", exclude={"digest"})
    env = config.model_dump(mode="json")
    if change == "route":
        body["route_identity"] = "openrouter"
    elif change == "model":
        body["provider_model_id"] = "other"
    elif change == "retries":
        env["agent"]["retries"]["max_retries"] = 1
    elif change == "auxiliary":
        env["agent"]["client"] = {"type": "eval"}
    elif change == "output":
        env["agent"]["harness"]["output_budget"] = 32768
    elif change == "mcp_name":
        env["agent"]["harness"]["approved_mcp_tools"] = {
            "automationbench": ["execute_tool", "search_tools"]
        }
    elif change == "threshold":
        body["limits"]["max_output_tokens"] = 32768
        env["agent"]["max_output_tokens"] = 32768
        env["agent"]["harness"]["output_budget"] = 32768
    elif change == "forward_env":
        env["agent"]["harness"]["forward_env"] = ["PRIVATE"]
    elif change == "client":
        client = vf.EvalClientConfig(
            base_url="https://api.openai.com/v1", api_key_var="OPENAI_API_KEY"
        )
    elif change == "sampling":
        sampling = vf.Sampling(max_tokens=16384)
    config = cast(SingleAgentEnvConfig, resolve_env_config(env))
    body["native_config"] = native_binding(config, client, sampling)
    manifest = type(manifest).model_validate({**body, "digest": content_digest(body)})
    with pytest.raises(ValueError):
        validate_sdk_binding(inventory, manifest, config, client, sampling)


def test_sdk_composition_reuses_collector_and_immutable_inputs(sdk_binding, tmp_path, monkeypatch):
    from contextlib import asynccontextmanager

    import automationbench_v1.calibration.sdk_runner as module

    inventory, manifest, _config, client, _sampling = sdk_binding
    seen = []

    class Environment:
        @asynccontextmanager
        async def serving(self, *, client_factory):
            assert isinstance(client_factory(client), SdkOnlyClient)
            with pytest.raises(ValueError, match="unqualified inference"):
                client_factory(vf.EvalClientConfig())
            yield self

    environment = Environment()

    async def collected(
        env, ctx, inv, planned, directory, *, attempts_per_task, stop_on_execution_error
    ):
        assert env is environment and inv is inventory and planned is manifest
        assert ctx.model == "gpt-6-luna" and attempts_per_task == 1
        assert stop_on_execution_error is False
        seen.append(directory)
        return ()

    monkeypatch.setattr(module, "load_environment", lambda _: environment)
    monkeypatch.setattr(module, "collect", collected)
    asyncio.run(run_collection_sdk(inventory, manifest, _config, client, _sampling, tmp_path))
    assert seen == [tmp_path.resolve()]
    assert (
        json.loads((tmp_path / "sdk-execution-policy.json").read_text())[
            "automatic_purchase_or_reset"
        ]
        is False
    )
    assert not (tmp_path / "cost-policy.json").exists()
    (tmp_path / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="inputs changed"):
        asyncio.run(run_collection_sdk(inventory, manifest, _config, client, _sampling, tmp_path))
    assert len(seen) == 1


def test_sdk_budget_replaces_cumulative_updates_across_turns_and_keeps_unknowns():
    def event(output, turn="first", thread="thread-a"):
        total = {
            "inputTokens": 100,
            "cachedInputTokens": 20,
            "outputTokens": output,
            "reasoningOutputTokens": 5,
        }
        return {
            "method": "thread/tokenUsage/updated",
            "params": {
                "threadId": thread,
                "turnId": turn,
                "tokenUsage": {"total": total, "last": {"outputTokens": 999999}},
            },
        }

    result = summarize_sdk_usage(
        [event(10), event(10), event(20, "second")], thread_id="thread-a", fresh_thread=True
    )
    assert result.reported_counts["outputTokens"] == 20
    assert result.output_remaining == 16364
    assert result.reasoning_inclusion == "unqualified"
    assert result.reported_counts["totalTokens"] is None
    over = summarize_sdk_usage([event(16390)], thread_id="thread-a", fresh_thread=True)
    assert over.threshold_reached and over.overshoot_tokens == 6
    assert over.enforcement == "observed_threshold"
    missing_after_crossing = summarize_sdk_usage(
        [event(16390), event(None)], thread_id="thread-a", fresh_thread=True
    )
    assert missing_after_crossing.status == "unavailable"
    assert missing_after_crossing.output_remaining is None
    assert missing_after_crossing.threshold_reached is True
    assert missing_after_crossing.overshoot_tokens is None
    assert missing_after_crossing.observed_output_lower_bound == 16390
    assert missing_after_crossing.observed_overshoot_lower_bound == 6
    assert (
        output_budget_eligibility(
            missing_after_crossing, final_usage_confirmed=False, reasoning_inclusion_confirmed=False
        )[0]
        == "over_budget"
    )
    assert (
        output_budget_eligibility(
            result, final_usage_confirmed=True, reasoning_inclusion_confirmed=False
        )[0]
        == "unverified"
    )
    assert (
        output_budget_eligibility(
            result, final_usage_confirmed=True, reasoning_inclusion_confirmed=True
        )[0]
        == "within_budget"
    )
    rescue = summarize_sdk_usage(
        [event(20)], thread_id="thread-a", fresh_thread=True, output_budget=32768
    )
    assert (
        output_budget_eligibility(
            rescue, final_usage_confirmed=True, reasoning_inclusion_confirmed=True
        )[1]
        == "different_attempt_budget"
    )
    missing = summarize_sdk_usage([event(None)], thread_id="thread-a", fresh_thread=True)
    assert missing.status == "unavailable" and missing.output_remaining is None
    resumed = summarize_sdk_usage([event(20)], thread_id="thread-a", fresh_thread=False)
    assert resumed.status == "unavailable"
    assert resumed.reason == "existing_thread_requires_retained_baseline"
    with pytest.raises(ValueError, match="regressed"):
        summarize_sdk_usage([event(20), event(10)], thread_id="thread-a", fresh_thread=True)
    with pytest.raises(ValueError, match="identity"):
        summarize_sdk_usage([event(10, thread="another")], thread_id="thread-a", fresh_thread=True)


def test_sdk_budget_retention_keeps_original_events_on_bad_accounting():
    events = [
        {"kind": "thread_started", "response": {"thread": {"id": "a"}}},
        {
            "kind": "event",
            "event": {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": "wrong",
                    "tokenUsage": {"total": {"outputTokens": 10}},
                },
            },
        },
    ]
    info = {"codex_sdk": {"events": events, "fresh_thread_requested": True}}
    original = json.dumps(info)
    retain_sdk_budget(info, 16384)
    assert info["automationbench_output_budget"]["status"] == "invalid"
    assert json.dumps({"codex_sdk": info["codex_sdk"]}) == original
    restored = json.loads(json.dumps(info))
    retain_sdk_budget(restored, 16384)
    assert restored == info


def _response_accounting_events():
    def counts(input_tokens, output, reasoning):
        return {
            "inputTokens": input_tokens,
            "cachedInputTokens": 0,
            "cacheWriteInputTokens": 0,
            "outputTokens": output,
            "reasoningOutputTokens": reasoning,
            "totalTokens": input_tokens + output,
        }

    events = []
    for response_id, usage, total in (
        ("r1", counts(10, 7, 3), counts(10, 7, 3)),
        ("r2", counts(20, 5, 2), counts(30, 12, 5)),
    ):
        events.extend(
            [
                {
                    "method": "rawResponse/completed",
                    "params": {
                        "threadId": "a",
                        "turnId": "t",
                        "responseId": response_id,
                        "usage": usage,
                        "usageMetadata": None,
                    },
                },
                {
                    "method": "thread/tokenUsage/updated",
                    "params": {
                        "threadId": "a",
                        "turnId": "t",
                        "tokenUsage": {"total": total},
                    },
                },
            ]
        )
    events.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": "a",
                "turn": {"id": "t", "status": "completed"},
            },
        }
    )
    return events


def _reconcile(events, **overrides):
    return reconcile_sdk_responses(
        events,
        **{
            "thread_id": "a",
            "fresh_thread": True,
            "sdk_version": "0.160.0",
            "raw_response_events_requested": True,
            **overrides,
        },
    )


def test_sdk_response_accounting_reconciles_reports_and_input_dimensions():
    events = _response_accounting_events()
    result = _reconcile(events)
    assert result.status == "reconciled"
    assert result.response_ids == ("r1", "r2")
    assert result.reported_counts["outputTokens"] == 12
    assert result.reported_counts["reasoningOutputTokens"] == 5
    assert result.reasoning_inclusion == "reported_output_detail"
    assert (
        result.first_response_input,
        result.maximum_response_input,
        result.cumulative_response_input,
    ) == (10, 20, 30)
    events.insert(1, json.loads(json.dumps(events[0])))
    assert _reconcile(events) == result  # retransmission is not another response.


@pytest.mark.parametrize(
    "case",
    [
        "missing_usage",
        "missing_final_usage",
        "missing_raw",
        "mismatch",
        "bad_reasoning",
        "bool_count",
        "duplicate_conflict",
        "foreign_turn",
        "no_final_counter",
        "no_terminal",
        "event_after_terminal",
        "old_journal",
        "different_version",
        "counter_reset",
        "counter_foreign_turn",
        "terminal_id_missing",
        "terminal_id_empty",
        "recovered_error",
        "nonretry_error",
    ],
)
def test_sdk_response_accounting_declines_incomplete_or_conflicting_evidence(case):
    events = _response_accounting_events()
    overrides = {}
    if case == "missing_usage":
        events[0]["params"]["usage"] = None
    elif case == "missing_final_usage":
        events[2]["params"]["usage"] = None
    elif case == "missing_raw":
        events.pop(0)
    elif case == "mismatch":
        events[3]["params"]["tokenUsage"]["total"]["outputTokens"] = 13
    elif case == "bad_reasoning":
        events[0]["params"]["usage"]["reasoningOutputTokens"] = 8
    elif case == "bool_count":
        events[0]["params"]["usage"]["cachedInputTokens"] = False
    elif case == "duplicate_conflict":
        duplicate = json.loads(json.dumps(events[0]))
        duplicate["params"]["usage"]["cachedInputTokens"] = False
        events.insert(1, duplicate)
    elif case == "foreign_turn":
        events[0]["params"]["turnId"] = "other"
    elif case == "no_final_counter":
        events.pop(3)
    elif case == "no_terminal":
        events.pop()
    elif case == "event_after_terminal":
        events.append(events[1])
    elif case == "old_journal":
        overrides["raw_response_events_requested"] = False
    elif case == "different_version":
        overrides["sdk_version"] = "next"
    elif case == "counter_reset":
        reset = json.loads(json.dumps(events[1]))
        reset["params"]["tokenUsage"]["total"]["outputTokens"] = 0
        events.insert(2, reset)
    elif case == "counter_foreign_turn":
        events[1]["params"]["turnId"] = "other"
    elif case == "terminal_id_missing":
        events[-1]["params"]["turn"].pop("id")
        for event in events[:-1]:
            event["params"].pop("turnId")
    elif case == "terminal_id_empty":
        events[-1]["params"]["turn"]["id"] = ""
    elif case in ("recovered_error", "nonretry_error"):
        events.insert(
            0,
            {
                "method": "error",
                "params": {
                    "threadId": "a",
                    "turnId": "t",
                    "willRetry": case == "recovered_error",
                    "error": {"message": "partial response failed", "codexErrorInfo": None},
                },
            },
        )
    assert _reconcile(events, **overrides).status == "unavailable"


@pytest.fixture
def binding():
    config = cast(
        SingleAgentEnvConfig,
        resolve_env_config(
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
                    "max_turns": 4,
                    "max_output_tokens": 256,
                    "harness": {"id": "codex", "version": "0.147.0", "multi_agent": False},
                    "runtime": {
                        "type": "docker",
                        "allow": [],
                        "image": "python@sha256:" + "a" * 64,
                        "listener_image": "python@sha256:" + "b" * 64,
                        "network_setup_image": "alpine@sha256:" + "c" * 64,
                    },
                },
            }
        ),
    )
    inventory = freeze_inventory(
        cast(AutomationBenchConfig, config.taskset),
        source_identity={"fixture": True, "price_snapshot_digest": "unpaid-fixture"},
    )
    client = vf.EvalClientConfig(
        base_url="https://openrouter.ai/api/v1",
        api_key_var="OPENROUTER_API_KEY",
    )
    sampling = vf.Sampling.model_validate(
        {
            "max_tokens": 64,
            "extra_body": {
                "store": False,
                "provider": {
                    "only": ["openai"],
                    "order": ["openai"],
                    "allow_fallbacks": False,
                    "require_parameters": True,
                },
            },
        }
    )
    policy = CostPolicy(
        max_usd="4.99",
        context_token_ceiling=1_050_000,
        input_usd_per_million="0.25",
        output_usd_per_million="0.75",
        price_provenance="unpaid-fixture",
        accepted_response_models=("gpt-6-luna",),
        max_output_tokens_per_session=256,
    )
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
        route_identity="unpaid-fixture",
        provider_model_id=policy.model,
        native_config=native_binding(config, client, sampling),
        scorer_revision="fixture",
        limits=CollectionLimits(
            max_concurrent=1,
            max_total_attempts=1,
            max_elapsed_seconds=60,
            attempt_timeout_seconds=30,
            max_turns=4,
            max_output_tokens=256,
            cost_measurement="priced_usage",
            cost_ceiling_usd=4.99,
        ),
    )
    return inventory, manifest, config, client, sampling, policy


def test_binding_admits_matching_values_and_persisted_inputs_cannot_change(tmp_path, binding):
    inventory, manifest, _config, _client, _sampling, policy = binding
    validate_binding(*binding)
    persist_inputs(tmp_path, inventory, manifest, policy)
    persist_inputs(tmp_path, inventory, manifest, policy)
    with pytest.raises(ValueError, match="persisted collection inputs changed"):
        persist_inputs(tmp_path, inventory, manifest, replace(policy, max_usd="5.00"))


def test_price_snapshot_binds_bytes_route_tiers_and_freshness(tmp_path, binding):
    current = datetime.now(UTC)
    record = {
        "model_id": "openai/gpt-6-luna",
        "source_url": "https://openrouter.ai/api/v1/models/openai/gpt-6-luna/endpoints",
        "collected_at": current.isoformat(),
        "endpoint": {
            "model_id": "openai/gpt-6-luna",
            "tag": "openai",
            "provider_name": "OpenAI",
            "status": 0,
            "context_length": 1_050_000,
            "max_completion_tokens": 128_000,
            "pricing": {
                "prompt": "0.0000001",
                "completion": "0.0000005",
                "input_cache_read": "0.00000001",
                "input_cache_write": "0.000000125",
                "overrides": [
                    {
                        "prompt": "0.0000002",
                        "completion": "0.00000075",
                        "input_cache_read": "0.00000002",
                        "input_cache_write": "0.00000025",
                        "min_prompt_tokens": 272000,
                    }
                ],
            },
        },
    }
    path = tmp_path / "price.json"

    def write():
        raw = json.dumps(record).encode()
        path.write_bytes(raw)
        return replace(
            binding[-1],
            price_provenance=hashlib.sha256(raw).hexdigest(),
            input_usd_per_million="0.47",
        )

    policy = write()
    source = validate_price_snapshot(path, policy, 64, now=current)
    assert source["raw_utf8"].encode() == path.read_bytes()
    assert source["sha256"] == policy.price_provenance
    with pytest.raises(ValueError, match="categories"):
        validate_price_snapshot(
            path, replace(policy, input_usd_per_million="0.25"), 64, now=current
        )
    with pytest.raises(ValueError, match="one hour"):
        validate_price_snapshot(path, policy, 64, now=current + timedelta(hours=2))
    with pytest.raises(ValueError, match="completion limit"):
        validate_price_snapshot(path, policy, 128001, now=current)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="bytes"):
        validate_price_snapshot(path, policy, 64, now=current)
    record["endpoint"]["tag"] = "openai/fast"
    with pytest.raises(ValueError, match="standard OpenAI"):
        validate_price_snapshot(path, write(), 64, now=current)
    record["endpoint"]["tag"] = "openai"
    record["endpoint"]["pricing"]["unknown_billing"] = "0.1"
    with pytest.raises(ValueError, match="billing category"):
        validate_price_snapshot(path, write(), 64, now=current)


@pytest.mark.parametrize(
    "change", ["retry", "tokens", "client", "price", "spend", "output", "sampling"]
)
def test_mismatched_bindings_reject_before_runtime_or_send(binding, change):
    inventory, manifest, config, client, sampling, policy = binding
    if change == "retry":
        config = config.model_copy(deep=True)
        config.agent.retries.max_retries = 1
    elif change == "tokens":
        config = config.model_copy(deep=True)
        config.agent.max_output_tokens = 200
    elif change == "client":
        client = client.model_copy(update={"base_url": "https://unqualified.example/v1"})
    elif change == "price":
        policy = replace(policy, price_provenance="other")
    elif change == "spend":
        policy = replace(policy, max_usd="5.00")
    elif change == "output":
        policy = replace(policy, max_output_tokens_per_session=512)
    else:
        sampling = sampling.model_copy(update={"max_tokens": 128})
    # Retain matching config provenance so tests exercise runtime/cost admission,
    # rather than all failing at the preceding equality check.
    body = manifest.model_dump(mode="json", exclude={"digest"})
    body["native_config"] = native_binding(config, client, sampling)
    manifest = type(manifest).model_validate({**body, "digest": content_digest(body)})
    if change == "sampling":
        # This remains a valid explicitly revised per-response limit within budget.
        validate_binding(inventory, manifest, config, client, sampling, policy)
        return
    with pytest.raises(ValueError):
        validate_binding(inventory, manifest, config, client, sampling, policy)


def test_existing_remote_tool_url_cannot_bypass_host_owned_capture(binding):
    inventory, manifest, config, client, sampling, policy = binding
    config = config.model_copy(deep=True)
    taskset = cast(AutomationBenchConfig, config.taskset)
    taskset.task.tools.url = "http://unqualified.example/mcp"
    changed = freeze_inventory(taskset, source_identity=inventory.source_identity)
    body = manifest.model_dump(mode="json", exclude={"digest"})
    body["inventory_digest"] = changed.digest
    body["tasks"][0]["task_digest"] = changed.tasks[0].digest
    body["native_config"] = native_binding(config, client, sampling)
    manifest = type(manifest).model_validate({**body, "digest": content_digest(body)})
    with pytest.raises(ValueError, match="host-owned action capture"):
        validate_binding(changed, manifest, config, client, sampling, policy)
