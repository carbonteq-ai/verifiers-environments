"""Public ticket-status outcome only; resolution email and action credit stay open.

Handlers are real installed simulator calls. Native alternatives use manufactured
validated envelopes; the SHA-bound historical episode is an actual Luna trace.
"""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from test_notification_evidence import run_operations, zapier

from automationbench.tools.api.impl.zendesk import zendesk_tickets_update
from automationbench.tools.zapier.zendesk.tickets import zendesk_update_ticket
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.engine import binding_reason, compile_contract
from automationbench_v1.contracts.loader import load_contract, load_task_contract

ROOT = Path('/home/hammad/projects/rl')
PACK = ROOT / '.posttrain/state/verifiers-assessment-qualification/manifest-authoring-105/batch-10.json'
DRAFT = Path(__file__).resolve().parents[1] / 'manifest-drafts' / 'legacy' / 'zendesk-retained-component-draft.json'
NAME = 'simple.zendesk_resolve_email'
SIGNAL = 'simple.zendesk_requested_ticket_solved'
PACK_SHA = 'a99c6aa6fca047d97221b28679aec5811c74e9c7e651d352c8b5f4161d53e42c'
EPISODE_SHA = 'e04a068ad087b52ff28c8294f99cb539cf7f282c0914a795f654a115bd4439c9'


@pytest.fixture(scope='module')
def public():
    if not PACK.exists():
        pytest.skip('local immutable public task pack unavailable')
    raw = PACK.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PACK_SHA
    entry = next(item for item in json.loads(raw)['tasks'] if item['task_name'] == NAME)
    value = entry['public_input']
    assert hashlib.sha256(canonical_json(value).encode()).hexdigest() == entry['public_input_sha256']
    return value


@pytest.fixture
def draft():
    if not DRAFT.exists():
        pytest.skip('local retained-status review draft unavailable')
    contract = load_contract(DRAFT.read_bytes())
    installed = load_task_contract(NAME)
    assert installed.checks == contract.checks and installed.bindings == contract.bindings
    assert installed.public_request == contract.public_request
    assert installed.revision == 'public_batch10_credit_v2'
    return contract


def update(status='solved', *, ticket='ZD-501', api=False):
    args: dict[str, Any] = {'ticket_id': ticket, 'status': status}
    if api:
        return ('api_fetch', {'method': 'PUT', 'url': f'/zendesk/api/v2/tickets/{ticket}',
            'body': {'ticket': {'status': status}}}, lambda world: zendesk_tickets_update(world, **args))
    return zapier('zendesk_update_ticket', args, lambda world: zendesk_update_ticket(world, **args))


def material(public, calls):
    source = run_operations(public['initial_state'], calls)
    source['task_evidence']['initial'] = copy.deepcopy(public['initial_state'])
    source['task_evidence']['prompt'] = copy.deepcopy(public['prompt'])
    return source


def core(source, draft):
    from automationbench_v1.contracts.populations import capture_population
    from automationbench_v1.contracts.retained_records import (
        capture_record_retention,
        evaluate_retained_records,
    )

    assert binding_reason(source, draft) is None
    check = draft.checks[0]
    population_source, retention_source = draft.sources[check.population], draft.sources[check.source]
    return evaluate_retained_records(source, check,
        {check.population: capture_population(source, population_source)},
        capture_record_retention(source, retention_source),
        population_sources={check.population: population_source}, retention_source=retention_source)


def target(outcome):
    assert len(outcome.findings) == 1
    return outcome.findings[0]


def test_core_public_scope_schema_and_no_credit(public, draft):
    assert compile_contract(draft) == ('requested-ticket-solved',)
    assert load_contract(draft.model_dump_json()) == draft and not draft.credit
    outcome = core(material(public, [update()]), draft)
    assert target(outcome).value == 1
    assert target(outcome).native_record_id == 'ZD-501'


@pytest.mark.parametrize('statuses,expected', [
    ([], 0), (['open'], 0), (['solved'], 1), (['closed'], 0),
    (['solved', 'open'], 0), (['solved', 'open', 'solved'], 1),
    (['solved', 'solved'], 1),
])
def test_core_real_updates_observe_terminal_status_not_first_success(public, draft, statuses, expected):
    assert target(core(material(public, [update(status) for status in statuses]), draft)).value == expected


def test_core_api_and_zapier_produce_same_outcome(public, draft):
    outcomes = [core(material(public, [update(api=api)]), draft) for api in (False, True)]
    assert [target(item).value for item in outcomes] == [1, 1]
    assert target(outcomes[0]).instance_key == target(outcomes[1]).instance_key


@pytest.mark.parametrize('defect', ['missing-status', 'missing-id', 'bool-id', 'duplicate-id',
    'missing-service', 'missing-collection', 'unfinished'])
def test_core_unknown_final_evidence_never_manufactures_solved(public, draft, defect):
    source = material(public, [update()])
    evidence = source['task_evidence']
    tickets = evidence['final']['zendesk']['tickets']
    if defect == 'missing-status':
        tickets[0].pop('status')
    elif defect == 'missing-id':
        tickets[0].pop('id')
    elif defect == 'bool-id':
        tickets[0]['id'] = True
    elif defect == 'duplicate-id':
        tickets.append(copy.deepcopy(tickets[0]))
    elif defect == 'missing-service':
        evidence['final'].pop('zendesk')
    elif defect == 'missing-collection':
        evidence['final']['zendesk'].pop('tickets')
    else:
        evidence['complete'] = False
    assert target(core(source, draft)).value is None


@pytest.mark.parametrize('replacement', [False, True])
def test_core_closed_absence_or_different_native_replacement_is_failure(public, draft, replacement):
    source = material(public, [update()])
    rows = source['task_evidence']['final']['zendesk']['tickets']
    if replacement:
        rows[0]['id'] = 'ZD-other'
    else:
        rows.clear()
    assert target(core(source, draft)).value == 0


def test_core_final_solved_survives_missing_ack_without_action_credit(public, draft):
    source = material(public, [update()])
    source['state_write_receipts'] = []
    source['tool_execution_events'] = []
    assert target(core(source, draft)).value == 1 and not draft.credit


def test_core_wrong_ticket_update_does_not_complete_requested_ticket(public, draft):
    source = material(public, [update(ticket='ZD-other')])
    assert target(core(source, draft)).value == 0


def test_core_unrelated_unknown_fields_and_final_order_do_not_erase_unique_target(public, draft):
    source = material(public, [update()])
    expected = target(core(source, draft))
    rows = source['task_evidence']['final']['zendesk']['tickets']
    rows.insert(0, {'id': 'ZD-other', 'status': 1})
    actual = target(core(source, draft))
    assert actual.value == 1 and actual.instance_key == expected.instance_key
    rows.reverse()
    assert target(core(source, draft)).value == 1


def test_core_forged_retained_projection_is_rejected(public, draft):
    from automationbench_v1.contracts.populations import capture_population
    from automationbench_v1.contracts.retained_records import (
        capture_record_retention,
        evaluate_retained_records,
    )

    source = material(public, [update('open')])
    check = draft.checks[0]
    population_source, final_source = draft.sources[check.population], draft.sources[check.source]
    retained = capture_record_retention(source, final_source)
    forged = retained.model_copy(update={'rows': (retained.rows[0].model_copy(
        update={'cells_json': canonical_json({'status': 'solved'})}),)})
    with pytest.raises(ValueError):
        evaluate_retained_records(source, check,
            {check.population: capture_population(source, population_source)}, forged,
            population_sources={check.population: population_source}, retention_source=final_source)


@pytest.mark.parametrize('changed', ['prompt', 'missing-target', 'replacement-target'])
def test_core_changed_public_authority_invalidates_draft(public, draft, changed):
    source = material(public, [update()])
    if changed == 'prompt':
        source['task_evidence']['prompt'][-1]['content'] = 'Leave ZD-501 open.'
    elif changed == 'missing-target':
        source['task_evidence']['initial']['zendesk']['tickets'] = []
    else:
        source['task_evidence']['initial']['zendesk']['tickets'][0]['id'] = 'ZD-other'
    assert binding_reason(source, draft) == 'manifest_source_binding_mismatch'


def clean(trace):
    assert not trace.assessment_errors and not trace.credit_errors and not trace.credit_assignments
    assert not [batch for batch in trace.assessment_batches if batch.run.status in {'failed', 'interrupted'}]


def native_run(public, draft, monkeypatch, calls, *, missing_ack=None, changed_initial=False, expect_clean=True):
    import verifiers.v1 as vf
    from test_manifest_guard_assessments import native_fixture

    from automationbench_v1 import manifest_assessments
    from automationbench_v1.manifest_assessments import ManifestAssessmentTask
    from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig

    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: draft)
    source = material(public, calls)
    if changed_initial:
        source['task_evidence']['initial']['zendesk']['tickets'] = []
    _, episode, trace = native_fixture(source, missing_ack=missing_ack)
    data = AutomationBenchData(domain='simple', task_name=NAME, prompt=public['prompt'],
        initial_state=source['task_evidence']['initial'], assertions=(), zapier_tools=tuple(public['zapier_tools']))
    trace.task = vf.TraceTask(type='Task', data=data)
    cast(Any, episode).task = trace.task
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    if expect_clean:
        clean(trace)
    assert trace.rewards == scalar
    return task, episode, trace


@pytest.mark.parametrize('statuses,missing_ack,expected', [(['solved'], None, 1),
    (['solved', 'open'], None, 0), (['solved', 'open', 'solved'], None, 1),
    (['solved'], 0, 1)])
def test_native_terminal_status_only_no_action_credit(public, draft, monkeypatch, statuses, missing_ack, expected):
    from test_manifest_guard_assessments import terminal_records

    _, _, trace = native_run(public, draft, monkeypatch, [update(status) for status in statuses],
        missing_ack=missing_ack)
    findings = [item for item in terminal_records(trace) if item.signal.signal_id == SIGNAL]
    assert len(findings) == 1 and findings[0].value == expected


def test_native_missing_public_target_cannot_vacuously_succeed(public, draft, monkeypatch):
    from test_manifest_guard_assessments import terminal_records

    _, _, trace = native_run(public, draft, monkeypatch, [], changed_initial=True)
    findings = terminal_records(trace)
    assert findings and not any(item.value == 1 for item in findings)


@pytest.mark.parametrize('tamper', ['projection', 'raw-source'])
def test_native_forged_view_or_self_consistent_alternate_source_cannot_publish_success(public, draft, monkeypatch, tamper):
    import verifiers.v1 as vf
    from test_manifest_guard_assessments import terminal_records

    from automationbench_v1.manifest_assessments import ManifestAssessmentTask
    from automationbench_v1.manifest_guard_assessments import digest
    from automationbench_v1.manifest_record_retained_assessments import (
        capture_record_retained_inputs,
    )

    original = ManifestAssessmentTask.assessment_requests

    def substituted(self, source):
        result = []
        for name, request in original(self, source):
            view = request.views[0]
            content = json.loads(view.input_json)
            config = json.loads(request.run.configuration_json)
            if tamper == 'raw-source':
                content['source']['task_evidence']['final']['zendesk']['tickets'][0]['status'] = 'solved'
                content.update(capture_record_retained_inputs(content['source'], draft))
                config['source_digest'] = digest(content['source'])
            else:
                retained = json.loads(content['retained_record_terminal_json'])
                retained['final_tickets']['rows'][0]['cells_json'] = canonical_json({'status': 'solved'})
                content['retained_record_terminal_json'] = canonical_json(retained)
            replacement = vf.ObservationView.capture(content, snapshot_id=source.snapshot_id,
                builder_revision=view.builder_revision, scope=view.scope, subjects=view.subjects)
            result.append((name, request.model_copy(update={'views': (replacement,),
                'run': request.run.model_copy(update={'configuration_json': canonical_json(config)})})))
        return result

    monkeypatch.setattr(ManifestAssessmentTask, 'assessment_requests', substituted)
    _, _, trace = native_run(public, draft, monkeypatch, [update('open')], expect_clean=False)
    assert any(batch.run.status == 'failed' for batch in trace.assessment_batches)
    assert not terminal_records(trace) and not trace.credit_assignments


def test_native_direct_assessor_without_executor_sealed_source_is_rejected(public, draft, monkeypatch):
    import verifiers.v1 as vf

    from automationbench_v1.manifest_record_retained_assessments import assess_record_retained

    task, _, trace = native_run(public, draft, monkeypatch, [update()])
    batch = next(batch for batch in trace.assessment_batches if batch.run.status == 'complete')
    request = vf.AssessmentRequest(source=batch.source.identity, run=batch.run, views=batch.views)
    context = vf.AssessmentContext(views=batch.views)
    with pytest.raises(ValueError, match='source'):
        assess_record_retained(task, request, context)


def test_native_actual_recorded_status_rescore_reload_and_scalar(public, draft, monkeypatch):
    import verifiers.v1 as vf
    from test_batch01_manifests import recorded
    from test_manifest_guard_assessments import terminal_records
    from test_nda_status_manifest import terminal_semantics

    from automationbench_v1 import manifest_assessments
    from automationbench_v1.manifest_assessments import ManifestAssessmentTask
    from automationbench_v1.taskset import AutomationBenchTaskConfig
    from automationbench_v1.tools import AutomationBenchState

    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: draft)
    path, raw, episode, trace, data = recorded(NAME)
    assert hashlib.sha256(raw).hexdigest() == EPISODE_SHA
    assert data.model_dump(mode='json')['prompt'] == public['prompt']
    assert data.initial_state == public['initial_state']
    trace.state = AutomationBenchState(world=trace.info['automationbench']['end_state'],
        initial_state=data.initial_state, assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    clean(trace)
    goals = [item for item in terminal_records(trace) if item.signal.signal_id == SIGNAL]
    assert len(goals) == 1 and goals[0].value == 1 and trace.rewards == scalar
    expected = terminal_semantics(trace.assessment_batches)
    count = len(trace.assessment_batches)
    asyncio.run(task.score(trace))
    clean(trace)
    assert terminal_semantics(trace.assessment_batches[count:]) == expected
    retained = tuple(trace.assessment_batches)
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    assert tuple(replay.assessment_batches) == retained
    asyncio.run(task.score(replay))
    clean(replay)
    assert terminal_semantics(replay.assessment_batches[len(retained):]) == expected
    assert replay.rewards == scalar and trace.rewards == scalar and path.read_bytes() == raw
