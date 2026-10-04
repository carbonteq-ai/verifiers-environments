"""Actual cash-flow native scoring keeps benchmark rewards and credit separate."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
import verifiers.v1 as vf

from automationbench_v1.finance_assessments import ReviewedCashFlowTask
from automationbench_v1.finance_evidence import TASK
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchData,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState


def test_loader_selects_only_cash_flow_with_explicit_flag():
    tasks = AutomationBenchTaskset(AutomationBenchConfig(
        domains=["finance"],
        task=AutomationBenchTaskConfig(reviewed_cash_flow_assessments=True),
    )).load()
    assert [task.data.task_name for task in tasks if isinstance(task, ReviewedCashFlowTask)] == [TASK]


def test_actual_cash_flow_native_findings_credit_reload_and_rescore():
    registry = Path("/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-policy-contracts.json")
    if not registry.exists():
        pytest.skip("retained development registry unavailable")
    case = next(item for item in json.loads(registry.read_text())["tasks"]
                if item["task_name"] == TASK)
    binding = case["source_binding"]
    raw = Path(binding["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == binding["source_episode_sha256"]
    episode = vf.WireEpisode.model_validate_json(raw)
    trace = episode.traces[0]
    data = AutomationBenchData.model_validate(episode.task.data.model_dump(mode="json"))
    task = ReviewedCashFlowTask(data, AutomationBenchTaskConfig(capture_actions=True))
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state, assertions=data.assertions,
    )
    official = dict(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == official
    assert not trace.assessment_errors and not trace.credit_errors
    batch = trace.assessment_batches[-1]
    records = {record.signal.signal_id: record for record in batch.assessments}
    assert records["forecast.ending_balance"].value == 1
    assert records["forecast.no_prohibited_claim"].value == 1
    retained_assignments = tuple(trace.credit_assignments)
    assignments = tuple(item for item in retained_assignments if item.status == "complete")
    assert len(assignments) == 7
    assert all(item.status == "complete" for item in assignments)
    assert all(item.contributions[0].recipient.kind == "execution" for item in assignments)
    assert all(item.contributions[0].signal.direction == "higher" for item in assignments)
    assert len({item.contributions[0].recipient for item in assignments}) == 1
    assert "assertions" not in batch.views[0].input_json
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    assert restored.traces[0].credit_assignments == trace.credit_assignments
    asyncio.run(task.score(trace))
    assert not trace.credit_errors and tuple(trace.credit_assignments) == retained_assignments
    assert Path(binding["source_episode_path"]).read_bytes() == raw
