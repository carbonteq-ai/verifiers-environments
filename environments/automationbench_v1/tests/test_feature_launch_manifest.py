"""Public request creation component, real handlers and one recorded Luna trace."""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_batch01_manifests import recorded
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.asana.actions import asana_create_task
from automationbench_v1 import manifest_assessments
from automationbench_v1.contracts import load_contract, load_task_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

ROOT = Path('/home/hammad/projects/rl')
DRAFT = Path(__file__).resolve().parents[1] / 'manifest-drafts' / 'legacy' / 'feature-launch-asana-draft.json'
PACK = ROOT / '.posttrain/state/verifiers-assessment-qualification/manifest-authoring-105/batch-07.json'
NAME = 'simple.feature_launch_slack'
SIGNAL = 'simple.launch_monitor_creation'
EPISODE_SHA = 'ff21dbc6fcf9ad96f3b52f015d677cf6e341226f94a5bd61d4b1862b0f32b127'


@pytest.fixture
def declaration(monkeypatch):
    if not PACK.exists() or not DRAFT.exists():
        pytest.skip('local public authoring pack unavailable')
    entry = next(item for item in json.loads(PACK.read_bytes())['tasks'] if item['task_name'] == NAME)
    public = entry['public_input']
    from automationbench_v1.capture import canonical_json
    assert hashlib.sha256(canonical_json(public).encode()).hexdigest() == entry['public_input_sha256']
    contract = load_contract(DRAFT.read_text())
    assert load_task_contract(NAME) == contract
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: contract)
    return public


def goals(trace):
    return [record for record in terminal_records(trace) if record.signal.signal_id == SIGNAL]


def create(name='Monitor analytics dashboard launch', workspace='ws_prod'):
    args = {'name': name, 'workspace': workspace}
    return zapier('asana_create_task', args, lambda world: asana_create_task(world, name=name, workspace=workspace))


def simulate(public, calls, *, missing_ack=None, changed_prompt=False):
    initial = copy.deepcopy(public['initial_state'])
    material = run_operations(initial, calls)
    _, _, trace = native_fixture(material, missing_ack=missing_ack)
    prompt = copy.deepcopy(public['prompt'])
    if changed_prompt:
        prompt[-1]['content'] = 'Cancel the Asana launch monitoring task.'
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
    assert not trace.assessment_errors and not trace.credit_errors
    assert trace.rewards == scalar
    return task, episode, trace


def test_actual_hash_bound_luna_creation_occurrence_and_reload(declaration):
    path, raw, episode, trace, data = recorded(NAME)
    assert hashlib.sha256(raw).hexdigest() == EPISODE_SHA
    trace.state = AutomationBenchState(world=trace.info['automationbench']['end_state'],
        initial_state=data.initial_state, assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    assert trace.rewards == scalar
    assert len(goals(trace)) == 1 and goals(trace)[0].value == 1
    assert len(penalties(trace)) == 1 and penalties(trace)[0].value == 1
    recipient = penalties(trace)[0].recipient.execution
    assert recipient is not None and recipient.invocation_id == 'e85c11c8b5cf4623976b2cac1ed67746'
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


def test_only_matching_create_receives_once_only_credit(declaration):
    task, episode, trace = simulate(declaration, [create(name='Other task'), create(), create()])
    assert len(goals(trace)) == 1 and goals(trace)[0].value == 1
    assert len(penalties(trace)) == 1
    assert penalties(trace)[0].recipient.execution.invocation_id == 'execution-1'
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert len(penalties(replay)) == 1 and not replay.credit_errors


@pytest.mark.parametrize('variant', ['wrong-name', 'wrong-workspace', 'split', 'missing-ack', 'changed-prompt'])
def test_incomplete_or_unqualified_creation_never_receives_credit(declaration, variant):
    calls = [create()]
    if variant == 'wrong-name':
        calls = [create(name='Other task')]
    elif variant == 'wrong-workspace':
        calls = [create(workspace='wrong')]
    elif variant == 'split':
        calls = [create(workspace='wrong'), create(name='Other task')]
    _, _, trace = simulate(declaration, calls, missing_ack=0 if variant == 'missing-ack' else None,
        changed_prompt=variant == 'changed-prompt')
    assert len(goals(trace)) == 1 and goals(trace)[0].value != 1
    assert not penalties(trace)
