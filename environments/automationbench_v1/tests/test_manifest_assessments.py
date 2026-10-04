"""Native publication and credit replay from hash-bound recorded executions."""

import asyncio
import copy
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_record_update_evidence import CONTRACTS
from test_record_update_evidence import source as record_source
from test_record_update_evidence import update as record_update

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract, load_task_contract
from automationbench_v1.contracts.evidence import capture_records
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchData,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState


def test_self_consistent_alternate_final_record_cannot_publish_false_goal(monkeypatch):
    from automationbench_v1 import manifest_assessments
    previous = CONTRACTS[0]
    raw = load_task_contract(previous.task_name).model_dump(mode="json")
    raw["bindings"] = []  # Manufactured task envelope: this is a source-boundary test.
    contract = load_contract(canonical_json(raw))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    original = ManifestAssessmentTask.assessment_requests
    def substituted(self, source):
        altered = []
        for name, request in original(self, source):
            view = request.views[0]
            material = json.loads(view.input_json)
            records = material["source"]["task_evidence"]["final"]["salesforce"]["opportunities"]
            record = next(item for item in records if item["id"] == previous.record_id)
            desired = previous.desired_fields[0]
            record[desired.name] = desired.value
            material["record_evidence_json"] = canonical_json({key: asdict(value)
                for key, value in capture_records(material["source"], contract.sources).items()})
            replacement = vf.ObservationView.capture(material, snapshot_id=source.snapshot_id,
                builder_revision=view.builder_revision, scope=view.scope, subjects=view.subjects)
            altered.append((name, request.model_copy(update={"views": (replacement,)})))
        return altered
    monkeypatch.setattr(ManifestAssessmentTask, "assessment_requests", substituted)
    task, _, trace = native_fixture(record_source(previous, [record_update(previous, value="Prospecting")]))
    asyncio.run(task.score(trace))
    assert any(batch.run.status == "failed" for batch in trace.assessment_batches)
    assert not terminal_records(trace) and not penalties(trace)


def test_native_opt_in_selects_packaged_manifest_catalog():
    from automationbench_v1.contracts import supported_tasks

    tasks = AutomationBenchTaskset(
        AutomationBenchConfig(
            domains=["simple"],
            task=AutomationBenchTaskConfig(manifest_assessments=True),
        )
    ).load()
    assert {
        task.data.task_name for task in tasks if isinstance(task, ManifestAssessmentTask)
    } == {name for name in supported_tasks() if name.startswith("simple.")}


def recorded(previous):
    index = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-review-coverage.json"
    )
    if not index.exists():
        pytest.skip("retained development coverage index unavailable")
    entry = next(
        item
        for item in json.loads(index.read_bytes())["entries"]
        if item["task_name"] == previous.task_name
    )
    path = Path(entry["source_episode_path"])
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["source_episode_sha256"]
    episode = vf.WireEpisode.model_validate_json(raw)
    trace = cast(Any, episode.traces[0])
    data = AutomationBenchData.model_validate(episode.task.data.model_dump(mode="json"))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state,
        assertions=data.assertions,
    )
    return task, episode, trace, path, raw


@pytest.mark.parametrize("previous", CONTRACTS, ids=lambda item: item.task_name)
def test_native_manifest_publishes_recorded_goal_credit_and_roundtrips(previous):
    task, episode, trace, path, raw = recorded(previous)
    original = dict(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == original
    assert not trace.assessment_errors and not trace.credit_errors
    batch = next(
        item
        for item in reversed(trace.assessment_batches)
        if any(record.signal.signal_id == "simple.requested_state" for record in item.assessments)
    )
    goal = batch.assessments[0]
    assert goal.status == "valid" and goal.value == 1
    assert goal.subject.kind == "trace"
    completed = [item for item in trace.credit_assignments if item.status == "complete"]
    assert len(completed) == 1
    contribution = completed[0].contributions[0]
    assert contribution.value == 1 and contribution.recipient.kind == "execution"
    assert contribution.parent_assessment_ids == (goal.assessment_id,)
    assert all("assertions" not in view.input_json for view in batch.views)
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    restored_trace = cast(Any, restored.traces[0])
    assert restored_trace.assessment_batches == trace.assessment_batches
    assert restored_trace.credit_assignments == trace.credit_assignments
    retained = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert not trace.credit_errors and tuple(trace.credit_assignments) == retained
    assert path.read_bytes() == raw


def test_native_joint_credit_is_one_contribution_with_two_independent_parent_records(monkeypatch):
    from automationbench_v1 import manifest_assessments

    previous = CONTRACTS[0]
    declaration = load_task_contract(previous.task_name).model_dump(mode="json")
    second = copy.deepcopy(declaration["checks"][0])
    second["check_id"] = "second-obligation"
    declaration["checks"].append(second)
    declaration["credit"] = [
        {
            "policy": "joint_verified_transition_once@1",
            "checks": ["requested-state", "second-obligation"],
            "channel": "goal",
        }
    ]
    contract = load_contract(json.dumps(declaration))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda name: contract)
    task, episode, trace, path, raw = recorded(previous)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    assignments = [item for item in trace.credit_assignments if item.status == "complete"]
    assert len(assignments) == 1 and len(assignments[0].contributions) == 1
    contribution = assignments[0].contributions[0]
    assert contribution.value == 1 and contribution.attribution == "joint"
    assert len(set(contribution.parent_assessment_ids)) == 2
    published = {
        record.assessment_id
        for batch in trace.assessment_batches
        for record in batch.assessments
        if record.signal.signal_id == "simple.requested_state"
    }
    assert set(contribution.parent_assessment_ids) == published
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    assert cast(Any, restored.traces[0]).credit_assignments == trace.credit_assignments
    assert path.read_bytes() == raw


@pytest.mark.parametrize("history", ["conflict", "missing-current"])
def test_native_credit_rejects_conflicting_history_and_ignores_unaccepted_runs(
    monkeypatch, history
):
    original = ManifestAssessmentTask.plan_credit
    checked = []

    def altered(self, source, assessments, context):
        if history == "missing-current":
            requests = original(
                self,
                source,
                assessments,
                context.model_copy(update={"current_assessment_runs": ()}),
            )
            assert requests == []
            checked.append(True)
            return requests
        terminal = next(batch for batch in assessments if batch.run.status == "complete")
        record = terminal.assessments[0]
        changed = terminal.model_copy(
            update={
                "assessments": (record.model_copy(update={"value": 0 if record.value == 1 else 1}),)
            }
        )
        with pytest.raises(ValueError, match="history_regression"):
            original(self, source, (*assessments, changed), context)
        checked.append(True)
        return []

    monkeypatch.setattr(ManifestAssessmentTask, "plan_credit", altered)
    task, _, trace, _, _ = recorded(CONTRACTS[0])
    asyncio.run(task.score(trace))
    assert checked and not trace.credit_errors
    assert not trace.credit_assignments
