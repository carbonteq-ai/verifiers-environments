"""One native publisher serves ten independently bound public update contracts."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
import verifiers.v1 as vf

from automationbench_v1.record_assessments import ReviewedRecordUpdateTask
from automationbench_v1.simple_record_contracts import CONTRACTS, SUPPORTED
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchData,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState


def test_loader_selects_exact_reviewed_record_batch():
    tasks = AutomationBenchTaskset(AutomationBenchConfig(
        domains=["simple"],
        task=AutomationBenchTaskConfig(reviewed_record_update_assessments=True),
    )).load()
    assert {task.data.task_name for task in tasks if isinstance(task, ReviewedRecordUpdateTask)} == SUPPORTED


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda item: item.task_name)
def test_actual_record_update_native_credit_reload_and_repeat(contract):
    index = Path("/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-review-coverage.json")
    if not index.exists():
        pytest.skip("retained development coverage index unavailable")
    entry = next(item for item in json.loads(index.read_bytes())["entries"]
                 if item["task_name"] == contract.task_name)
    path = Path(entry["source_episode_path"])
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["source_episode_sha256"]
    episode = vf.WireEpisode.model_validate_json(raw)
    trace = episode.traces[0]
    data = AutomationBenchData.model_validate(episode.task.data.model_dump(mode="json"))
    task = ReviewedRecordUpdateTask(data, AutomationBenchTaskConfig(capture_actions=True))
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state, assertions=data.assertions,
    )
    original = dict(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == original
    assert not trace.assessment_errors and not trace.credit_errors
    batch = trace.assessment_batches[-1]
    goal = next(item for item in batch.assessments if item.signal.signal_id == "simple.requested_state")
    assert goal.status == "valid" and goal.value == 1 and goal.subject.kind == "trace"
    retained = tuple(trace.credit_assignments)
    completed = [item for item in retained if item.status == "complete"]
    assert len(completed) == 1
    contribution = completed[0].contributions[0]
    assert contribution.recipient.kind == "execution" and contribution.value == 1
    assert contribution.parent_assessment_ids == (goal.assessment_id,)
    assert "assertions" not in batch.views[0].input_json
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    assert restored.traces[0].assessment_batches == trace.assessment_batches
    assert restored.traces[0].credit_assignments == trace.credit_assignments
    asyncio.run(task.score(trace))
    assert not trace.credit_errors and tuple(trace.credit_assignments) == retained
    assert path.read_bytes() == raw
