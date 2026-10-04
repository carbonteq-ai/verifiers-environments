from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf

from automationbench.schema.world import WorldState
from automationbench_v1.api_tools import AutomationBenchApiToolset
from automationbench_v1.limited_tools import AutomationBenchLimitedToolset
from automationbench_v1.scoring import score_world
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
    _with_world_time,
)
from automationbench_v1.tools import AutomationBenchState, AutomationBenchToolset

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("timestamp", ["2026-04-15T09:00:00Z", "2026-01-27T09:00:00", "2026-04-15T09:00:00+05:00"])
def test_world_time_context_preserves_declared_clock_without_hidden_task_data(timestamp: str) -> None:
    prompt = [{"role": "system", "content": "Workflow instructions"}, {"role": "user", "content": "Check recent hires"}]
    result = _with_world_time(prompt, timestamp)
    assert prompt[0]["content"] == "Workflow instructions"
    assert result[1] == prompt[1]
    assert timestamp in result[0]["content"]
    assert "host clock does not define task time" in result[0]["content"]
    assert ("timezone is unspecified" in result[0]["content"]) == (timestamp == "2026-01-27T09:00:00")


@pytest.mark.parametrize("timestamp", [None, "", "2026-04-15", "invalid", "2026-99-15T09:00:00Z"])
def test_world_time_context_rejects_missing_or_invalid_clock(timestamp: Any) -> None:
    with pytest.raises(ValueError, match="explicit ISO datetime"):
        _with_world_time([{"role": "system", "content": "Instructions"}], timestamp)


def test_world_time_context_is_opt_in_and_bound_to_loaded_task() -> None:
    config = AutomationBenchConfig(domains=["hr"], task_names=["hr.i9_verification_tracking"])
    [original] = AutomationBenchTaskset(config).load()
    [contextual] = AutomationBenchTaskset(config.model_copy(update={"task": AutomationBenchTaskConfig(world_time_context=True)})).load()
    original_prompt = cast(Any, original.data.prompt)
    contextual_prompt = cast(Any, contextual.data.prompt)
    assert "Simulation context:" not in original_prompt[0].content
    assert contextual.data.initial_state["meta"]["current_time"] in contextual_prompt[0].content
    assert contextual_prompt[1].content == original_prompt[1].content
    assert contextual.data.assertions == original.data.assertions


def test_world_time_context_does_not_validate_unselected_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    from automationbench_v1 import taskset

    rows = [
        {"task": "hr.untimed", "prompt": [], "info": {}},
        {
            "task": "hr.timed",
            "prompt": [{"role": "system", "content": "Instructions"}, {"role": "user", "content": "Task"}],
            "info": {"initial_state": {"meta": {"current_time": "2026-04-15T09:00:00Z"}}},
        },
    ]
    monkeypatch.setattr(taskset, "get_domain_dataset", lambda domain: rows)
    [selected] = AutomationBenchTaskset(
        AutomationBenchConfig(domains=["hr"], task_names=["hr.timed"], task=AutomationBenchTaskConfig(world_time_context=True))
    ).load()
    assert selected.data.idx == 1
    assert selected.key == "hr.timed"
    with pytest.raises(ValueError, match="explicit ISO datetime"):
        AutomationBenchTaskset(AutomationBenchConfig(domains=["hr"], task=AutomationBenchTaskConfig(world_time_context=True))).load()


def test_distribution_metadata_supports_both_online_rl_python_capsules() -> None:
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((PACKAGE_ROOT / "uv.lock").read_text(encoding="utf-8"))

    assert pyproject["project"]["requires-python"] == ">=3.12,<3.14"
    assert lock["requires-python"] == ">=3.12, <3.14"


def test_simple_taskset_preserves_typed_world_and_assertions() -> None:
    taskset = AutomationBenchTaskset(AutomationBenchConfig(domains=["simple"]))
    task = next(iter(taskset.load()))

    assert task.data.task_name == "simple.email_sf_contact_phone_update"
    assert task.data.zapier_tools == (
        "gmail_find_email",
        "gmail_get_email_by_id",
        "salesforce_find_records",
        "salesforce_contact_update",
    )
    assert task.data.assertions[0]["type"] == "salesforce_field_equals"
    prompt = cast(Any, task.data.prompt)
    assert prompt[0].content.startswith("You are a workflow automation agent")


def test_taskset_can_freeze_an_explicit_cross_domain_task_mix() -> None:
    config = AutomationBenchConfig(
        domains=["simple", "finance"],
        task_names=["simple.gmail_weekly_status", "finance.quarterly_tax_estimate"],
    )
    tasks = AutomationBenchTaskset(config).load()
    assert [task.data.task_name for task in tasks] == [
        "simple.gmail_weekly_status",
        "finance.quarterly_tax_estimate",
    ]
    assert [task.data.idx for task in tasks] == [62, 286]


def test_task_identity_is_stable_across_fresh_world_instances() -> None:
    config = AutomationBenchConfig(
        domains=["finance"],
        task_names=["finance.ap_aging_report"],
    )

    first = AutomationBenchTaskset(config).load()[0]
    second = AutomationBenchTaskset(config).load()[0]

    transformed = first.with_system_prompt("runtime renderer system prompt")

    assert first.key == second.key == "finance.ap_aging_report"
    assert transformed.key == first.key
    assert transformed.hash != first.hash


def test_taskset_rejects_duplicate_or_unknown_frozen_task_names() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        AutomationBenchTaskset(
            AutomationBenchConfig(task_names=["simple.gmail_weekly_status"] * 2)
        ).load()
    with pytest.raises(ValueError, match="unknown AutomationBench task_names"):
        AutomationBenchTaskset(AutomationBenchConfig(task_names=["simple.not_a_task"])).load()


def test_migrated_simple_task_matches_legacy_contract_snapshot() -> None:
    """Pin the former in-repository adapter's stable task-facing contract."""

    task = next(iter(AutomationBenchTaskset(AutomationBenchConfig(domains=["simple"])).load()))

    assert task.data.name == "simple.email_sf_contact_phone_update"
    prompt = cast(Any, task.data.prompt)
    assert [message.role for message in prompt] == ["system", "user"]
    assert prompt[1].content == (
        "Jordan Lee just emailed us with a new phone number. Can you find that email "
        "and update her phone number in Salesforce?"
    )
    assert task.data.initial_state["gmail"]["messages"][0]["id"] == "msg_3001"
    assert task.data.initial_state["salesforce"]["contacts"][0]["id"] == "003001"
    assert task.data.assertions == (
        {
            "collection": "contacts",
            "field": "phone",
            "record_id": "003001",
            "type": "salesforce_field_equals",
            "value": "+1-555-0101",
        },
    )

    before = score_world(
        world=task.data.initial_state,
        initial_state=task.data.initial_state,
        assertions=task.data.assertions,
    )
    assert (before.partial_credit, before.task_completed_correctly) == (0.0, 0.0)

    world = WorldState.model_validate(task.data.initial_state)
    world.salesforce.contacts[0].phone = "+1-555-0101"
    after = score_world(
        world=world.model_dump(mode="json"),
        initial_state=task.data.initial_state,
        assertions=task.data.assertions,
    )
    assert (after.partial_credit, after.task_completed_correctly) == (1.0, 1.0)
    assert (after.assertions_passed, after.assertions_scored, after.assertions_excluded) == (
        1,
        1,
        0,
    )


def test_dense_and_strict_scores_use_upstream_assertion_registry() -> None:
    task = next(iter(AutomationBenchTaskset(AutomationBenchConfig(domains=["simple"])).load()))
    initial = task.data.initial_state
    before = score_world(world=initial, initial_state=initial, assertions=task.data.assertions)
    assert before.partial_credit == 0.0
    assert before.task_completed_correctly == 0.0

    world = WorldState.model_validate(initial)
    world.salesforce.contacts[0].phone = "+1-555-0101"
    after = score_world(
        world=world.model_dump(mode="json"),
        initial_state=initial,
        assertions=task.data.assertions,
    )
    assert after.partial_credit == 1.0
    assert after.task_completed_correctly == 1.0
    assert after.assertions_passed == after.assertions_scored == 1


def test_default_toolset_matches_upstream_zapier_meta_tools() -> None:
    task = next(iter(AutomationBenchTaskset(AutomationBenchConfig(domains=["simple"])).load()))
    state = AutomationBenchState(
        world=task.data.initial_state, initial_state=task.data.initial_state
    )
    toolset = AutomationBenchToolset(vf.ToolsetConfig())
    toolset._inert_state = state

    search = toolset.search_tools("salesforce update contact", top_k=5)
    assert "salesforce_contact_update" in search
    result = toolset.execute_tool(
        "salesforce_contact_update",
        '{"id":"003001","phone":"+1-555-0101"}',
    )
    assert "error" not in result.lower()
    world = WorldState.model_validate(toolset.state.world)
    assert world.salesforce.contacts[0].phone == "+1-555-0101"


def test_optional_api_toolset_searches_and_mutates_per_rollout_state() -> None:
    task = next(iter(AutomationBenchTaskset(AutomationBenchConfig(domains=["simple"])).load()))
    state = AutomationBenchState(
        world=task.data.initial_state, initial_state=task.data.initial_state
    )
    toolset = AutomationBenchApiToolset(vf.ToolsetConfig())
    toolset._inert_state = state

    search = toolset.api_search("salesforce update contact", top_k=3)
    assert "salesforce" in search.lower()
    result = toolset.api_fetch(
        "PATCH",
        "https://example.my.salesforce.com/services/data/v61.0/sobjects/Contact/003001",
        body='{"Phone":"+1-555-0101"}',
    )
    assert "error" not in result.lower()
    world = WorldState.model_validate(toolset.state.world)
    assert world.salesforce.contacts[0].phone == "+1-555-0101"


def test_limited_zapier_mode_exposes_and_executes_only_task_tools() -> None:
    config = AutomationBenchConfig(
        domains=["simple"],
        task=AutomationBenchTaskConfig(toolset="limited_zapier"),
    )
    task = next(iter(AutomationBenchTaskset(config).load()))
    [toolset] = task.toolsets(AutomationBenchTaskConfig.model_validate(task.config.model_dump()))
    assert isinstance(toolset, AutomationBenchLimitedToolset)
    assert toolset.config.allowed_tools == task.data.zapier_tools

    toolset._inert_state = AutomationBenchState(
        world=task.data.initial_state,
        initial_state=task.data.initial_state,
    )
    toolset.invoke("salesforce_contact_update", id="003001", phone="+1-555-0101")
    state = cast(AutomationBenchState, toolset.state)
    world = WorldState.model_validate(state.world)
    assert world.salesforce.contacts[0].phone == "+1-555-0101"


def test_task_setup_and_finalize_put_evaluation_detail_on_trace() -> None:
    task = next(iter(AutomationBenchTaskset(AutomationBenchConfig(domains=["simple"])).load()))
    trace = vf.Trace(
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type=type(task).__name__, data=task.data),
        state=AutomationBenchState(),
    )
    asyncio.run(task.setup(trace, None))  # type: ignore[arg-type]
    state = cast(AutomationBenchState, trace.state)
    world = WorldState.model_validate(state.world)
    world.salesforce.contacts[0].phone = "+1-555-0101"
    state.world = world.model_dump(mode="json")
    asyncio.run(task.finalize(trace, None))  # type: ignore[arg-type]
    asyncio.run(task.score(cast(Any, trace)))

    assert trace.reward == 1.0
    assert trace.metrics["task_completed_correctly"] == 1.0
    assert trace.info["automationbench"]["assertions"][0]["passed"] is True


def test_calibration_capture_is_opt_in_host_material_with_explicit_coverage() -> None:
    task = AutomationBenchTaskset(
        AutomationBenchConfig(task=AutomationBenchTaskConfig(capture_actions=True))
    ).load()[0]
    trace = vf.Trace(
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type=type(task).__name__, data=task.data),
        state=AutomationBenchState(),
    )
    asyncio.run(task.setup(trace, None))  # type: ignore[arg-type]
    state = cast(AutomationBenchState, trace.state)
    assert state.capture_actions
    assert state.action_initial_digest in state.action_snapshots
    asyncio.run(task.finalize(trace, None))  # type: ignore[arg-type]
    captured = trace.info["automationbench_capture"]
    assert captured["events"] == []
    assert captured["initial_digest"] == state.action_initial_digest
    assert captured["coverage"]["native_call_alignment"] == "unavailable"
    assert captured["coverage"]["failed_mcp_retention"] == "unqualified"
    assert not AutomationBenchTaskConfig().capture_actions


def test_limited_zapier_adds_spreadsheet_search_when_ids_are_undiscoverable() -> None:
    config = AutomationBenchConfig(
        domains=["hr", "simple"],
        task_names=["hr.docusign_nda_collection", "simple.email_sf_contact_phone_update"],
        task=AutomationBenchTaskConfig(toolset="limited_zapier"),
    )
    hr_task, simple_task = AutomationBenchTaskset(config).load()
    assert hr_task.data.zapier_tools[-1] == "google_drive_find_multiple_files"
    assert "google_drive_find_multiple_files" not in simple_task.data.zapier_tools

    [toolset] = hr_task.toolsets(AutomationBenchTaskConfig.model_validate(hr_task.config.model_dump()))
    assert isinstance(toolset, AutomationBenchLimitedToolset)
    assert toolset.config.allowed_tools == hr_task.data.zapier_tools
    toolset._inert_state = AutomationBenchState(
        world=hr_task.data.initial_state,
        initial_state=hr_task.data.initial_state,
    )
    found = toolset.invoke("google_drive_find_multiple_files", title="NDA compliance tracker")
    assert "ss_nda_tracker" in found
    worksheet = toolset.invoke("google_sheets_find_worksheet", spreadsheet="ss_nda_tracker", title="Status")
    assert '"success": true' in worksheet


def test_default_toolset_keeps_upstream_tool_lists() -> None:
    config = AutomationBenchConfig(domains=["hr"], task_names=["hr.docusign_nda_collection"])
    [task] = AutomationBenchTaskset(config).load()
    assert "google_drive_find_multiple_files" not in task.data.zapier_tools


def test_turn_budget_replaces_the_upstream_fifty_turn_sentence_in_every_domain() -> None:
    domains: list[Any] = ["simple", "sales", "marketing", "operations", "support", "finance", "hr"]
    budgeted = AutomationBenchTaskset(
        AutomationBenchConfig(domains=domains, task=AutomationBenchTaskConfig(turn_budget=12))
    ).load()
    upstream = AutomationBenchTaskset(AutomationBenchConfig(domains=domains)).load()
    assert len(budgeted) == len(upstream) == 800
    for task, original in zip(budgeted, upstream, strict=True):
        system = cast(Any, task.data.prompt)[0].content
        assert "~50 tool-using turns" not in system
        assert "You have a budget of 12 tool-using turns" in system
        assert "keep your thinking brief" in system
        assert "~50 tool-using turns" in cast(Any, original.data.prompt)[0].content
        assert task.data.task_name == original.data.task_name
