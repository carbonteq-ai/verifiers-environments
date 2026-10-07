"""Raw native/SDK authored-output projection, including sealed actual SDK replay.

This qualifies source availability and exact text, never a narrative-policy
verdict or an imitation target for future agent summaries.
"""

import base64
import copy
import hashlib
import json
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_batch01_manifests import recorded
from verifiers.v1.graph import MessageNode
from verifiers.v1.trace import ModelCall
from verifiers.v1.types import AssistantMessage, UserMessage

from automationbench_v1.authored_output_source import build_authored_output_material
from automationbench_v1.calibration.collector import read_retained_artifacts
from automationbench_v1.contracts.authored_outputs import (
    AuthoredOutputSource,
    capture_authored_outputs,
    validate_authored_outputs,
)
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

NAME = 'simple.email_sf_contact_assistant_update'
EPISODE_SHA = '05c81896501fa361b1d35d1388d1e7300eee468b1aacd8b2cced895dafeee037'
ENVELOPE_SHA = 'a585ec5edee63890d73cfae792cec6fb8e24f3410aff36dd2cc00fd8a25eb012'
SDK_SHA = 'bb65881e6d7fec76cb38c370902ba67c774e379da4f353d469521d62a7aacd06'
FINAL_TEXT = 'Updated Rachel Nguyen’s Salesforce contact with assistant Kevin Torres (kevin.torres@ironclad.example.com).'


def source(trace):
    return {'task_evidence': {'authored_outputs': build_authored_output_material(trace)}}


def native():
    return vf.Trace(
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type='Task', data=vf.TaskData(prompt='Manufactured output source test')),
        nodes=[
            MessageNode(parent=None, sampled=False, message=UserMessage(content='User text is not authored output')),
            MessageNode(parent=0, sampled=False, message=AssistantMessage(content='Injected assistant prefill')),
            MessageNode(parent=1, sampled=True, message=AssistantMessage(
                content='First public answer', reasoning_content='Private reasoning sentinel')),
            MessageNode(parent=2, sampled=True, message=AssistantMessage(content='Second public answer')),
        ],
        calls=[ModelCall(node=2, finish_reason='stop'), ModelCall(node=3, finish_reason='stop')],
        is_completed=True, ok=True,
    )


def test_native_projection_preserves_original_indices_calls_and_excludes_reasoning():
    trace = native()
    projected = build_authored_output_material(trace)
    assert [item['node'] for item in projected['native_nodes']] == [0, 1, 2, 3]
    assert [item['parent'] for item in projected['native_nodes']] == [None, 0, 1, 2]
    assert projected['native_calls'] == [
        {'node': 2, 'finish_reason': 'stop', 'failed': False},
        {'node': 3, 'finish_reason': 'stop', 'failed': False},
    ]
    assert 'Private reasoning sentinel' not in json.dumps(projected)
    assert not projected['sdk_declared'] and projected['complete']
    captured = capture_authored_outputs(source(trace), AuthoredOutputSource())
    assert captured.closed and [item.output_id for item in captured.records] == ['native-node:2', 'native-node:3']
    assert [item.text for item in captured.records] == ['First public answer', 'Second public answer']


@pytest.mark.parametrize('mutation', ['unfinished', 'truncated', 'missing-call', 'no-nodes'])
def test_native_source_gaps_never_become_closed_empty_output(mutation):
    trace = native()
    if mutation == 'unfinished':
        trace.is_completed = False
    elif mutation == 'truncated':
        trace.calls[-1].finish_reason = 'length'
    elif mutation == 'missing-call':
        trace.calls.pop()
    else:
        trace.nodes = []
        trace.calls = []
    captured = capture_authored_outputs(source(trace), AuthoredOutputSource())
    assert not captured.closed


def test_sdk_info_is_copied_and_missing_artifact_cannot_fall_back_to_native_answer():
    trace = native()
    trace.info['codex_sdk'] = {'events': []}
    projected = build_authored_output_material(trace)
    trace.info['codex_sdk']['events'].append({'kind': 'changed'})
    assert projected['sdk_info'] == {'events': []}
    assert projected['sdk_declared'] and projected['sdk_artifact_base64'] is None
    captured = capture_authored_outputs({'task_evidence': {'authored_outputs': projected}}, AuthoredOutputSource())
    assert not captured.closed and not captured.records


def test_actual_sdk_artifacts_restore_exact_final_text_and_native_reload_without_policy_verdict():
    path, raw, episode, trace, data = recorded(NAME)
    assert hashlib.sha256(raw).hexdigest() == EPISODE_SHA
    envelope_path = path.parent / 'trace-0-artifacts.json'
    envelope = envelope_path.read_bytes()
    assert hashlib.sha256(envelope).hexdigest() == ENVELOPE_SHA
    assert trace.nodes == [] and trace.calls == []
    # The episode alone retains only the reference, not the excluded artifact.
    assert not trace.state.artifacts
    missing = capture_authored_outputs(source(trace), AuthoredOutputSource())
    assert not missing.closed and not missing.records
    restored = read_retained_artifacts(path.parent, trace)
    sdk = restored['codex_sdk/events.json']
    assert isinstance(sdk, bytes) and len(sdk) == 140095 and hashlib.sha256(sdk).hexdigest() == SDK_SHA
    scalar, info = copy.deepcopy(trace.rewards), copy.deepcopy(trace.info)
    trace.state = AutomationBenchState(world=trace.info['automationbench']['end_state'],
        initial_state=data.initial_state, assertions=data.assertions, artifacts=restored)
    projected = build_authored_output_material(trace)
    assert projected['sdk_artifact_sha256'] == SDK_SHA
    assert base64.b64decode(projected['sdk_artifact_base64'], validate=True) == sdk
    assert projected['sdk_info'] == json.loads(sdk)
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    task_source = {'task_evidence': task.assessment_source(trace)}
    assert task_source['task_evidence']['authored_outputs'] == projected
    captured = capture_authored_outputs(task_source, AuthoredOutputSource())
    assert captured.closed and captured.status == 'qualified'
    assert len(captured.records) == 1
    output = captured.records[0]
    assert output.text == FINAL_TEXT and output.origin == 'sdk_item' and output.channel is None
    # The SDK supplies phase=final_answer, not an explicit message channel.
    assert output.output_id == 'msg_01b15c2bbc2b7742016ac12a0e74e887d2b5fcd02545a0cd62'
    validate_authored_outputs(captured, task_source, AuthoredOutputSource())
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    assert not replay.state.artifacts
    replay.state.artifacts.update(read_retained_artifacts(path.parent, replay))
    assert build_authored_output_material(replay) == projected
    assert replay.rewards == scalar and trace.rewards == scalar and trace.info == info
    assert path.read_bytes() == raw and envelope_path.read_bytes() == envelope


@pytest.mark.parametrize('mutation', ['missing', 'envelope-bytes', 'reference-digest', 'trace-id'])
def test_actual_retained_envelope_failures_cannot_supply_authored_text(tmp_path, mutation):
    path, raw, _, trace, _ = recorded(NAME)
    original = (path.parent / 'trace-0-artifacts.json').read_bytes()
    target = tmp_path / 'trace-0-artifacts.json'
    if mutation != 'missing':
        target.write_bytes(original + b' ' if mutation == 'envelope-bytes' else original)
    if mutation == 'reference-digest':
        trace.info['automationbench_collection_artifacts']['digest'] = '0' * 64
    if mutation == 'trace-id':
        trace.id = 'different-trace'
    with pytest.raises((ValueError, FileNotFoundError)):
        read_retained_artifacts(tmp_path, trace)
    assert not trace.state.artifacts
    assert not capture_authored_outputs(source(trace), AuthoredOutputSource()).closed
    assert path.read_bytes() == raw and (path.parent / 'trace-0-artifacts.json').read_bytes() == original


def test_restored_sdk_info_disagreement_is_unavailable_without_root_reply_fallback():
    path, _, _, trace, _ = recorded(NAME)
    trace.state.artifacts.update(read_retained_artifacts(path.parent, trace))
    trace.info['codex_sdk']['events'] = []
    trace.info['reply'] = 'A tempting but unauthenticated final answer'
    captured = capture_authored_outputs(source(trace), AuthoredOutputSource())
    assert not captured.closed and not captured.records
