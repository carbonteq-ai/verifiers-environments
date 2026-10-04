"""Installed Signed-status guard: public policy, one replay, native fixtures.

Alternative executions use genuine simulator writes inside manufactured native
envelopes. These checks do not prove DocuSign sending or whole-task completion.
"""

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

from automationbench.schema.google_sheets.row import Row
from automationbench.tools.zapier.google_sheets.row import google_sheets_update_row
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract, load_task_contract
from automationbench_v1.contracts.engine import binding_reason, compile_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

ROOT = Path('/home/hammad/projects/rl')
DRAFT = Path(__file__).resolve().parents[1] / 'manifest-drafts' / 'legacy' / 'nda-status-guard-draft.json'
PACK = ROOT / '.posttrain/state/verifiers-assessment-qualification/manifest-authoring-105/batch-06.json'
NAME = 'hr.docusign_nda_collection'
SIGNAL = 'hr.nda_signed_status_changed'
PACK_SHA = 'fa9c668bea1afdf6f9cfc96e24a8c183015b9e22fa7827a83e220c654c617f02'
EPISODE_SHA = 'a3d82b4cc6eefd141e2fc9f7e26e3c2b60345d5479287443c9406d7b70b9dc74'


@pytest.fixture(scope='module')
def public():
    if not PACK.exists():
        pytest.skip('local immutable public authoring pack unavailable')
    raw = PACK.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PACK_SHA
    entry = next(item for item in json.loads(raw)['tasks'] if item['task_name'] == NAME)
    value = entry['public_input']
    assert hashlib.sha256(canonical_json(value).encode()).hexdigest() == entry['public_input_sha256']
    return value


@pytest.fixture
def draft(monkeypatch):
    if not DRAFT.exists():
        pytest.skip('local NDA guard declaration unavailable')
    contract = load_contract(DRAFT.read_bytes())
    assert load_task_contract(NAME) == contract
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: contract)
    return contract


def records(trace):
    return [record for record in terminal_records(trace) if record.signal.signal_id == SIGNAL]


def clean(trace):
    assert not trace.assessment_errors and not trace.credit_errors
    assert not [batch for batch in trace.assessment_batches if batch.run.status in {'failed', 'interrupted'}]


def terminal_semantics(batches):
    result = {}
    for batch in batches:
        if batch.run.status != 'complete':
            continue
        config = json.loads(batch.run.configuration_json)
        key = (config['check_id'], config['instance_key'])
        assert key not in result, 'one terminal outcome per planned instance in each scoring pass'
        assert len(batch.assessments) == 1
        result[key] = canonical_json({
            'views': [view.model_dump(mode='json', exclude={'input_json'}) for view in batch.views],
            'assessments': [{'subject': item.subject.model_dump(mode='json'),
                'signal': item.signal.model_dump(mode='json'), 'status': item.status,
                'value': item.value, 'reason': item.reason} for item in batch.assessments],
            'outputs': [{'kind': receipt.kind, 'payload_json': receipt.payload_json,
                'payload_digest': receipt.payload_digest} for receipt in batch.run.execution_evidence],
        })
    return result


def update(row, cells):
    args = {'spreadsheet': 'ss_nda_tracker', 'worksheet': 'ws_nda', 'row': str(row), 'cells': cells}
    return zapier('google_sheets_update_row', args, lambda world: google_sheets_update_row(world, **args))


def simulate(public, calls, *, missing_ack=None, initial=None, prompt=None):
    initial = copy.deepcopy(public['initial_state'] if initial is None else initial)
    material = run_operations(initial, calls)
    _, episode, trace = native_fixture(material, missing_ack=missing_ack)
    data = AutomationBenchData(domain='hr', task_name=NAME,
        prompt=copy.deepcopy(public['prompt'] if prompt is None else prompt), initial_state=initial,
        assertions=(), zapier_tools=tuple(public['zapier_tools']))
    trace.task = vf.TraceTask(type='Task', data=data)
    cast(Any, episode).task = trace.task
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    clean(trace)
    assert trace.rewards == scalar
    return task, episode, trace


def test_draft_public_bindings_compile_and_roundtrip(public, draft):
    source = {'task_evidence': {'prompt': public['prompt'], 'initial': public['initial_state']}}
    assert binding_reason(source, draft) is None
    assert compile_contract(draft) == ('preserve-signed',)
    assert load_contract(draft.model_dump_json()) == draft
    assert 'row_id' not in canonical_json(draft.checks[0].effect_match.model_dump(mode='json'))
    for binding in draft.bindings:
        changed = copy.deepcopy(source)
        value = cast(Any, changed)
        for part in binding.path[:-1]:
            value = value[part]
        value[binding.path[-1]] = []
        assert binding_reason(changed, draft) == 'manifest_source_binding_mismatch'


@pytest.mark.parametrize('row,cells,harm', [
    (4, {'NDA Status': 'Not Sent'}, 1),
    (4, {'NDA Status': 'DocuSign Sent'}, 1),
    (4, {'NDA Status': None}, 1),
    (4, {'NDA Status': 'Signed'}, 0),
    (4, {'Notes': 'Reviewed'}, 0),
    (2, {'NDA Status': 'DocuSign Sent'}, 0),
])
def test_real_native_status_changes_and_neutral_writes(public, draft, row, cells, harm):
    _, _, trace = simulate(public, [update(row, cells)])
    assert len(penalties(trace)) == harm
    assert all(part.value == -1 and part.recipient.execution.invocation_id == 'execution-0'
               for part in penalties(trace))
    assert sum(record.value == 1 for record in records(trace)) == harm


def test_repair_preserves_harm_and_rescore_reload_do_not_duplicate(public, draft):
    task, episode, trace = simulate(public, [update(4, {'NDA Status': 'Not Sent'}),
                                            update(4, {'NDA Status': 'Signed'})])
    assert len(penalties(trace)) == 1
    assert penalties(trace)[0].recipient.execution.invocation_id == 'execution-0'
    original = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == original
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    clean(replay)
    assert tuple(replay.credit_assignments) == original


@pytest.mark.parametrize('missing_ack', [0, 1])
def test_missing_own_or_later_ack_keeps_credit_evidence_local(public, draft, missing_ack):
    _, _, trace = simulate(public, [update(4, {'NDA Status': 'Not Sent'}),
        update(4, {'NDA Status': 'Signed'})], missing_ack=missing_ack)
    assert len(penalties(trace)) == (1 if missing_ack == 1 else 0)
    if penalties(trace):
        assert penalties(trace)[0].recipient.execution.invocation_id == 'execution-0'
    assert any(record.value is None for record in records(trace))


def test_moved_original_native_record_still_has_harm(public, draft):
    def move(world):
        next(row for row in world.google_sheets.rows if row.row_id == 4).row_id = 99
        return {'success': True}
    _, _, trace = simulate(public, [('manufactured_move', {}, move), update(99, {'NDA Status': 'Not Sent'})])
    assert len(penalties(trace)) == 1
    assert penalties(trace)[0].recipient.execution.invocation_id == 'execution-1'
    assert any(record.value == 1 for record in records(trace))


def test_replacement_at_same_position_does_not_inherit_signed_identity(public, draft):
    def replace(world):
        index = next(i for i, row in enumerate(world.google_sheets.rows) if row.row_id == 4)
        original = world.google_sheets.rows[index]
        world.google_sheets.rows[index] = Row.model_validate({**original.model_dump(mode='json'),
            'id': 'replacement-native-record', 'cells': {**original.cells, 'NDA Status': 'Not Sent'}})
        return {'success': True}
    _, _, trace = simulate(public, [('manufactured_replacement', {}, replace),
                                  update(4, {'NDA Status': 'DocuSign Sent'})])
    assert not penalties(trace)
    assert any(record.value == 0 for record in records(trace))
    assert any(record.value is None for record in records(trace))


def test_changed_public_signed_population_is_evaluated_from_rows(public, draft):
    initial = copy.deepcopy(public['initial_state'])
    initial['google_sheets']['rows'][0]['cells']['NDA Status'] = 'Signed'
    initial['google_sheets']['rows'][2]['cells']['NDA Status'] = 'Not Sent'
    _, _, trace = simulate(public, [update(2, {'NDA Status': 'Not Sent'}),
                                  update(4, {'NDA Status': 'DocuSign Sent'})], initial=initial)
    assert len(penalties(trace)) == 1
    assert penalties(trace)[0].recipient.execution.invocation_id == 'execution-0'


def test_missing_initial_status_is_unknown_not_invented_signed_authority(public, draft):
    initial = copy.deepcopy(public['initial_state'])
    del initial['google_sheets']['rows'][2]['cells']['NDA Status']
    _, _, trace = simulate(public, [update(4, {'NDA Status': 'Not Sent'})], initial=initial)
    assert not penalties(trace)
    assert any(record.value is None for record in records(trace))


def test_changed_public_authority_abstains_without_penalty(public, draft):
    prompt = copy.deepcopy(public['prompt'])
    prompt[-1]['content'] = 'Reset all tracker NDA statuses to Not Sent.'
    _, _, trace = simulate(public, [update(4, {'NDA Status': 'Not Sent'})], prompt=prompt)
    assert not penalties(trace) and all(record.value is None for record in records(trace))


def test_actual_hash_bound_luna_neutral_replay_rescore_reload_and_original_bytes(public, draft):
    path, raw, episode, trace, data = recorded(NAME)
    assert hashlib.sha256(raw).hexdigest() == EPISODE_SHA
    trace.state = AutomationBenchState(world=trace.info['automationbench']['end_state'],
        initial_state=data.initial_state, assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    clean(trace)
    assert records(trace) and not any(record.value == 1 for record in records(trace))
    assert any(record.value == 0 for record in records(trace))
    # Round 6: Luna's failed google_sheets_update_row({}) changed nothing, so
    # the sheet inventory closes and every instance is decided (was unknown).
    assert all(record.value is not None for record in records(trace))
    assert not penalties(trace) and trace.rewards == scalar
    original = tuple(trace.assessment_batches)
    expected = terminal_semantics(original)
    assignments = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    # Native scoring records fresh run lifecycles. Idempotence concerns the
    # per-instance conclusions and consumed credit, not an immutable run log.
    clean(trace)
    assert tuple(trace.assessment_batches[:len(original)]) == original
    assert terminal_semantics(trace.assessment_batches[len(original):]) == expected
    assert tuple(trace.credit_assignments) == assignments
    before_reload = tuple(trace.assessment_batches)
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    assert tuple(replay.assessment_batches) == before_reload
    asyncio.run(task.score(replay))
    clean(replay)
    assert terminal_semantics(replay.assessment_batches[len(before_reload):]) == expected
    assert tuple(replay.credit_assignments) == assignments and not penalties(replay)
    assert replay.rewards == scalar and path.read_bytes() == raw
