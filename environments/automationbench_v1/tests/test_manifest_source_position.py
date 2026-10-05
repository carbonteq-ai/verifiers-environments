"""Explicit physical collection ordering independent of row IDs or cell order."""

import asyncio
import copy

import pytest
import verifiers.v1 as vf
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture, terminal_records
from test_manifest_selections import NOTIFY, contract, field, initial, outcomes, send
from test_notification_evidence import run_operations

from automationbench_v1 import manifest_assessments
from automationbench_v1.contracts.selections import OrderKey, _select
from automationbench_v1.contracts.tables import TableSource, capture_table
from automationbench_v1.tools import AutomationBenchState

SELECT = {'alias': 'buddy', 'population': 'staff',
          'where': {'op': 'eq', 'left': field('member', 'Department'), 'right': field('request', 'Department')},
          'order_by': [{'source_position': 'source_path_index', 'direction': 'asc'}]}


def test_native_first_eligible_physical_member(monkeypatch):
    # Ana precedes older Ben in the physical source. No alphabetical or date
    # tie-break substitutes for the explicitly requested collection ordering.
    declared = contract([NOTIFY], selections=(SELECT,))
    good = outcomes(monkeypatch, declared, [send('ana@example.com', 'Please welcome Hal')])
    bad = outcomes(monkeypatch, declared, [send('ben@example.com', 'Please welcome Hal')])
    assert good['notify-buddy', 100][:2] == ('valid', 1)
    assert bad['notify-buddy', 100][:2] == ('valid', 0)


def population():
    source = {'task_evidence': {'initial': initial()}}
    spec = TableSource(path=('task_evidence', 'initial', 'google_sheets'), spreadsheet_id='s', worksheet_id='staff', key_fields=('Name',), required_fields=('Department',))
    return capture_table(source, spec)


def selection():
    return contract([NOTIFY], selections=(SELECT,)).checks[0].selections[0]


def test_source_order_not_row_identity_or_iteration_order():
    pop = population()
    reversed_pop = copy.copy(pop)
    object.__setattr__(reversed_pop, 'rows', tuple(reversed(pop.rows)))
    assert _select(selection(), {'request': {'Department': 'Sales'}}, reversed_pop)[1]['Name'] == 'Ana'


def test_cross_collection_or_missing_ordinal_is_unavailable():
    pop = population();rows = list(pop.rows)
    changed = copy.copy(rows[0]);object.__setattr__(changed, 'source_path', ('other', 0));rows[0] = changed
    damaged = copy.copy(pop);object.__setattr__(damaged, 'rows', tuple(rows))
    assert _select(selection(), {'request': {'Department': 'Sales'}}, damaged) is None
    rows = list(pop.rows);changed = copy.copy(rows[0]);object.__setattr__(changed, 'source_path', (*changed.source_path[:-1], 'unknown'));rows[0] = changed
    object.__setattr__(damaged, 'rows', tuple(rows))
    assert _select(selection(), {'request': {'Department': 'Sales'}}, damaged) is None


def test_position_order_is_opt_in_and_exclusive():
    with pytest.raises(ValidationError):OrderKey(source_position='source_path_index', value={'kind': 'input', 'format': 'decimal_string', 'path': ['member', 'Rank']}, direction='asc')
    plain = OrderKey(value={'kind': 'input', 'format': 'decimal_string', 'path': ['member', 'Rank']}, direction='asc')
    assert 'source_position' not in plain.model_dump(mode='json')


def test_native_archive_reload_and_reward_parity(monkeypatch):
    declared = contract([NOTIFY], selections=(SELECT,))
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _:declared)
    task, _, trace = native_fixture(run_operations(initial(), [send('ana@example.com', 'Please welcome Hal')]))
    rewards = copy.deepcopy(trace.rewards);asyncio.run(task.score(trace))
    before = {(r.signal.signal_id, r.status, r.value, r.reason) for r in terminal_records(trace)}
    wire = vf.WireEpisode.model_validate({'task': trace.task.model_dump(mode='json'), 'traces': [trace.model_dump(mode='json')]})
    restored = vf.WireEpisode.model_validate_json(wire.model_dump_json()).traces[0]
    restored.state = AutomationBenchState.model_validate(trace.state.model_dump(mode='json'));asyncio.run(task.score(restored))
    assert {(r.signal.signal_id, r.status, r.value, r.reason) for r in terminal_records(restored)} == before
    assert trace.rewards == restored.rewards == rewards and not restored.assessment_errors and not trace.assessment_errors
