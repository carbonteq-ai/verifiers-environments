"""Replay the authored prohibition against its unchanged recorded execution."""

import asyncio
import copy
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_batch01_manifests import recorded
from test_manifest_guard_assessments import penalties, terminal_records

from automationbench_v1 import manifest_assessments
from automationbench_v1.contracts.loader import load_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.tools import AutomationBenchState

REVIEW = Path('/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate/manifest-authoring-batch-08-review.json')
DRAFT = Path(__file__).resolve().parents[1] / 'manifest-drafts' / 'legacy' / 'retired-content-guard-draft.json'


def test_recorded_retired_content_append_receives_exact_negative_credit(monkeypatch):
    if not REVIEW.exists() or not DRAFT.exists():
        pytest.skip('local public authoring review unavailable')
    contract = load_contract(DRAFT.read_text())
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: contract)
    path, raw, episode, trace, data = recorded('marketing.content_repurpose')
    trace.state = AutomationBenchState(world=trace.info['automationbench']['end_state'],
        initial_state=data.initial_state, assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    harm = [record for record in terminal_records(trace) if record.signal.signal_id == contract.checks[0].signal_id]
    assert any(record.value == 1 for record in harm)
    contributions = penalties(trace)
    assert len(contributions) == 1 and contributions[0].value == -1
    assert contributions[0].recipient.execution.invocation_id == 'cd31335d27334cf0899cf01eebc7acd7'
    assert trace.rewards == scalar
    assignments = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == assignments
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors
    assert tuple(replay.credit_assignments) == assignments and replay.rewards == scalar
    assert path.read_bytes() == raw
