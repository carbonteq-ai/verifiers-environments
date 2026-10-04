"""Public Contact/read draft: real handlers in manufactured native envelopes.

The SHA-bound historical gate is separate. Neither path establishes comprehension
or compliance with conditional narrative rules absent complete message capture.
"""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_contact_task_manifests import actual, manufactured, public, update
from test_manifest_guard_assessments import penalties, terminal_records
from test_notification_evidence import zapier

from automationbench.tools.api.fetch import api_fetch
from automationbench.tools.zapier.gmail.message import gmail_find_email, gmail_get_email_by_id
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract, load_task_contract
from automationbench_v1.contracts.engine import binding_reason, compile_contract
from automationbench_v1.contracts.gmail_observations import (
    GmailObservationSource,
    capture_gmail_observations,
)
from automationbench_v1.manifest_guard_assessments import execution_subject

NAME = 'simple.email_sf_contact_assistant_update'
SIGNAL = 'simple.original_introduction_returned'
DRAFT = Path(__file__).resolve().parents[1] / 'manifest-drafts' / 'legacy' / 'contact-assistant-read-draft.json'
EPISODE_SHA = '05c81896501fa361b1d35d1388d1e7300eee468b1aacd8b2cced895dafeee037'


@pytest.fixture
def draft(monkeypatch):
    if not DRAFT.exists():
        pytest.skip('local public draft unavailable')
    declaration = load_contract(DRAFT.read_bytes())
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: declaration)
    return declaration


def read(kind='get', *, format='full', identity='msg_3010'):
    args: dict[str, Any]
    if kind == 'api':
        args = {'url': 'https://gmail.googleapis.com/gmail/v1/users/me/messages/' + identity,
                'method': 'GET', 'params': {'format': format}}
        return 'api_fetch', args, lambda world: api_fetch(world, **args)
    if kind == 'find':
        args = {'query': 'Rachel Nguyen assistant', 'format': format}
        return zapier('gmail_find_email', args, lambda world: gmail_find_email(world, **args))
    args = {'message_id': identity, 'format': format}
    return zapier('gmail_get_email_by_id', args, lambda world: gmail_get_email_by_id(world, **args))


def clean(trace):
    assert not trace.assessment_errors and not trace.credit_errors
    assert not [batch for batch in trace.assessment_batches if batch.run.status in {'failed', 'interrupted'}]


def latest(trace, signal=SIGNAL):
    return next(item for item in reversed(terminal_records(trace)) if item.signal.signal_id == signal)


def recipients(trace):
    return {item.channel: item.recipient.execution.invocation_id for item in penalties(trace)}


def wave(batches):
    result = {}
    for batch in batches:
        if batch.run.status != 'complete':
            continue
        config = json.loads(batch.run.configuration_json)
        key = (config['check_id'], config.get('instance_key'))
        assert key not in result
        result[key] = canonical_json({
            'assessments': [{'subject': item.subject.model_dump(mode='json'),
                'signal': item.signal.model_dump(mode='json'), 'status': item.status,
                'value': item.value, 'reason': item.reason} for item in batch.assessments],
            # The legacy Contact adapter hydrates omitted initial timestamps
            # on each pass. Compare published meaning, not incidental view IDs.
        })
    return result


def score(calls, **kwargs):
    episode, trace, task = manufactured(NAME, calls=calls, **kwargs)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    clean(trace)
    assert trace.rewards == scalar
    return episode, trace, task


def test_draft_public_binding_and_full_contact_fields_are_preserved(draft):
    source = public(NAME)
    material = {'task_evidence': {'initial': source['initial_state'], 'prompt': source['prompt']}}
    assert binding_reason(material, draft) is None
    assert set(compile_contract(draft)) == {'requested-state', 'recording-coverage', 'original-introduction-returned'}
    installed = load_task_contract(NAME)
    assert draft.bindings == installed.bindings and draft.checks[:2] == installed.checks[:2]
    assert draft.credit[0] == installed.credit[0]
    assert hashlib.sha256(canonical_json(source).encode()).hexdigest() == 'f76ffbe187dcb168a90243c7cf970badd9d5eb8ee8cef742b4171088bfa229a5'


@pytest.mark.parametrize('kind', ['find', 'get', 'api'])
def test_real_handler_alternatives_return_original_and_update_both_fields(draft, kind):
    _, trace, _ = score([read(kind), update(NAME)])
    assert latest(trace).value == 1 and latest(trace, 'simple.requested_state').value == 1
    assert recipients(trace) == {'original-message-read': 'execution-0', 'goal': 'execution-1'}
    assert len(penalties(trace)) == 2 and all(item.value == 1 for item in penalties(trace))


@pytest.mark.parametrize('kind,format', [('get', 'minimal'), ('get', 'metadata'), ('find', 'minimal'), ('api', 'minimal')])
def test_metadata_or_snippet_does_not_backfill_original_body(draft, kind, format):
    _, trace, _ = score([read(kind, format=format), update(NAME)])
    assert latest(trace).value is None and latest(trace).status == 'abstained'
    assert recipients(trace) == {'goal': 'execution-1'}


def test_wrong_message_result_cannot_discharge_original_read(draft):
    _, trace, _ = score([read(identity='missing-message'), update(NAME)])
    assert latest(trace).value != 1 and recipients(trace) == {'goal': 'execution-1'}


def test_contact_noop_is_independent_of_successful_read(draft):
    _, trace, _ = score([read(), update(NAME, fields={'assistant_name': '', 'assistant_email': ''})])
    assert latest(trace).value == 1 and latest(trace, 'simple.requested_state').value == 0
    assert recipients(trace) == {'original-message-read': 'execution-0'}


def test_missing_read_ack_does_not_invent_observation_credit(draft):
    _, trace, _ = score([read(), update(NAME)], missing_ack=0)
    assert latest(trace).value is None and not penalties(trace)
    assert latest(trace, 'simple.requested_state').value == 1


def test_repeated_reads_and_writes_consume_each_obligation_once_after_reload(draft):
    episode, trace, task = score([read(), read(), update(NAME), update(NAME)])
    assert recipients(trace) == {'original-message-read': 'execution-0', 'goal': 'execution-2'}
    credits = tuple(trace.credit_assignments)
    expected = wave(trace.assessment_batches)
    count = len(trace.assessment_batches)
    asyncio.run(task.score(trace))
    clean(trace)
    assert wave(trace.assessment_batches[count:]) == expected and tuple(trace.credit_assignments) == credits
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    count = len(replay.assessment_batches)
    asyncio.run(task.score(replay))
    clean(replay)
    assert wave(replay.assessment_batches[count:]) == expected and tuple(replay.credit_assignments) == credits


@pytest.mark.parametrize('mutation', ['author', 'body', 'inventory', 'system'])
def test_policy_inventory_or_author_drift_does_not_grade_stale_request(draft, mutation):
    source = public(NAME)
    initial, prompt = source['initial_state'], source['prompt']
    message = initial['gmail']['messages'][0]
    if mutation == 'author':
        message['from_'] = 'another@example.com'
    elif mutation == 'body':
        message['body_plain'] = 'My assistant is someone else.'
    elif mutation == 'inventory':
        initial['gmail']['messages'].append(dict(message, id='additional-introduction'))
    else:
        prompt[0]['content'] += ' Do not access Gmail.'
    _, trace, _ = score([read(), update(NAME)], initial=initial, prompt=prompt)
    assert latest(trace).value is None and not penalties(trace)


def test_actual_luna_original_return_credit_preserves_bytes_scalars_and_recipient(draft):
    installed = load_task_contract(NAME)
    path, raw, episode, trace, task = actual(NAME)
    assert hashlib.sha256(raw).hexdigest() == EPISODE_SHA
    assert trace.id == '832e7007cb714d7291754e96e0c72d2c'
    scalar = copy.deepcopy(trace.rewards)
    events, writes = tuple(trace.tool_execution_events), tuple(trace.state_write_receipts)
    asyncio.run(task.score(trace))
    clean(trace)
    assert latest(trace).value == 1 and latest(trace, 'simple.requested_state').value == 1
    assert recipients(trace) == {'original-message-read': 'eb45e8e2c5c648c1bce3fdb9994f3c29',
        'goal': '8baf7cd9ff6549b49fd1f565a59ad93a'}
    assert len(penalties(trace)) == 2 and all(item.value == 1 for item in penalties(trace))
    credit = next(item for item in penalties(trace) if item.channel == 'original-message-read')
    assignment = next(item for item in trace.credit_assignments if item.status == 'complete'
        and credit in item.contributions)
    assert isinstance(assignment.request.source, vf.SourceSnapshot)
    source = json.loads(assignment.request.source.source_json)
    expected_public = public(NAME)
    assert source['task_evidence']['initial'] == expected_public['initial_state']
    assert source['task_evidence']['prompt'] == expected_public['prompt']
    safe = {key: source[key] for key in ('task_evidence', 'tool_execution_events', 'state_write_receipts')}
    facts = capture_gmail_observations(safe, GmailObservationSource())
    (fact,) = [item for item in facts.effects if item.status == 'qualified'
        and item.invocation_id == 'eb45e8e2c5c648c1bce3fdb9994f3c29']
    params = json.loads(cast(str, fact.params_json))
    original = public(NAME)['initial_state']['gmail']['messages'][0]
    assert params['native_record_id'] == original['id'] and params['body_plain'] == original['body_plain']
    assert params['from_'] == original['from_']
    assert credit.recipient == execution_subject(assignment.request.source, fact.invocation_id)
    assert credit.parent_assessment_ids == (latest(trace).assessment_id,)
    expected = wave(trace.assessment_batches)
    credits = tuple(trace.credit_assignments)
    count = len(trace.assessment_batches)
    asyncio.run(task.score(trace))
    clean(trace)
    assert wave(trace.assessment_batches[count:]) == expected and tuple(trace.credit_assignments) == credits
    before = tuple(trace.assessment_batches)
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    assert tuple(replay.assessment_batches) == before
    asyncio.run(task.score(replay))
    clean(replay)
    assert wave(replay.assessment_batches[len(before):]) == expected and tuple(replay.credit_assignments) == credits
    assert tuple(replay.tool_execution_events) == events and tuple(replay.state_write_receipts) == writes
    assert trace.rewards == scalar and replay.rewards == scalar and path.read_bytes() == raw
    assert load_task_contract(NAME) == installed
