"""Actual renewal native replay keeps bounded effects distinct from full success."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
import verifiers.v1 as vf

from automationbench_v1.operations_assessments import (
    ACCESS_TASK,
    RENEWAL_TASK,
    ReviewedAccessTask,
    ReviewedRenewalTask,
)
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchData,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState


@pytest.mark.parametrize("flag,task_type,task_name", [
    ("reviewed_renewal_assessments", ReviewedRenewalTask, RENEWAL_TASK),
    ("reviewed_access_assessments", ReviewedAccessTask, ACCESS_TASK),
])
def test_loader_opt_in_selects_only_reviewed_operations(flag, task_type, task_name):
    tasks = AutomationBenchTaskset(AutomationBenchConfig(
        domains=["operations"],
        task=AutomationBenchTaskConfig(**{flag: True}),
    )).load()
    assert [task.data.task_name for task in tasks if isinstance(task, task_type)] == [
        task_name,
    ]


@pytest.mark.parametrize("task_type,task_name,expected", [
    (ReviewedRenewalTask, RENEWAL_TASK, 4),
    (ReviewedAccessTask, ACCESS_TASK, 8),
])
def test_actual_operations_native_credit_reload_and_rescore(task_type, task_name, expected):
    registry = Path("/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-policy-contracts.json")
    if not registry.exists():
        pytest.skip("retained development registry unavailable")
    case = next(item for item in json.loads(registry.read_text())["tasks"]
                if item["task_name"] == task_name)
    binding = case["source_binding"]
    raw = Path(binding["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == binding["source_episode_sha256"]
    episode = vf.WireEpisode.model_validate_json(raw)
    trace = episode.traces[0]
    data = AutomationBenchData.model_validate(episode.task.data.model_dump(mode="json"))
    task = task_type(data, AutomationBenchTaskConfig(capture_actions=True))
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state, assertions=data.assertions,
    )
    official = dict(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == official
    assert not trace.assessment_errors and not trace.credit_errors
    batch = trace.assessment_batches[-1]
    if task_name == RENEWAL_TASK:
        summary = next(item for item in batch.assessments
                       if item.signal.signal_id == "renewal.procurement_summary_correctness")
        assert summary.status == "abstained" and summary.value is None
    else:
        guard = next(item for item in batch.assessments
                     if item.signal.signal_id == "access.no_prohibited_route")
        assert guard.status == "valid" and guard.value == 1
    retained = tuple(trace.credit_assignments)
    completed = [item for item in retained if item.status == "complete"]
    assert len(completed) == expected
    if task_name == RENEWAL_TASK:
        assert sum(item.contributions[0].channel.startswith("renewal.agreement_sent:")
                   for item in completed) == 3
    else:
        assert all(item.contributions[0].channel.startswith((
            "access.create:", "access.section:", "access.denial:",
        )) for item in completed)
    assert all(item.contributions[0].recipient.kind == "execution" for item in completed)
    assert all(item.contributions[0].signal.direction == "higher" for item in completed)
    assert "assertions" not in batch.views[0].input_json
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    assert restored.traces[0].credit_assignments == trace.credit_assignments
    asyncio.run(task.score(trace))
    assert not trace.credit_errors and tuple(trace.credit_assignments) == retained
    assert Path(binding["source_episode_path"]).read_bytes() == raw
