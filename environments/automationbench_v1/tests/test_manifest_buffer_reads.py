"""Authenticated channels and native read-before-post archive behavior."""

import asyncio
import copy
import json

import pytest
import verifiers.v1 as vf
from test_manifest_airtable_record_writes import initial as sheet_initial
from test_manifest_gmail_observations import material, mutate_return
from test_manifest_guard_assessments import native_fixture, terminal_records
from test_manifest_trello_reads import declaration as trello_declaration
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.buffer.posts import buffer_add_to_queue, buffer_list_channels
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.buffer_reads import (
    BufferChannelReadSource,
    capture_buffer_channel_reads,
)
from automationbench_v1.tools import AutomationBenchState


def initial(org='org'):
    value = sheet_initial();value['buffer'] = {'channels': [{'id': 'channel', 'organization_id': org, 'name': 'Facebook', 'service': 'facebook'}]};return value


def read(org='org'):
    return zapier('buffer_list_channels', {'organization_id': org}, lambda w:buffer_list_channels(w, org))


def post():
    args = {'organization_id': 'org', 'channel_id': 'channel', 'text': 'Card'}
    return zapier('buffer_add_to_queue', args, lambda w:buffer_add_to_queue(w, **args))


def capture(source):return capture_buffer_channel_reads(source, BufferChannelReadSource())


def test_channel_list_empty_and_native_scope_fallback():
    evidence = capture(material([read(), post()], initial()));assert evidence.complete
    assert json.loads(evidence.effects[0].params_json)['record']['organization_id'] == 'org'
    empty = capture(material([read('foreign')], initial()));assert empty.complete and json.loads(empty.effects[0].params_json)['found'] is False
    fallback = capture(material([read('foreign')], initial('')));assert fallback.complete
    assert json.loads(fallback.effects[0].params_json)['record']['organization_id'] == ''


@pytest.mark.parametrize('damage', ['field', 'count', 'scope'])
def test_coherent_forgery(damage):
    def change(result):
        if damage == 'field':result['channels'][0]['id'] = 'forged'
        elif damage == 'count':result['total'] = 2
        else:result['channels'][0]['organization_id'] = 'foreign'
    assert not capture(mutate_return(material([read()], initial()), change)).complete


@pytest.mark.parametrize('scenario,expected', [('ordered', ('valid', 1)), ('late', ('valid', 0)), ('missing', ('abstained', None))])
def test_ordered_native_archive_parity(monkeypatch, scenario, expected):
    raw = trello_declaration().model_dump(mode='json')
    raw['sources']['reads'] = BufferChannelReadSource().model_dump(mode='json')
    raw['sources']['writes'] = {'adapter': 'service.record_writes@1', 'service': 'buffer', 'collection': ['posts'], 'kind': 'create'}
    c = raw['checks'][0]
    c['effect_match']['args'][0] = {'op': 'eq', 'left': {'kind': 'field', 'path': ['effect', 'record', 'text']}, 'right': {'kind': 'literal', 'value': 'Card'}}
    c['effect_joins'][0]['where'] = {'op': 'eq', 'left': {'kind': 'field', 'path': ['joined', 'record', 'id']}, 'right': {'kind': 'field', 'path': ['effect', 'record', 'channel_id']}}
    declared = load_contract(canonical_json(raw));monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _:declared)
    task, _, trace = native_fixture(run_operations(initial(), [post(), read()] if scenario == 'late' else [read(), post()]), missing_ack=0 if scenario == 'missing' else None)
    rewards = copy.deepcopy(trace.rewards);asyncio.run(task.score(trace));found = {(r.signal.signal_id, r.status, r.value) for r in terminal_records(trace)}
    assert ('expense.status', *expected) in found and trace.rewards == rewards and not trace.assessment_errors
    wire = vf.WireEpisode.model_validate({'task': trace.task.model_dump(mode='json'), 'traces': [trace.model_dump(mode='json')]})
    restored = vf.WireEpisode.model_validate_json(wire.model_dump_json()).traces[0];restored.state = AutomationBenchState.model_validate(trace.state.model_dump(mode='json'));asyncio.run(task.score(restored))
    assert {(r.signal.signal_id, r.status, r.value) for r in terminal_records(restored)} == found and restored.rewards == rewards and not restored.assessment_errors
