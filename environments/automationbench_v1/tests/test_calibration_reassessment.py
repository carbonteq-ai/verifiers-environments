"""Actual Task.score replay seam; placeholder contract grants no eligibility."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
import verifiers.v1 as vf
from verifiers.v1.assessment_source import capture_trace_source

from automationbench_v1.calibration.eligibility import (
    TaskRewardContract,
    _batch_semantics,
    _credit_semantics,
)
from automationbench_v1.calibration.inventory import FrozenTask, content_digest
from automationbench_v1.calibration.reassessment import TaskScoreReassessmentVerifier
from automationbench_v1.simple_assessments import ReviewedSimpleTask
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig


def _fixture(task_name="simple.sf_case_priority_high"):
    registry = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-policy-contracts.json"
    )
    if not registry.exists():
        pytest.skip("retained development registry unavailable")
    item = next(
        case for case in json.loads(registry.read_text())["tasks"] if case["task_name"] == task_name
    )
    raw = Path(item["source_binding"]["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == item["source_binding"]["source_episode_sha256"]
    episode = vf.WireEpisode.model_validate_json(raw)
    episode.traces[0].state.artifacts["fixture/runtime-evidence.json"] = b'{"retained":true}'
    data = episode.task.data.model_dump(mode="json")
    config = AutomationBenchTaskConfig(capture_actions=True).model_dump(mode="json")
    frozen = FrozenTask(
        task_name=item["task_name"],
        domain="simple",
        data=data,
        config=config,
        digest=content_digest({"data": data, "config": config}),
        initial_score={},
    )
    task = ReviewedSimpleTask(
        AutomationBenchData.model_validate(data), AutomationBenchTaskConfig.model_validate(config)
    )
    trace = episode.traces[0]
    source = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    request = task.assessment_requests(source)[0][1].run
    # Contract shape exercises this bridge, not scientific approval of a guard.
    checks = []
    for purpose in ("goal", "guard", "coverage"):
        signal = task.signal_definition("simple.requested_state").model_copy(
            update={"signal_id": f"fixture.{purpose}"}
        )
        checks.append(
            {
                "key": purpose,
                "purpose": purpose,
                "signal": signal.model_dump(mode="json"),
                "producer_id": task.producer_id,
                "producer_revision": "1",
                "rubric_revision": task.policy_revision,
                "subject_kind": "trace",
                "operator": "eq",
                "expected_value": 1.0,
            }
        )
    body = {
        "schema_version": 2,
        "task_name": frozen.task_name,
        "task_digest": frozen.digest,
        "policy_source_digest": "e" * 64,
        "admission_policy": "accepted_redesign",
        "guard_set": {
            "status": "reviewed_closed",
            "check_keys": ["guard"],
            "policy_source_digest": "e" * 64,
            "scope": "task_specific",
            "review_revision": "fixture-policy-review-1",
        },
        "checks": checks,
    }
    contract = TaskRewardContract.model_validate({**body, "digest": content_digest(body)})
    verifier = TaskScoreReassessmentVerifier(ReviewedSimpleTask, source_digest="f" * 64)
    return episode, frozen, contract, request, verifier


@pytest.mark.parametrize(
    "task_name",
    [
        "simple.sf_case_priority_high",
        "simple.hs_update_contact_phone",
        "simple.asana_api_docs_task",
        "simple.gcal_one_on_one",
    ],
)
def test_actual_native_score_replay_is_repeatable_and_preserves_original(task_name):
    episode, task, contract, request, verifier = _fixture(task_name)
    original = episode.model_dump_json()
    first = verifier.replay(episode=episode, task=task, contract=contract, request=request)
    second = verifier.replay(episode=episode, task=task, contract=contract, request=request)
    assert episode.model_dump_json() == original
    assert _batch_semantics(first.batch) == _batch_semantics(second.batch)
    assert [_credit_semantics(item) for item in first.credit_assignments] == [
        _credit_semantics(item) for item in second.credit_assignments
    ]
    assert len(first.credit_assignments) == 1
    assert (
        json.loads(first.batch.source.source_json)["artifacts"]["fixture/runtime-evidence.json"]
        == hashlib.sha256(b'{"retained":true}').hexdigest()
    )
    assert first.batch.assessments[0].subject.kind == "trace"
    assert first.credit_assignments[0].contributions[0].recipient.kind == "execution"


def test_sync_replay_bridge_works_inside_async_collector_and_rejects_stale_producer():
    episode, task, contract, request, verifier = _fixture()

    async def invoke():
        return verifier.replay(episode=episode, task=task, contract=contract, request=request)

    assert asyncio.run(invoke()).batch.run.status == "complete"
    stale = request.model_copy(update={"producer_revision": "stale"})
    with pytest.raises(ValueError, match="producer_revision_mismatch"):
        verifier.replay(episode=episode, task=task, contract=contract, request=stale)
