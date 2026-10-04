"""Native manifest delivery/guard transport; literal fixtures assert no prose meaning."""

import asyncio
import copy
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_manifest_guards import comparison, field, literal
from test_manifest_slack_effects import channel, dm, initial
from test_notification_evidence import run_operations

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_guard_assessments import digest
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig

SIGNAL = 'fixture.literal_delivery'


def prompt(kind='direct_message', guard=False):
    if guard:
        return [{'role': 'user', 'content': 'Do not message excluded recipients from the queue sheet.'}]
    target = 'user Usarah' if kind == 'direct_message' else 'channel Cproduct'
    return [{'role': 'user', 'content': f'Send the literal text Exact reminder to Slack {target}.'}]


def contract(*, kind='direct_message', guard=False):
    source = {'adapter': 'slack.messages@1', 'kind': kind}
    if guard:
        return load_contract(canonical_json({'schema_version': 1, 'manifest_id': 'slack-guard-fixture',
            'revision': '1', 'public_request': prompt(kind, guard=True)[0]['content'],
            'bindings': [{'path': ['task_evidence', 'prompt'], 'canonical_sha256': digest(prompt(kind, guard=True))}],
            'sources': {
                'queue': {'adapter': 'google_sheets.rows@1', 'path': ['task_evidence', 'initial', 'google_sheets'],
                    'spreadsheet_id': 'sheet', 'worksheet_id': 'queue', 'key_fields': ['User'],
                    'required_fields': ['Excluded']}, 'messages': source},
            'checks': [{'check_id': 'excluded-recipient', 'signal_id': 'fixture.prohibited_delivery',
                'role': 'harm', 'operator': 'effects.prohibited_when@1', 'population': 'queue', 'source': 'messages',
                'prohibited_when': comparison('eq', field('request', 'Excluded', domain='boolean'), literal(True)),
                'effect_match': comparison('eq', field('effect', 'recipient_user_id'), field('request', 'User'))}],
            'credit': [{'check': 'excluded-recipient', 'policy': 'per_effect_negative@1', 'channel': 'harm'}]}))
    target = 'recipient_user_id' if kind == 'direct_message' else 'channel_id'
    expected = 'Usarah' if kind == 'direct_message' else 'Cproduct'
    public = prompt(kind)
    return load_contract(canonical_json({'schema_version': 1, 'manifest_id': 'slack-literal-fixture',
        'revision': '1', 'public_request': public[0]['content'], 'bindings': [
            {'path': ['task_evidence', 'prompt'], 'canonical_sha256': digest(public)}],
        'sources': {'request': {'adapter': 'public.request@1', 'member_key': 'literal-delivery', 'fields': {
            'text': {'value': 'Exact reminder', 'authority_paths': [['task_evidence', 'prompt']]},
            'destination': {'value': expected, 'authority_paths': [['task_evidence', 'prompt']]}}},
            'messages': source},
        'checks': [{'check_id': 'literal-delivery', 'signal_id': SIGNAL, 'role': 'goal',
            'operator': 'effects.required_when@1', 'semantics': 'new_occurrence',
            'population': 'request', 'source': 'messages',
            'required_when': comparison('eq', field('request', 'request_key'), literal('literal-delivery')),
            'effect_match': {'op': 'all', 'args': [
                comparison('eq', field('effect', 'text'), field('request', 'text')),
                comparison('eq', field('effect', target), field('request', 'destination'))]}}],
        'credit': [{'check': 'literal-delivery', 'policy': 'required_effect_once@1', 'channel': 'literal-delivery'}]}))


def scored(monkeypatch, calls, *, kind='direct_message', guard=False, missing_ack=None):
    declared = contract(kind=kind, guard=guard)
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: declared)
    world = initial()
    if guard:
        world['google_sheets'] = {'worksheets': [{'id': 'queue', 'spreadsheet_id': 'sheet', 'title': 'Queue'}],
            'rows': [{'id': 'native-request', 'spreadsheet_id': 'sheet',
            'worksheet_id': 'queue', 'row_id': 1, 'cells': {'User': 'Usarah', 'Excluded': True}}]}
    task, _, trace = native_fixture(run_operations(world, calls), missing_ack=missing_ack)
    data = AutomationBenchData.model_validate({**task.data.model_dump(mode='json'), 'prompt': prompt(kind, guard=guard)})
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    trace.task = trace.task.model_copy(update={'data': data})
    episode = vf.WireEpisode.model_validate({'task': trace.task.model_dump(mode='json'),
        'traces': [trace.model_dump(mode='json')]})
    replay = cast(Any, episode.traces[0])
    replay.state = trace.state
    scalar = copy.deepcopy(replay.rewards)
    asyncio.run(task.score(replay))
    assert replay.rewards == scalar and not replay.assessment_errors and not replay.credit_errors
    return task, episode, replay


@pytest.mark.parametrize('kind', ['channel_message', 'direct_message'])
def test_native_literal_delivery_recipient_once_and_reload(monkeypatch, kind):
    send = dm if kind == 'direct_message' else channel
    task, episode, trace = scored(monkeypatch, [send(text='Other'), send(text='Exact reminder'),
        send(text='Exact reminder')], kind=kind)
    goals = [record for record in terminal_records(trace) if record.signal.signal_id == SIGNAL]
    assert len(goals) == 1 and goals[0].value == 1
    assert len(penalties(trace)) == 1 and penalties(trace)[0].value == 1
    assert penalties(trace)[0].recipient.execution.invocation_id == 'execution-1'
    assignments = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == assignments
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert tuple(replay.credit_assignments) == assignments and not replay.credit_errors


@pytest.mark.parametrize('variant', ['wrong-text', 'missing-ack', 'split'])
def test_incomplete_literal_delivery_never_receives_credit(monkeypatch, variant):
    calls = [dm(text='Other')] if variant == 'wrong-text' else [dm()]
    if variant == 'split':
        calls = [dm(text='Other'), channel(text='Exact reminder')]
    _, _, trace = scored(monkeypatch, calls, missing_ack=0 if variant == 'missing-ack' else None)
    assert not penalties(trace)
    assert all(record.value != 1 for record in terminal_records(trace) if record.signal.signal_id == SIGNAL)


def test_prohibited_native_send_has_raw_harm_and_separate_negative_credit(monkeypatch):
    _, _, trace = scored(monkeypatch, [dm()], guard=True)
    harms = [record for record in terminal_records(trace) if record.signal.signal_id == 'fixture.prohibited_delivery']
    assert len(harms) == 1 and harms[0].value == 1
    assert len(penalties(trace)) == 1 and penalties(trace)[0].value == -1
    assert penalties(trace)[0].recipient.execution.invocation_id == 'execution-0'
