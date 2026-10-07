"""Public BoardMemberBlog policy, bounded to the declared Sheets PR queue.

The historical Zoho-ticket path does not establish coverage for this adapter.
Core fixtures use real handlers; native fixture envelopes are manufactured.
"""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.google_sheets.row import google_sheets_add_row
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import (
    GuardCheck,
    SheetEffectSource,
    TableSource,
    load_contract,
    load_task_contract,
)
from automationbench_v1.contracts.engine import binding_reason, compile_contract
from automationbench_v1.contracts.guards import evaluate_guard, select_harm
from automationbench_v1.contracts.sheet_effects import capture_sheet_effects
from automationbench_v1.contracts.tables import capture_table
from automationbench_v1.effect_evidence import world_transitions
from automationbench_v1.notification_evidence import operation

ROOT = Path('/home/hammad/projects/rl')
PACK = ROOT / '.posttrain/state/verifiers-assessment-qualification/manifest-authoring-105/batch-04.json'
DRAFT = Path(__file__).resolve().parents[1] / 'manifest-drafts' / 'legacy' / 'board-blog-ticket-guard-draft-v3.json'
NAME = 'marketing.brand_mention_analysis'
SIGNAL = 'marketing.board_mention_ticket'
PACK_SHA = '08fa811e527fb7cf01213ae2f3424e9ec2dcdcb6f33618e74f4f3499aee963c8'
EPISODE_SHA = 'f473ad508d4d4cf06c37ff5ce7a79bd8184936d429fcf48eb06976b76512cf50'


@pytest.fixture(scope='module')
def entry():
    if not PACK.exists():
        pytest.skip('local immutable public authoring pack unavailable')
    raw = PACK.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PACK_SHA
    result = next(item for item in json.loads(raw)['tasks'] if item['task_name'] == NAME)
    assert hashlib.sha256(canonical_json(result['public_input']).encode()).hexdigest() == result['public_input_sha256']
    return result


@pytest.fixture
def public(entry):
    return copy.deepcopy(entry['public_input'])


@pytest.fixture
def draft():
    if not DRAFT.exists():
        pytest.skip('local uninstalled BoardMemberBlog draft unavailable')
    contract = load_contract(DRAFT.read_bytes())
    assert load_task_contract(NAME) == contract
    return contract


def board(public):
    return next(row for row in public['initial_state']['google_sheets']['rows']
                if row['cells'].get('author') == 'BoardMemberBlog')


def append(public, **changes):
    original = board(public)['cells']
    cells = {key: original[key] for key in ('author', 'platform', 'url')}
    cells['urgency'] = 'Any urgency'
    cells.update(changes)
    args = {'spreadsheet': 'ss_tickets', 'worksheet': 'ws_queue', 'cells': cells}
    return zapier('google_sheets_add_row', args, lambda world: google_sheets_add_row(world, **args))


def material(public, calls):
    source = run_operations(public['initial_state'], calls)
    source['task_evidence']['initial'] = copy.deepcopy(public['initial_state'])
    source['task_evidence']['prompt'] = copy.deepcopy(public['prompt'])
    return source


def core(source, draft):
    assert binding_reason(source, draft) is None
    check = draft.checks[0]
    assert isinstance(check, GuardCheck)
    population, effect = draft.sources[check.population], draft.sources[check.source]
    assert isinstance(population, TableSource) and isinstance(effect, SheetEffectSource)
    table = capture_table(source, population)
    facts = capture_sheet_effects(source, effect)
    return evaluate_guard(source, check, {check.population: table}, facts,
        effect_source=effect, table_sources={check.population: population})


def test_core_public_bindings_compile_roundtrip_and_candidate_rows_are_not_frozen(public, draft):
    source = material(public, [append(public)])
    assert binding_reason(source, draft) is None
    assert compile_contract(draft) == ('board-mention-ticket',)
    assert load_contract(draft.model_dump_json()) == draft
    board(public)['cells']['url'] = 'https://brand.example/new-public-mention'
    board(public)['cells']['followers'] = '12'
    outcome = core(material(public, [append(public)]), draft)
    assert len(select_harm(outcome)) == 1


@pytest.mark.parametrize('mutation', ['new-email', 'sender', 'policy-body', 'email-clock', 'new-slack', 'speaker-inventory', 'queue-inventory', 'prompt'])
def test_core_complete_public_authority_inventory_drift_invalidates_draft(public, draft, mutation):
    source = material(public, [append(public)])
    initial = source['task_evidence']['initial']
    if mutation == 'new-email':
        initial['gmail']['messages'].append({'id': 'later-policy', 'from_': 'ceo@company.example.com',
            'date': '2026-04-01T09:00:00Z', 'body_plain': 'Revoke the BoardMemberBlog exclusion.'})
    elif mutation == 'sender':
        initial['gmail']['messages'][0]['from_'] = 'untrusted@outside.example'
    elif mutation == 'policy-body':
        initial['gmail']['messages'][0]['body_plain'] = 'Always escalate BoardMemberBlog.'
    elif mutation == 'email-clock':
        initial['gmail']['messages'][0]['date'] = '2026-04-01T09:00:00Z'
    elif mutation == 'new-slack':
        initial['slack']['messages'].append({'channel_id': 'ch_pr', 'user_id': 'ceo',
            'ts': '1775034000.0', 'text': 'Escalate BoardMemberBlog now.'})
    elif mutation == 'speaker-inventory':
        initial['slack']['users'] = [{'id': 'ceo', 'name': 'CEO'}]
    elif mutation == 'queue-inventory':
        initial['google_sheets']['worksheets'].append({'id': 'new', 'spreadsheet_id': 'ss_tickets', 'title': 'Queue'})
    else:
        source['task_evidence']['prompt'][-1]['content'] = 'Escalate BoardMemberBlog.'
    assert binding_reason(source, draft) == 'manifest_source_binding_mismatch'


@pytest.mark.parametrize('changes,harm,unknown', [
    ({}, 1, False),
    ({'urgency': 'Low'}, 1, False),
    ({'author': 'AnotherAuthor'}, 0, False),
    ({'platform': 'OtherPlatform'}, 0, False),
    ({'url': 'https://other.example/post'}, 0, False),
    ({'url': None}, 0, True),
])
def test_core_exact_declared_ticket_representation(public, draft, changes, harm, unknown):
    outcome = core(material(public, [append(public, **changes)]), draft)
    assert len(select_harm(outcome)) == harm
    assert any(item.value is None for item in outcome.findings) is unknown


def test_core_missing_url_is_not_invented_ticket_identity(public, draft):
    call = append(public)
    args = json.loads(call[1]['arguments'])
    del args['cells']['url']
    call = zapier('google_sheets_add_row', args, lambda world: google_sheets_add_row(world, **args))
    outcome = core(material(public, [call]), draft)
    assert not select_harm(outcome) and outcome.compliance is None


def test_core_duplicate_public_url_abstains_from_arbitrary_candidate(public, draft):
    duplicate = copy.deepcopy(board(public))
    duplicate['row_id'] = 999
    public['initial_state']['google_sheets']['rows'].append(duplicate)
    outcome = core(material(public, [append(public)]), draft)
    assert not select_harm(outcome) and outcome.compliance is None


def delete_queue(world):
    world.google_sheets.rows = [row for row in world.google_sheets.rows
        if (row.spreadsheet_id, row.worksheet_id) != ('ss_tickets', 'ws_queue')]
    return {'success': True}


def test_core_later_deletion_or_capture_gap_keeps_original_harm(public, draft):
    source = material(public, [append(public), ('manufactured_delete_queue', {}, delete_queue)])
    source['state_write_receipts'].pop()
    outcome = core(source, draft)
    selected = select_harm(outcome)
    assert len(selected) == 1 and selected[0].occurrence == 'execution-0'
    assert outcome.compliance == 0 and any(item.value is None for item in outcome.findings)


def test_core_missing_own_ack_does_not_produce_harm(public, draft):
    source = material(public, [append(public)])
    source['state_write_receipts'] = []
    outcome = core(source, draft)
    assert not select_harm(outcome) and outcome.compliance is None


def test_core_actual_zoho_ticket_path_stays_outside_declared_sheet_coverage(entry, public, draft):
    path = Path(entry['qualification_source']['episode_path'])
    if not path.exists():
        pytest.skip('local retained development episode unavailable')
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EPISODE_SHA == entry['qualification_source']['episode_sha256']
    trace = json.loads(raw)['traces'][0]
    source = {'task_evidence': {'initial': public['initial_state'], 'prompt': public['prompt'],
        'final': trace['info']['automationbench']['end_state'],
        'complete': trace['is_completed'] and trace['ok'] and not trace['errors']},
        'tool_execution_events': trace['tool_execution_events'], 'state_write_receipts': trace['state_write_receipts']}
    names = [operation(item.action)[0] for item in world_transitions(source) if item.action is not None]
    assert 'zoho_desk_create_ticket' in names
    assert not {'google_sheets_add_row', 'google_sheets_append_row'} & set(names)
    outcome = core(source, draft)
    assert outcome.compliance is None and outcome.findings
    assert all(item.value is None for item in outcome.findings) and not select_harm(outcome)
    assert path.read_bytes() == raw


def test_native_exact_ticket_harm_consumption_and_reload(public, draft, monkeypatch):
    import verifiers.v1 as vf
    from test_manifest_guard_assessments import native_fixture, penalties

    from automationbench_v1 import manifest_assessments
    from automationbench_v1.manifest_assessments import ManifestAssessmentTask
    from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig

    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: draft)
    _, episode, trace = native_fixture(material(public, [append(public)]))
    data = AutomationBenchData(domain='marketing', task_name=NAME, prompt=public['prompt'],
        initial_state=public['initial_state'], assertions=(), zapier_tools=tuple(public['zapier_tools']))
    trace.task = vf.TraceTask(type='Task', data=data)
    cast(Any, episode).task = trace.task
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors and trace.rewards == scalar
    assert len(penalties(trace)) == 1 and penalties(trace)[0].value == -1
    assert penalties(trace)[0].recipient.execution.invocation_id == 'execution-0'
    assignments = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == assignments
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors
    assert tuple(replay.credit_assignments) == assignments and replay.rewards == scalar
