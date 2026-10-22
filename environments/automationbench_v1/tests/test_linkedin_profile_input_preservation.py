from __future__ import annotations

import copy
import asyncio
import hashlib
import json

import pytest
import verifiers.v1 as vf

from automationbench.schema.linkedin.profile import Profile
from automationbench.schema.world import WorldState
from automationbench_v1.contracts.loader import load_task_contract
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState


def test_profile_alias_normalization_preserves_the_callers_source_dict() -> None:
    source = {
        "profile_id": "person-1",
        "first_name": "Ada",
        "last_name": "Lee",
        "profile_url": "https://example.com/profile",
        "title": "Engineer",
        "company_name": "Example",
    }
    before = copy.deepcopy(source)
    profile = Profile.model_validate(source)
    assert source == before
    assert profile.id == "person-1"
    assert profile.public_profile_url == before["profile_url"]
    assert profile.current_title == "Engineer"
    assert profile.current_company == "Example"


@pytest.mark.parametrize("name", ["sales.linkedin_job_change", "sales.linkedin_sales_prospecting"])
def test_world_construction_keeps_original_linkedin_authority_binding(name: str) -> None:
    [task] = AutomationBenchTaskset(
        AutomationBenchConfig(domains=["sales"], task_names=[name])
    ).load()
    initial = task.data.initial_state
    profiles = copy.deepcopy(initial["linkedin"]["profiles"])
    world = WorldState.model_validate(initial)
    assert initial["linkedin"]["profiles"] == profiles
    assert world.linkedin.profiles[0].public_profile_url == profiles[0].get(
        "profile_url", profiles[0].get("public_profile_url")
    )
    binding = next(
        b for b in load_task_contract(name).bindings if b.path == ("task_evidence", "initial")
    )
    canonical = json.dumps(initial, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == binding.canonical_sha256


@pytest.mark.parametrize("name", ["sales.linkedin_job_change", "sales.linkedin_sales_prospecting"])
@pytest.mark.parametrize("deterministic", [False, True])
def test_native_setup_and_validation_preserve_linkedin_public_source(
    name: str, deterministic: bool
) -> None:
    [task] = AutomationBenchTaskset(
        AutomationBenchConfig(
            domains=["sales"],
            task_names=[name],
            task=AutomationBenchTaskConfig(deterministic_world=deterministic),
        )
    ).load()
    before = copy.deepcopy(task.data.initial_state)
    trace = vf.Trace(
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type=type(task).__name__, data=task.data),
        state=AutomationBenchState(),
    )
    asyncio.run(task.validate(None))  # type: ignore[arg-type]
    asyncio.run(task.setup(trace, None))  # type: ignore[arg-type]
    assert task.data.initial_state == before
    assert trace.state.initial_state == before
