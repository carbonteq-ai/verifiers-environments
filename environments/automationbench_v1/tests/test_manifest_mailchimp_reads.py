"""Native subscriber read authenticity and ordered action evidence."""

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

from automationbench.tools.zapier.mailchimp.subscribers import (
    mailchimp_add_subscriber,
    mailchimp_list_subscribers,
)
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.mailchimp_reads import (
    MailchimpSubscriberReadSource,
    _project,
    capture_mailchimp_subscriber_reads,
)
from automationbench_v1.tools import AutomationBenchState


def initial():
    value = sheet_initial()
    value['mailchimp'] = {'subscribers': [{'id': 'member-1', 'email': 'a@example.test', 'list_id': 'list-1', 'merge_fields': {'FNAME': 'Ann'}, 'tags': ['tag']} ]}
    return value


def read(list_id='list-1'):
    return zapier('mailchimp_list_subscribers', {'list_id': list_id}, lambda world: mailchimp_list_subscribers(world, list_id))


def add():
    args = {'list_id': 'list-1', 'email': 'b@example.test'}
    return zapier('mailchimp_add_subscriber', args, lambda world: mailchimp_add_subscriber(world, **args))


def capture(source):
    return capture_mailchimp_subscriber_reads(source, MailchimpSubscriberReadSource())


def test_exact_native_list_and_empty_audience():
    evidence = capture(material([read(), add()], initial()))
    assert evidence.complete, evidence.reason
    (fact,) = evidence.effects
    fields = json.loads(fact.params_json)
    assert fields['record']['merge_fields']['FNAME'] == 'Ann' and fields['returned_count'] == 1
    assert fields['record']['tags'] == ['tag'] and fields['list_id'] == 'list-1'
    empty = capture(material([read('absent')], initial()))
    assert empty.complete and json.loads(empty.effects[0].params_json)['found'] is False


@pytest.mark.parametrize('damage', ['field', 'count', 'list', 'duplicate'])
def test_coherent_forgery_rejected(damage):
    def change(result):
        if damage == 'field':result['subscribers'][0]['email'] = 'forged@example.test'
        elif damage == 'count':result['count'] = 2
        elif damage == 'list':result['subscribers'][0]['list_id'] = 'foreign'
        else:result['subscribers'].append(result['subscribers'][0]);result['count'] = 2
    evidence = capture(mutate_return(material([read()], initial()), change))
    assert not evidence.complete and all(x.status == 'unavailable' for x in evidence.effects)


def test_missing_ack_and_source_budget():
    source = material([read()], initial());source['state_write_receipts'] = []
    assert not capture(source).complete
    source = material([read()], initial())
    before = source['task_evidence']['final'];before['mailchimp']['extra'] = 'x' * (8 * 1024 * 1024)
    with pytest.raises(ValueError, match='source_budget'):_project(before, 'mailchimp_list_subscribers', {'list_id': 'list-1'}, {'success': True, 'subscribers': []})


@pytest.mark.parametrize('scenario,expected', [('ordered', ('valid', 1)), ('late', ('valid', 0)), ('missing', ('abstained', None))])
def test_native_ordered_join_archive_parity(monkeypatch, scenario, expected):
    raw = trello_declaration().model_dump(mode='json')
    raw['sources']['reads'] = MailchimpSubscriberReadSource().model_dump(mode='json')
    raw['sources']['writes'] = {'adapter': 'service.record_writes@1', 'service': 'mailchimp', 'collection': ['subscribers'], 'kind': 'create'}
    check = raw['checks'][0]
    check['effect_match']['args'][0] = {'op': 'eq', 'left': {'kind': 'field', 'path': ['effect', 'record', 'email']}, 'right': {'kind': 'literal', 'value': 'b@example.test'}}
    check['effect_joins'][0]['where'] = {'op': 'eq', 'left': {'kind': 'field', 'path': ['joined', 'record', 'list_id']}, 'right': {'kind': 'field', 'path': ['effect', 'record', 'list_id']}}
    contract = load_contract(canonical_json(raw));monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _:contract)
    calls = [add(), read()] if scenario == 'late' else [read(), add()]
    task, _, trace = native_fixture(run_operations(initial(), calls), missing_ack=0 if scenario == 'missing' else None)
    rewards = copy.deepcopy(trace.rewards);asyncio.run(task.score(trace))
    findings = {(r.signal.signal_id, r.status, r.value) for r in terminal_records(trace)}
    assert ('expense.status', *expected) in findings, findings
    assert trace.rewards == rewards and not trace.assessment_errors and not trace.credit_errors
    wire = vf.WireEpisode.model_validate({'task': trace.task.model_dump(mode='json'), 'traces': [trace.model_dump(mode='json')]})
    restored = vf.WireEpisode.model_validate_json(wire.model_dump_json()).traces[0]
    restored.state = AutomationBenchState.model_validate(trace.state.model_dump(mode='json'));asyncio.run(task.score(restored))
    assert {(r.signal.signal_id, r.status, r.value) for r in terminal_records(restored)} == findings and restored.rewards == rewards and not restored.assessment_errors
