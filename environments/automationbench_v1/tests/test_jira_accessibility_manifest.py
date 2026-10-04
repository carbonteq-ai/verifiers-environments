"""Real public request and preserved historical trace; current handler alternatives."""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_batch01_manifests import recorded
from test_manifest_created_objects import create
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_notification_evidence import run_operations

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.loader import load_contract, load_task_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

ROOT = Path('/home/hammad/projects/rl')
DRAFT = Path(__file__).resolve().parents[1] / 'manifest-drafts' / 'legacy' / 'jira-accessibility-draft.json'
PACK = ROOT / '.posttrain/state/verifiers-assessment-qualification/manifest-authoring-105/batch-09.json'
NAME = 'simple.jira_accessibility_audit'
SUMMARY = 'Conduct accessibility audit for main dashboard'
SIGNAL = 'simple.accessibility_issue_retained'
EPISODE_SHA = 'a1bba91c81e87f1bc25e832fc042e8aaefed375625ec709fcb8c67f3b11cb313'


@pytest.fixture
def public(monkeypatch):
    if not PACK.exists() or not DRAFT.exists():
        pytest.skip('local public authoring pack unavailable')
    entry = next(item for item in json.loads(PACK.read_bytes())['tasks'] if item['task_name'] == NAME)
    value = entry['public_input']
    assert hashlib.sha256(canonical_json(value).encode()).hexdigest() == entry['public_input_sha256']
    contract = load_contract(DRAFT.read_text())
    assert load_task_contract(NAME) == contract
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: contract)
    return value


def goals(trace):
    return [item for item in terminal_records(trace) if item.signal.signal_id == SIGNAL]


def clean(trace):
    assert not trace.assessment_errors and not trace.credit_errors


def simulate(public, calls, *, missing_ack=None, changed_prompt=False):
    initial = copy.deepcopy(public['initial_state'])
    material = run_operations(initial, calls)
    _, _, trace = native_fixture(material, missing_ack=missing_ack)
    prompt = copy.deepcopy(public['prompt'])
    if changed_prompt:
        prompt[-1]['content'] = 'Cancel the accessibility audit.'
    data = AutomationBenchData(domain='simple', task_name=NAME, prompt=prompt,
        initial_state=initial, assertions=(), zapier_tools=tuple(public['zapier_tools']))
    trace.task = vf.TraceTask(type='Task', data=data)
    episode = vf.WireEpisode.model_validate({'task': trace.task.model_dump(mode='json'),
        'traces': [trace.model_dump(mode='json')]})
    trace = cast(Any, episode.traces[0])
    trace.state = AutomationBenchState(world=material['task_evidence']['final'], initial_state=initial, assertions=())
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    clean(trace)
    assert trace.rewards == scalar
    return task, episode, trace


def test_recorded_action_log_does_not_invent_retained_issue(public):
    path, raw, episode, trace, data = recorded(NAME)
    assert hashlib.sha256(raw).hexdigest() == EPISODE_SHA
    trace.state = AutomationBenchState(world=trace.info['automationbench']['end_state'],
        initial_state=data.initial_state, assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    clean(trace)
    assert len(goals(trace)) == 1 and goals(trace)[0].value == 0
    assert not penalties(trace) and trace.rewards == scalar
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    clean(replay)
    assert goals(replay)[0].value == 0 and not penalties(replay)
    assert replay.rewards == scalar and path.read_bytes() == raw


def test_current_handler_matches_same_fresh_issue_and_consumes_once(public):
    task, episode, trace = simulate(public, [create(summary='Other'), create(summary=SUMMARY), create(summary=SUMMARY)])
    assert len(goals(trace)) == 1 and goals(trace)[0].value == 1
    assert len(penalties(trace)) == 1
    assert penalties(trace)[0].recipient.execution.invocation_id == 'execution-1'
    original = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == original
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    clean(replay)
    assert tuple(replay.credit_assignments) == original


@pytest.mark.parametrize('variant', ['wrong-summary', 'wrong-type', 'split', 'missing-ack', 'changed-prompt'])
def test_nonmatching_or_unproven_actions_receive_no_credit(public, variant):
    calls = [create(summary=SUMMARY)]
    if variant == 'wrong-summary':
        calls = [create(summary='Other')]
    elif variant == 'wrong-type':
        calls = [create(summary=SUMMARY, issuetype='Bug')]
    elif variant == 'split':
        calls = [create(summary=SUMMARY, issuetype='Bug'), create(summary='Other')]
    _, _, trace = simulate(public, calls, missing_ack=0 if variant == 'missing-ack' else None,
        changed_prompt=variant == 'changed-prompt')
    assert len(goals(trace)) == 1 and not penalties(trace)
    if variant != 'missing-ack':
        assert goals(trace)[0].value != 1
