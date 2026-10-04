"""Excluded-account append guard; no health-score or whole-task qualification.

Core cases use genuine handlers with reduced captures. Native alternatives use
manufactured validated envelopes; the SHA-bound replay is an actual Luna trace.
"""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.google_sheets.row import google_sheets_append_row
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

ROOT = Path('/home/hammad/projects/rl')
PACK = ROOT / '.posttrain/state/verifiers-assessment-qualification/manifest-authoring-105/batch-07.json'
DRAFT = Path(__file__).resolve().parents[1] / 'manifest-drafts' / 'legacy' / 'zoho-excluded-dashboard-guard-draft.json'
NAME = 'support.zoho_account_health'
SIGNAL = 'support.health_excluded_dashboard_account'
PACK_SHA = '6913ff37ab6ef7a4fd6297312a746a305330a350ada61bfc46c4e19efd2385a1'
EPISODE_SHA = '705789a97d7c86b384f2b1db0c77d419b11cd9d0d8a614d85353e1c3923b4153'


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
        pytest.skip('local uninstalled Zoho guard draft unavailable')
    contract = load_contract(DRAFT.read_bytes())
    assert load_task_contract(NAME) == contract
    return contract


def append(account='za_904', *, tab='ws_dashboard', cells=None):
    args = {'spreadsheet_id': 'ss_health', 'worksheet_id': tab,
        'row': {'Account ID': account, 'Account Name': 'DeltaNew', 'Health Score': 80, 'Status': 'Healthy'}
        if cells is None else cells}
    return zapier('google_sheets_append_row', args, lambda world: google_sheets_append_row(world, **args))


def material(public, calls, *, initial=None):
    initial = copy.deepcopy(public['initial_state'] if initial is None else initial)
    source = run_operations(initial, calls)
    source['task_evidence']['initial'] = initial
    source['task_evidence']['prompt'] = copy.deepcopy(public['prompt'])
    return source


def core(source, draft):
    assert binding_reason(source, draft) is None
    check = draft.checks[0]
    assert isinstance(check, GuardCheck)
    population_source, effect_source = draft.sources[check.population], draft.sources[check.source]
    assert isinstance(population_source, TableSource) and isinstance(effect_source, SheetEffectSource)
    table = capture_table(source, population_source)
    effects = capture_sheet_effects(source, effect_source)
    return evaluate_guard(source, check, {check.population: table}, effects,
        effect_source=effect_source, table_sources={check.population: population_source})


def test_core_public_scope_bindings_and_roundtrip(public, draft):
    source = material(public, [append()])
    assert compile_contract(draft) == ('excluded-dashboard-account',)
    assert load_contract(draft.model_dump_json()) == draft
    assert binding_reason(source, draft) is None
    for binding in draft.bindings:
        changed = copy.deepcopy(source)
        target = cast(Any, changed)
        for part in binding.path[:-1]:
            target = target[part]
        target[binding.path[-1]] = []
        assert binding_reason(changed, draft) == 'manifest_source_binding_mismatch'


@pytest.mark.parametrize('account,cells,expected', [
    ('za_904', None, 1),
    ('different-account', None, 0),
    ('za_904', {'Account ID': 'za_904', 'Health Score': -999}, 1),
    ('za_904', {'Account Name': 'DeltaNew'}, None),
    ('za_904', {'Account ID': True}, None),
])
def test_core_exact_business_identity_without_score_or_name_policy(public, draft, account, cells, expected):
    outcome = core(material(public, [append(account, cells=cells)]), draft)
    assert len(outcome.findings) == 1 and outcome.findings[0].value == expected
    assert len(select_harm(outcome)) == (1 if expected == 1 else 0)


def test_core_wrong_worksheet_does_not_become_dashboard_harm(public, draft):
    outcome = core(material(public, [append(tab='ws_config')]), draft)
    assert not select_harm(outcome) and not outcome.findings


@pytest.mark.parametrize('defect', ['duplicate', 'missing-key', 'unknown-other-key'])
def test_core_ambiguous_or_unknown_exclusion_identity_abstains(public, draft, defect):
    initial = copy.deepcopy(public['initial_state'])
    rows = initial['google_sheets']['rows']
    row = next(row for row in rows if row['worksheet_id'] == 'ws_new_accounts')
    if defect == 'missing-key':
        del row['cells']['Account ID']
    else:
        extra = copy.deepcopy(row)
        extra['row_id'] = 3
        if defect == 'unknown-other-key':
            del extra['cells']['Account ID']
        rows.append(extra)
    outcome = core(material(public, [append()], initial=initial), draft)
    assert not select_harm(outcome)
    assert any(item.value is None for item in outcome.findings) and outcome.compliance is None


def delete_dashboard(world):
    world.google_sheets.rows = [row for row in world.google_sheets.rows if row.worksheet_id != 'ws_dashboard']
    return {'success': True}


def test_core_later_deletion_does_not_erase_qualified_historical_harm(public, draft):
    outcome = core(material(public, [append(), ('manufactured_delete', {}, delete_dashboard)]), draft)
    selected = select_harm(outcome)
    assert len(selected) == 1 and selected[0].occurrence == 'execution-0'
    assert outcome.compliance == 0 and any(item.value is None for item in outcome.findings)


def test_core_each_distinct_harm_has_one_stable_selection(public, draft):
    source = material(public, [append(), append()])
    first = select_harm(core(source, draft))
    second = select_harm(core(json.loads(canonical_json(source)), draft))
    assert first == second and len(first) == 2
    assert {item.occurrence for item in first} == {'execution-0', 'execution-1'}


def test_core_missing_ack_does_not_authorize_harm_credit(public, draft):
    source = material(public, [append()])
    source['state_write_receipts'] = []
    outcome = core(source, draft)
    assert not select_harm(outcome) and outcome.compliance is None


def test_core_exclusion_population_remains_dynamic(public, draft):
    initial = copy.deepcopy(public['initial_state'])
    row = next(row for row in initial['google_sheets']['rows'] if row['worksheet_id'] == 'ws_new_accounts')
    row['cells']['Account ID'] = 'new-exclusion'
    source = material(public, [append('za_904'), append('new-exclusion')], initial=initial)
    selected = select_harm(core(source, draft))
    assert len(selected) == 1 and selected[0].occurrence == 'execution-1'


def native_run(public, draft, monkeypatch, calls):
    import verifiers.v1 as vf
    from test_manifest_guard_assessments import native_fixture

    from automationbench_v1 import manifest_assessments
    from automationbench_v1.manifest_assessments import ManifestAssessmentTask
    from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig

    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: draft)
    source = material(public, calls)
    _, episode, trace = native_fixture(source)
    data = AutomationBenchData(domain='support', task_name=NAME, prompt=public['prompt'],
        initial_state=public['initial_state'], assertions=(), zapier_tools=tuple(public['zapier_tools']))
    trace.task = vf.TraceTask(type='Task', data=data)
    cast(Any, episode).task = trace.task
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors and trace.rewards == scalar
    return task, episode, trace


def test_native_harm_then_delete_consumes_once_across_rescore_and_reload(public, draft, monkeypatch):
    import verifiers.v1 as vf
    from test_manifest_guard_assessments import penalties

    task, episode, trace = native_run(public, draft, monkeypatch,
        [append(), ('manufactured_delete', {}, delete_dashboard)])
    assert len(penalties(trace)) == 1 and penalties(trace)[0].value == -1
    assert penalties(trace)[0].recipient.execution.invocation_id == 'execution-0'
    original = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == original
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors
    assert tuple(replay.credit_assignments) == original


def test_native_actual_hash_bound_neutral_replay_semantics_and_scalar(public, draft, monkeypatch):
    import verifiers.v1 as vf
    from test_batch01_manifests import recorded
    from test_manifest_guard_assessments import penalties, terminal_records
    from test_nda_status_manifest import terminal_semantics

    from automationbench_v1 import manifest_assessments
    from automationbench_v1.manifest_assessments import ManifestAssessmentTask
    from automationbench_v1.taskset import AutomationBenchTaskConfig
    from automationbench_v1.tools import AutomationBenchState

    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: draft)
    path, raw, episode, trace, data = recorded(NAME)
    assert hashlib.sha256(raw).hexdigest() == EPISODE_SHA
    trace.state = AutomationBenchState(world=trace.info['automationbench']['end_state'],
        initial_state=data.initial_state, assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    findings = [item for item in terminal_records(trace) if item.signal.signal_id == SIGNAL]
    # Zoho Desk/Salesforce/search calls cannot touch Sheets, so every excluded
    # account is now a known non-violation instead of partly unknown.
    assert findings and all(item.value == 0 for item in findings)
    assert not any(item.value == 1 for item in findings) and not penalties(trace)
    assert trace.rewards == scalar
    expected = terminal_semantics(trace.assessment_batches)
    original = tuple(trace.assessment_batches)
    assignments = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert terminal_semantics(trace.assessment_batches[len(original):]) == expected
    assert tuple(trace.credit_assignments) == assignments
    before_reload = tuple(trace.assessment_batches)
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    assert tuple(replay.assessment_batches) == before_reload
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors
    assert terminal_semantics(replay.assessment_batches[len(before_reload):]) == expected
    assert tuple(replay.credit_assignments) == assignments
    assert replay.rewards == scalar and path.read_bytes() == raw
