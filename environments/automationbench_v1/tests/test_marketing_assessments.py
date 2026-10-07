"""Native publisher integration over the actual retained suppression episode."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
import verifiers.v1 as vf

from automationbench_v1.marketing_assessments import ReviewedSuppressionTask
from automationbench_v1.marketing_evidence import TASK
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchData,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState


def test_normal_loader_selects_only_reviewed_suppression():
    tasks = AutomationBenchTaskset(
        AutomationBenchConfig(
            domains=["marketing"],
            task=AutomationBenchTaskConfig(reviewed_suppression_assessments=True),
        )
    ).load()
    assert [task.data.task_name for task in tasks if isinstance(task, ReviewedSuppressionTask)] == [
        TASK
    ]
    assert len(tasks) > 1


def test_actual_suppression_native_score_credit_reload_and_official_parity():
    registry = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-policy-contracts.json"
    )
    if not registry.exists():
        pytest.skip("actual retained development registry unavailable")
    item = next(
        case for case in json.loads(registry.read_text())["tasks"] if case["task_name"] == TASK
    )
    binding = item["source_binding"]
    raw = Path(binding["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == binding["source_episode_sha256"]
    episode = vf.WireEpisode.model_validate_json(raw)
    original = episode.model_dump_json()
    trace = episode.traces[0]
    data = AutomationBenchData.model_validate(episode.task.data.model_dump(mode="json"))
    task = ReviewedSuppressionTask(data, AutomationBenchTaskConfig(capture_actions=True))
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state,
        assertions=data.assertions,
    )
    rewards = dict(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    assert trace.rewards == rewards
    batch = trace.assessment_batches[-1]
    assert batch.run.producer_id == task.producer_id
    records = {record.signal.signal_id: record for record in batch.assessments}
    assert records["suppression.no_prohibited_effect"].value == 1
    assert all(record.subject.kind == "trace" for record in records.values())
    assignments = [item for item in trace.credit_assignments if item.status == "complete"]
    assert len(assignments) == 3
    assert {item.contributions[0].channel for item in assignments} == {
        "suppression.archived:bad1@example.com",
        "suppression.archived:bad2@example.com",
        "suppression.ops_summary",
    }
    assert all(item.contributions[0].recipient.kind == "execution" for item in assignments)
    assert all(item.contributions[0].signal.direction != "neutral" for item in assignments)
    assert len(task.credit_requests(batch.source, (batch, batch))) == 3
    independent_run = batch.model_copy(
        update={
            "run": batch.run.model_copy(update={"run_id": "independent-reassessment"}),
            "assessments": tuple(
                record.model_copy(
                    update={
                        "assessment_id": f"independent-{record.assessment_id}",
                        "run_id": "independent-reassessment",
                    }
                )
                for record in batch.assessments
            ),
        }
    )
    with pytest.raises(ValueError, match="credit_assessment_attempt_selection_unresolved"):
        task.credit_requests(batch.source, (batch, independent_run))
    conflicting_history = batch.model_copy(
        update={
            "assessments": (
                batch.assessments[0].model_copy(update={"reason": "conflicting-history"}),
                *batch.assessments[1:],
            ),
        }
    )
    with pytest.raises(ValueError, match="credit_assessment_history_conflict"):
        task.credit_requests(batch.source, (batch, conflicting_history))
    assert "assertions" not in batch.views[0].input_json
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    assert restored.traces[0].assessment_batches == trace.assessment_batches
    assert restored.traces[0].credit_assignments == trace.credit_assignments
    assert Path(binding["source_episode_path"]).read_bytes() == raw
    assert original != episode.model_dump_json()  # new evidence stays in this detached copy
    # A fresh assessment attempt retains its findings without multiplying the
    # same source-bound domain accomplishments.
    before_assignments = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    assert tuple(trace.credit_assignments) == before_assignments
    latest = trace.assessment_batches[-1]
    assert latest.run.run_id != batch.run.run_id
    assert latest.source.identity == batch.source.identity
    context = vf.CreditPlanningContext(
        source=batch.source.identity,
        current_assessment_runs=(),
        prior_assignments=before_assignments,
    )
    assert task.plan_credit(batch.source, (batch,), context) == []
    current = context.model_copy(update={"current_assessment_runs": (latest.run,)})
    assert task.plan_credit(latest.source, tuple(trace.assessment_batches), current) == []
    failed_current = context.model_copy(
        update={
            "current_assessment_runs": (
                latest.run.model_copy(
                    update={
                        "run_id": "failed-current-run",
                        "attempt_id": "failed-current-attempt",
                        "invocation_id": "failed-current-invocation",
                    }
                ),
            ),
            "prior_assignments": (),
        }
    )
    # Older success cannot rescue this call's missing/failed assessment result,
    # even when that older evidence has never been assigned.
    assert task.plan_credit(latest.source, tuple(trace.assessment_batches), failed_current) == []
