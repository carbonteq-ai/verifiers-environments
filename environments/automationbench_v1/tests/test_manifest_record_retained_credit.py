"""Manufactured policies qualify record completion credit, not public tasks."""

import asyncio
import copy
import hashlib
import json
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_manifest_zendesk_effects import initial, update
from test_notification_evidence import run_operations

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.loader import load_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_guard_assessments import execution_subject
from automationbench_v1.manifest_record_retained_assessments import (
    RECORD_RETAINED_OUTPUT,
    manifest_record_retained_identity,
)


def contract(*, revision='1', channel='status-completion'):
    return load_contract(canonical_json({
        'schema_version': 1, 'manifest_id': 'manufactured-status-completion', 'revision': revision,
        'public_request': 'Manufactured qualification policy: retain T-1 solved.',
        'sources': {
            'initial': {'adapter': 'initial.records@1', 'path': ['task_evidence', 'initial', 'zendesk', 'tickets'],
                'fields': {'id': ['id'], 'status': ['status']}, 'key_fields': ['id']},
            'final': {'adapter': 'final.records@1', 'path': ['task_evidence', 'final', 'zendesk', 'tickets'],
                'fields': {'status': ['status']}},
            'updates': {'adapter': 'zendesk.ticket_updates@1', 'kind': 'status_update'},
        },
        'checks': [{'check_id': 'ticket-solved', 'signal_id': 'manufactured.ticket_solved', 'role': 'goal',
            'operator': 'records.retained_when@1', 'population': 'initial', 'source': 'final',
            'required_when': {'op': 'eq', 'left': {'kind': 'field', 'path': ['request', 'id'], 'domain': 'string'},
                'right': {'kind': 'literal', 'value': 'T-1'}},
            'retained_when': {'op': 'eq', 'left': {'kind': 'field', 'path': ['retained', 'status'], 'domain': 'string'},
                'right': {'kind': 'literal', 'value': 'solved'}}}],
        'credit': [{'check': 'ticket-solved', 'policy': 'records_retained_completion_once@1',
            'channel': channel, 'effects': 'updates', 'goal_fields': ['status'], 'completion_selection': 'earliest'}],
    }))


def scored(monkeypatch, *, calls=None, public=None, missing_ack=None, declaration=None):
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: declaration or contract())
    public = initial() if public is None else public
    material = run_operations(public, calls if calls is not None else [update()])
    material['task_evidence']['initial'] = copy.deepcopy(public)
    task, episode, trace = native_fixture(material, missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar
    return task, episode, trace


def clean(trace):
    assert not trace.assessment_errors and not trace.credit_errors
    assert not [batch for batch in trace.assessment_batches if batch.run.status in {'failed', 'interrupted'}]


def goal(trace):
    return next(item for item in terminal_records(trace)
        if item.signal.signal_id == 'manufactured.ticket_solved' and item.status == 'valid')


def test_exact_completion_recipient_rescore_and_native_reload_consume_once(monkeypatch):
    task, episode, trace = scored(monkeypatch)
    clean(trace)
    assert goal(trace).value == 1
    (credit,) = penalties(trace)
    assert credit.value == 1 and credit.transformation == 'records_retained_completion_identity@1'
    assert credit.recipient.execution.invocation_id == 'execution-0'
    assert credit.parent_assessment_ids == (goal(trace).assessment_id,)
    original = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    clean(trace)
    assert tuple(trace.credit_assignments) == original
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    clean(replay)
    assert tuple(replay.credit_assignments) == original and replay.rewards == trace.rewards


@pytest.mark.parametrize('statuses,count,witness', [([], 0, None), (['open'], 0, None),
    (['solved', 'open'], 0, None), (['solved', 'open', 'solved'], 1, 'execution-0'),
    (['pending', 'solved'], 1, 'execution-1'), (['solved', 'solved'], 1, 'execution-0')])
def test_earliest_declared_completion_distinct_from_last_repair(monkeypatch, statuses, count, witness):
    _, _, trace = scored(monkeypatch, calls=[update(status) for status in statuses])
    clean(trace)
    assert len(penalties(trace)) == count
    if witness is not None:
        assert penalties(trace)[0].recipient.execution.invocation_id == witness


@pytest.mark.parametrize('method', ['PUT', 'PATCH'])
def test_genuine_api_fetch_qualifies_same_native_ticket(monkeypatch, method):
    _, _, trace = scored(monkeypatch, calls=[update(method=method)])
    clean(trace)
    assert goal(trace).value == 1 and len(penalties(trace)) == 1


def test_initially_satisfied_break_restore_has_no_progress_credit(monkeypatch):
    _, _, trace = scored(monkeypatch, public=initial('solved'), calls=[update('open'), update()])
    clean(trace)
    assert goal(trace).value == 1 and not penalties(trace)


def test_unknown_initial_status_cannot_be_inferred_from_hydrated_before_world(monkeypatch):
    public = initial()
    del public['zendesk']['tickets'][0]['status']
    _, _, trace = scored(monkeypatch, public=public)
    clean(trace)
    assert goal(trace).value == 1 and not penalties(trace)


def test_missing_completion_ack_keeps_outcome_but_no_credit(monkeypatch):
    _, _, trace = scored(monkeypatch, missing_ack=0)
    clean(trace)
    assert goal(trace).value == 1 and not penalties(trace)


def test_unrelated_later_missing_ack_preserves_known_earliest_completion(monkeypatch):
    _, _, trace = scored(monkeypatch, calls=[update(), update(identity='T-2')], missing_ack=1)
    clean(trace)
    assert goal(trace).value == 1 and penalties(trace)[0].recipient.execution.invocation_id == 'execution-0'


@pytest.mark.parametrize('mutation', ['missing', 'native_record_id', 'value'])
def test_tampered_current_parent_receipt_cannot_authorize_credit(monkeypatch, mutation):
    original = ManifestAssessmentTask.plan_credit

    def altered(self, source, assessments, context):
        changed = []
        for batch in assessments:
            receipts = []
            for receipt in batch.run.execution_evidence:
                payload = json.loads(receipt.payload_json)
                if receipt.kind == RECORD_RETAINED_OUTPUT and payload.get('kind') == 'finding':
                    if mutation == 'missing':
                        continue
                    payload[mutation] = 'foreign' if mutation == 'native_record_id' else 0
                    receipt = vf.ExecutionEvidence.capture(receipt.kind, payload, invocation_id=receipt.invocation_id)
                receipts.append(receipt)
            changed.append(batch.model_copy(update={'run': batch.run.model_copy(update={'execution_evidence': tuple(receipts)})}))
        return original(self, source, tuple(changed), context)

    monkeypatch.setattr(ManifestAssessmentTask, 'plan_credit', altered)
    _, _, trace = scored(monkeypatch)
    assert trace.credit_errors and not penalties(trace)


def test_failed_current_attempt_cannot_reuse_successful_historical_parent(monkeypatch):
    task, _, trace = scored(monkeypatch)
    clean(trace)
    # Retain successful outcome history but remove its contribution. A failed
    # fresh wave must not turn an older complete outcome into a current parent.
    trace.credit_assignments = ()
    original = ManifestAssessmentTask.plan_credit

    def failed(self, source, assessments, context):
        current = {run.run_id for run in context.current_assessment_runs}
        changed = tuple(batch.model_copy(update={'run': batch.run.model_copy(update={'status': 'failed'})})
            if batch.run.run_id in current else batch for batch in assessments)
        return original(self, source, changed, context)

    monkeypatch.setattr(ManifestAssessmentTask, 'plan_credit', failed)
    asyncio.run(task.score(trace))
    assert not penalties(trace)


def test_changed_source_and_witness_cannot_reset_stable_consumption(monkeypatch):
    _, _, prefix = scored(monkeypatch)
    clean(prefix)
    material = run_operations(initial(), [update('pending'), update()])
    material['task_evidence']['initial'] = initial()
    task, _, extended = native_fixture(material)
    extended.id = prefix.id
    extended.credit_assignments = prefix.credit_assignments
    asyncio.run(task.score(extended))
    clean(extended)
    assert len(penalties(extended)) == 1
    assert penalties(extended)[0].recipient.execution.invocation_id == 'execution-0'


@pytest.mark.parametrize('ending', ['failed', 'interrupted'])
def test_actual_partial_yield_then_failure_or_cancel_consumes_once_on_rescore_and_reload(monkeypatch, ending):
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: contract())
    material = run_operations(initial(), [update()])
    material['task_evidence']['initial'] = initial()
    task, episode, trace = native_fixture(material)
    original = manifest_assessments.manifest_record_retained_identity

    async def yield_then_stop(task, request):
        contributions = await original(task, request)

        async def stream():
            yield contributions[0]
            if ending == 'interrupted':
                raise asyncio.CancelledError
            raise RuntimeError('manufactured interruption after valid native yield')

        return stream()

    monkeypatch.setattr(manifest_assessments, 'manifest_record_retained_identity', yield_then_stop)
    if ending == 'interrupted':
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(task.score(trace))
    else:
        asyncio.run(task.score(trace))
    assert [assignment.status for assignment in trace.credit_assignments] == ['running', 'partial', ending]
    valid_ids = {part.contribution_id for assignment in trace.credit_assignments
                 for part in assignment.contributions if part.status == 'valid'}
    assert len(valid_ids) == 1
    before = tuple(trace.credit_assignments)
    scalar = copy.deepcopy(trace.rewards)
    monkeypatch.setattr(manifest_assessments, 'manifest_record_retained_identity', original)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == before and trace.rewards == scalar
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert tuple(replay.credit_assignments) == before and replay.rewards == scalar


@pytest.mark.parametrize('change', ['revision', 'signal', 'effects-alias'])
def test_changed_reward_meaning_rejects_mixed_ledger_for_same_obligation(monkeypatch, change):
    task, _, trace = scored(monkeypatch)
    clean(trace)
    original = tuple(trace.credit_assignments)
    raw = contract().model_dump(mode='json')
    if change == 'revision':
        raw['revision'] = '2'
    elif change == 'signal':
        raw['checks'][0]['signal_id'] = 'manufactured.other_status_meaning'
    else:
        raw['sources']['renamed_updates'] = raw['sources'].pop('updates')
        raw['credit'][0]['effects'] = 'renamed_updates'
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: load_contract(canonical_json(raw)))
    asyncio.run(task.score(trace))
    assert trace.credit_errors and tuple(trace.credit_assignments) == original


def test_coherent_target_and_witness_forgery_cannot_reassign_completion(monkeypatch):
    task, _, trace = scored(monkeypatch, calls=[update(), update()])
    clean(trace)
    request = trace.credit_assignments[0].request
    config = json.loads(request.rule.configuration_json)
    config['allocation_witness'].update(occurrence='execution-1', expected_revision=1, applied_revision=2)
    target = request.targets[0].model_copy(update={'recipient': execution_subject(request.source, 'execution-1')})
    forged = request.model_copy(update={'targets': (target,),
        'rule': request.rule.model_copy(update={'configuration_json': canonical_json(config)})})
    with pytest.raises(ValueError, match='allocation_proof_mismatch'):
        asyncio.run(manifest_record_retained_identity(task, forged))


def test_direct_projector_requires_full_source_and_task_proof(monkeypatch):
    _, _, trace = scored(monkeypatch)
    clean(trace)
    with pytest.raises(ValueError, match='source_proof_unavailable'):
        asyncio.run(manifest_record_retained_identity(None, trace.credit_assignments[0].request))


def test_projector_rejects_declared_effect_selector_digest_tamper(monkeypatch):
    task, _, trace = scored(monkeypatch)
    clean(trace)
    request = trace.credit_assignments[0].request
    config = json.loads(request.rule.configuration_json)
    config['effects_selector_digest'] = '0' * 64
    forged = request.model_copy(update={'rule': request.rule.model_copy(update={'configuration_json': canonical_json(config)})})
    with pytest.raises(ValueError, match='effect_selector_mismatch'):
        asyncio.run(manifest_record_retained_identity(task, forged))


@pytest.mark.parametrize('field', ['expected_revision', 'applied_revision', 'value'])
def test_boolean_witness_metadata_is_not_a_numeric_proof(monkeypatch, field):
    task, _, trace = scored(monkeypatch)
    clean(trace)
    request = trace.credit_assignments[0].request
    config = json.loads(request.rule.configuration_json)
    config['allocation_witness'][field] = True
    forged = request.model_copy(update={'rule': request.rule.model_copy(update={'configuration_json': canonical_json(config)})})
    with pytest.raises(ValueError):
        asyncio.run(manifest_record_retained_identity(task, forged))


def test_effect_selector_is_part_of_credit_consumption_meaning(monkeypatch):
    _, _, trace = scored(monkeypatch)
    clean(trace)
    config = json.loads(trace.credit_assignments[0].request.rule.configuration_json)
    parent_batch = next(batch for batch in trace.assessment_batches if batch.run.status == 'complete')
    outcome = json.loads(parent_batch.run.configuration_json)
    assert config['consumption']['selectors_digest'] != outcome['selectors_digest']
    assert config['effects'] == 'updates' and config['completion_selection'] == 'earliest'


def test_same_execution_channel_for_multiple_goals_requires_explicit_aggregation(monkeypatch):
    raw = contract().model_dump(mode='json')
    other = copy.deepcopy(raw['checks'][0])
    other['check_id'] = 'ticket-solved-again'
    raw['checks'].append(other)
    rule = copy.deepcopy(raw['credit'][0])
    rule['check'] = other['check_id']
    raw['credit'].append(rule)
    _, _, trace = scored(monkeypatch, declaration=load_contract(canonical_json(raw)))
    assert trace.credit_errors and not penalties(trace)


def test_actual_luna_public_status_completion_credit_retains_original_provenance_once(monkeypatch):
    from test_batch01_manifests import recorded
    from test_nda_status_manifest import terminal_semantics

    from automationbench_v1.contracts.loader import load_task_contract
    from automationbench_v1.contracts.zendesk_effects import (
        ZendeskTicketEffectSource,
        capture_zendesk_ticket_effects,
    )
    from automationbench_v1.taskset import AutomationBenchTaskConfig
    from automationbench_v1.tools import AutomationBenchState

    name = 'simple.zendesk_resolve_email'
    original_recipient = 'a19b0f39ad6f4d81ae756b8b93d2daa0'
    installed = load_task_contract(name)
    raw_contract = installed.model_dump(mode='json')
    raw_contract['revision'] = 'public_batch10_credit_v2'
    raw_contract['sources']['initial_tickets']['fields']['status'] = ['status']
    raw_contract['sources']['writes'] = {'adapter': 'zendesk.ticket_updates@1', 'kind': 'status_update'}
    raw_contract['credit'] = [{'check': 'requested-ticket-solved', 'policy': 'records_retained_completion_once@1',
        'channel': 'ticket-status-completion', 'effects': 'writes', 'goal_fields': ['status'],
        'completion_selection': 'earliest'}]
    public_contract = load_contract(canonical_json(raw_contract))
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: public_contract)
    path, raw, episode, trace, data = recorded(name)
    assert hashlib.sha256(raw).hexdigest() == 'e04a068ad087b52ff28c8294f99cb539cf7f282c0914a795f654a115bd4439c9'
    assert trace.id == '53ebbeba533d417183fda46331d2c5d2'
    trace.state = AutomationBenchState(world=trace.info['automationbench']['end_state'],
        initial_state=data.initial_state, assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    events, writes = tuple(trace.tool_execution_events), tuple(trace.state_write_receipts)
    asyncio.run(task.score(trace))
    clean(trace)
    outcomes = [item for item in terminal_records(trace)
                if item.signal.signal_id == 'simple.zendesk_requested_ticket_solved']
    assert len(outcomes) == 1 and outcomes[0].value == 1
    (credit,) = penalties(trace)
    assert credit.value == 1 and credit.recipient.execution.invocation_id == original_recipient
    assert credit.recipient.execution.origin == 'tool_server'
    assert credit.parent_assessment_ids == (outcomes[0].assessment_id,)
    assert credit.transformation == 'records_retained_completion_identity@1'
    request = next(item.request for item in trace.credit_assignments if item.status == 'complete')
    assert isinstance(request.source, vf.SourceSnapshot)
    source = json.loads(request.source.source_json)
    safe = {'task_evidence': source['task_evidence'], 'tool_execution_events': source['tool_execution_events'],
            'state_write_receipts': source['state_write_receipts']}
    facts = capture_zendesk_ticket_effects(safe, ZendeskTicketEffectSource())
    (fact,) = [item for item in facts.effects if item.status == 'qualified' and item.invocation_id == original_recipient]
    params = json.loads(cast(str, fact.params_json))
    assert params['native_record_id'] == 'ZD-501'
    assert params['before_fields']['status'] == 'open' and params['after_fields']['status'] == 'solved'
    witness = json.loads(request.rule.configuration_json)['allocation_witness']
    assert witness['effect_id'] == fact.effect_id
    assert (witness['expected_revision'], witness['applied_revision']) == (fact.expected_revision, fact.applied_revision)
    assert credit.recipient == execution_subject(request.source, original_recipient)
    assert not facts.complete, 'unrelated Gmail calls stay outside Zendesk occurrence coverage'
    expected = terminal_semantics(trace.assessment_batches)
    retained_credit = tuple(trace.credit_assignments)
    count = len(trace.assessment_batches)
    asyncio.run(task.score(trace))
    clean(trace)
    assert terminal_semantics(trace.assessment_batches[count:]) == expected
    assert tuple(trace.credit_assignments) == retained_credit
    before_reload = tuple(trace.assessment_batches)
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    assert tuple(replay.assessment_batches) == before_reload
    asyncio.run(task.score(replay))
    clean(replay)
    assert terminal_semantics(replay.assessment_batches[len(before_reload):]) == expected
    assert tuple(replay.credit_assignments) == retained_credit
    assert tuple(replay.tool_execution_events) == events and tuple(replay.state_write_receipts) == writes
    assert replay.rewards == scalar and trace.rewards == scalar and path.read_bytes() == raw
    assert load_task_contract(name) == installed, 'qualification must not mutate the installed public contract'
