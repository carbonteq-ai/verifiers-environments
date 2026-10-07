"""Deterministic simulation: equal actions on equal worlds give equal tool results."""

import asyncio
import json
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import verifiers.v1 as vf

from automationbench import sim_runtime
from automationbench.schema.world import WorldState
from automationbench_v1.limited_tools import (
    AutomationBenchLimitedToolset,
    AutomationBenchLimitedToolsetConfig,
)
from automationbench_v1.simulation import world_clock_base
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState

TASK = "simple.email_sf_log_task"
TOOLS = ("gmail_find_email", "gmail_send_email", "salesforce_task_create")


def attempt(deterministic: bool) -> tuple[AutomationBenchLimitedToolset, AutomationBenchState]:
    """Set up a fresh rollout of TASK, as each attempt of a group does."""

    config = AutomationBenchConfig(
        domains=["simple"],
        task=AutomationBenchTaskConfig(toolset="limited_zapier", deterministic_world=deterministic),
    )
    task = next(t for t in AutomationBenchTaskset(config).load() if t.data.task_name == TASK)
    trace = vf.Trace(
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type=type(task).__name__, data=task.data),
        state=AutomationBenchState(),
    )
    asyncio.run(task.setup(trace, None))  # type: ignore[arg-type]
    tools = AutomationBenchLimitedToolset(AutomationBenchLimitedToolsetConfig(allowed_tools=TOOLS))
    tools._inert_state = trace.state
    return tools, cast(AutomationBenchState, trace.state)


def create_task(tools: AutomationBenchLimitedToolset) -> Any:
    return tools.invoke("salesforce_task_create", subject="Email received from client", contact_id="003002")


def send_email(tools: AutomationBenchLimitedToolset) -> Any:
    return tools.invoke("gmail_send_email", to="natalie@example.com", subject="Logged", body="Done.")


def test_sim_runtime_is_the_standard_library_outside_a_call():
    assert not sim_runtime.active()
    before = datetime.now(UTC)
    assert before - timedelta(seconds=5) < sim_runtime.now(UTC) < before + timedelta(seconds=5)
    assert sim_runtime.uuid4() != sim_runtime.uuid4()
    assert sim_runtime.rng() is random._inst  # type: ignore[attr-defined]


def test_sim_runtime_call_is_seeded_and_its_clock_advances_per_reading():
    clock = datetime(2025, 3, 10, 9, 0, tzinfo=UTC)
    with sim_runtime.simulated_call("seed", clock):
        first = (sim_runtime.uuid4(), sim_runtime.now(UTC), sim_runtime.now(UTC), sim_runtime.rng().random())
    with sim_runtime.simulated_call("seed", clock):
        second = (sim_runtime.uuid4(), sim_runtime.now(UTC), sim_runtime.now(UTC), sim_runtime.rng().random())
    assert first == second
    assert isinstance(first[0], uuid.UUID) and first[0].version == 4
    assert first[1] == clock + timedelta(microseconds=1) < first[2]
    with sim_runtime.simulated_call("other", clock):
        assert sim_runtime.uuid4() != first[0]
    assert not sim_runtime.active()


def test_same_calls_on_same_world_give_identical_results_and_worlds():
    a_tools, a = attempt(deterministic=True)
    b_tools, b = attempt(deterministic=True)
    assert a.world == b.world and a.world_clock == b.world_clock

    assert create_task(a_tools) == create_task(b_tools)
    assert send_email(a_tools) == send_email(b_tools)
    assert a.world == b.world
    assert a.world_revision == b.world_revision == 2


def test_wall_clock_mode_still_differs_between_attempts():
    a_tools, _ = attempt(deterministic=False)
    b_tools, _ = attempt(deterministic=False)
    assert create_task(a_tools) != create_task(b_tools)


def test_reads_do_not_shift_later_results():
    a_tools, a = attempt(deterministic=True)
    b_tools, b = attempt(deterministic=True)
    b_tools.invoke("gmail_find_email", query="project timeline")
    b_tools.invoke("gmail_find_email", query="Natalie")
    assert b.world_revision == 0
    assert create_task(a_tools) == create_task(b_tools)
    assert a.world == b.world


def test_repeated_create_mints_a_new_identifier():
    tools, state = attempt(deterministic=True)
    first, second = json.loads(create_task(tools)), json.loads(create_task(tools))
    assert first != second
    world = WorldState.model_validate(state.world)
    created = [task for task in world.salesforce.tasks if task.subject == "Email received from client"]
    assert len({task.id for task in created}) == 2


def test_world_clock_is_the_tasks_declared_time_or_utc_midnight():
    declared = {"meta": {"current_time": "2025-03-10T14:30:00Z"}}
    assert world_clock_base(declared) == datetime(2025, 3, 10, 14, 30, tzinfo=UTC)
    today = datetime(2026, 10, 6, 17, 45, tzinfo=UTC)
    assert world_clock_base({}, today=today) == datetime(2026, 10, 6, tzinfo=UTC)
    _, state = attempt(deterministic=True)
    stored = WorldState.model_validate(state.world).meta.current_time
    assert stored == datetime.fromisoformat(cast(str, state.world_clock))
