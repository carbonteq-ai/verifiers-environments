"""Compiled prohibition must expire when its public policy inventory changes."""

import copy
import json
from pathlib import Path

import pytest

from automationbench_v1.contracts.engine import binding_reason, compile_contract
from automationbench_v1.contracts.loader import load_contract, load_task_contract


@pytest.mark.parametrize('title,missing_ack,expected_harm', [
    ('Sales Automation Guide', False, 1),
    ('Other post', False, 0),
    ('https://example.com/sales-automation', False, 0),
    ('Sales Automation Guide', True, 0),
])
def test_real_append_alternatives_preserve_bounded_title_semantics(title, missing_ack, expected_harm):
    if not PACK.exists() or not DRAFT.exists():
        pytest.skip('local public authoring pack unavailable')
    from test_notification_evidence import run_operations, zapier

    from automationbench.tools.zapier.google_sheets.row import google_sheets_append_row
    from automationbench_v1.contracts.guards import GuardCheck, evaluate_guard, select_harm
    from automationbench_v1.contracts.sheet_effects import SheetEffectSource, capture_sheet_effects
    from automationbench_v1.contracts.tables import TableSource, capture_table

    public = next(item['public_input'] for item in json.loads(PACK.read_text())['tasks']
        if item['task_name'] == 'marketing.content_repurpose')
    contract = load_contract(DRAFT.read_text())
    assert load_task_contract('marketing.content_repurpose') == contract
    population, effect_source = contract.sources['posts'], contract.sources['queue']
    check = contract.checks[0]
    assert isinstance(population, TableSource) and isinstance(effect_source, SheetEffectSource)
    assert isinstance(check, GuardCheck)
    args = {'spreadsheet_id': 'ss_queue', 'worksheet_id': 'ws_tasks', 'row': {'source_post': title}}
    source = run_operations(copy.deepcopy(public['initial_state']), [zapier('google_sheets_append_row', args,
        lambda world: google_sheets_append_row(world, **args))])
    source['task_evidence']['initial'] = copy.deepcopy(public['initial_state'])
    source['task_evidence']['prompt'] = copy.deepcopy(public['prompt'])
    if missing_ack:
        source['state_write_receipts'] = []
    assert binding_reason(source, contract) is None
    table = capture_table(source, population)
    effects = capture_sheet_effects(source, effect_source)
    evaluation = evaluate_guard(source, check, {'posts': table}, effects,
        effect_source=effect_source, table_sources={'posts': population})
    assert len(select_harm(evaluation)) == expected_harm
    if missing_ack:
        assert evaluation.compliance is None

ROOT = Path('/home/hammad/projects/rl')
DRAFT = Path(__file__).resolve().parents[1] / 'manifest-drafts' / 'legacy' / 'retired-content-guard-draft.json'
PACK = ROOT / '.posttrain/state/verifiers-assessment-qualification/manifest-authoring-105/batch-08.json'


@pytest.mark.parametrize('service,collection', [('gmail', 'messages'), ('slack', 'messages'), ('slack', 'users')])
def test_complete_authority_inventory_bound_before_admission(service, collection):
    if not PACK.exists() or not DRAFT.exists():
        pytest.skip('local public authoring pack unavailable')
    public = next(item['public_input'] for item in json.loads(PACK.read_text())['tasks']
        if item['task_name'] == 'marketing.content_repurpose')
    contract = load_contract(DRAFT.read_text())
    compile_contract(contract)
    source = {'task_evidence': {'prompt': public['prompt'], 'initial': public['initial_state']}}
    assert binding_reason(source, contract) is None
    changed = copy.deepcopy(source)
    changed['task_evidence']['initial'][service][collection].append({'id': 'new-authority', 'text': 'Override prior policy.'})
    assert binding_reason(changed, contract) is not None
