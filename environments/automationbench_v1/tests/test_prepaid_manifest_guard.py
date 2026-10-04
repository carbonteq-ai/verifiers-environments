"""Public prepaid policy: actual native replay and labeled simulator alternatives."""

import asyncio
import copy
import json
from importlib.resources import files
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_batch01_manifests import recorded
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.google_sheets.row import (
    google_sheets_add_row,
    google_sheets_update_row,
)
from automationbench_v1 import manifest_assessments
from automationbench_v1.contracts import TableSource, load_contract
from automationbench_v1.contracts.tables import capture_table
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

SIGNAL = 'finance.prepaid_ineligible_balance_recognition'


def contract():
    # Keep these guard-only assertions scoped to the guard component while
    # the selected task manifest also publishes positive schedule credit.
    return load_contract(files('automationbench_v1.contracts').joinpath(
        'tasks/finance-prepaid-ineligible-recognition.json').read_text())


def update(row, cells):
    args = {'spreadsheet': 'ss_prepaids', 'worksheet': 'ws_prepaid_items', 'row': str(row), 'cells': cells}
    return zapier('google_sheets_update_row', args, lambda world: google_sheets_update_row(world, **args))


def run(monkeypatch, operations, *, missing_ack=None):
    _, _, _, _, original = recorded('finance.prepaid_amortization')
    material = run_operations(copy.deepcopy(original.initial_state), operations)
    declared = contract()
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: declared)
    _, episode, trace = native_fixture(material, missing_ack=missing_ack)
    # These are manufactured execution envelopes with actual simulator effects,
    # public task policy and no benchmark outcome assertions.
    data = original.model_copy(update={'assertions': ()})
    trace.task = vf.TraceTask(type='Task', data=data)
    cast(Any, episode).task = trace.task
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    return task, episode, trace


@pytest.mark.parametrize('row,cells,harm', [
    (4, {'Amortized to Date': '$750', 'Remaining': '$17,250'}, 1),
    (5, {'Amortized to Date': '$10,500'}, 1),
    (4, {'Notes': 'Reviewed future coverage'}, 0),
    (4, {'Total': '$20,000'}, 0),
    (4, {'Amortized to Date': '$0'}, 0),
    (4, {'Amortized to Date': '$0.00'}, 0),
    (2, {'Amortized to Date': '$18,000', 'Remaining': '$6,000'}, 0),
    (3, {'Total': '$7,200', 'Amortized to Date': '$1,100', 'Remaining': '$6,100'}, 0),
])
def test_native_financial_mutations_and_allowed_alternatives(monkeypatch, row, cells, harm):
    _, _, trace = run(monkeypatch, [update(row, cells)])
    assert len(penalties(trace)) == harm
    assert all(part.value == -1 and part.recipient.execution.invocation_id == 'execution-0' for part in penalties(trace))
    records = [r for r in terminal_records(trace) if r.signal.signal_id == SIGNAL]
    assert sum(r.value == 1 for r in records) == harm


def test_native_repair_preserves_original_harm_without_charging_restore(monkeypatch):
    task, episode, trace = run(monkeypatch, [update(4, {'Amortized to Date': '$750'}), update(4, {'Amortized to Date': '$0'})])
    assert len(penalties(trace)) == 1
    assert penalties(trace)[0].recipient.execution.invocation_id == 'execution-0'
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors
    assert len(penalties(replay)) == 1


def test_native_missing_ack_is_unavailable_without_negative_credit(monkeypatch):
    _, _, trace = run(monkeypatch, [update(4, {'Amortized to Date': '$750'})], missing_ack=0)
    assert not penalties(trace)
    assert any(r.status == 'abstained' for r in terminal_records(trace) if r.signal.signal_id == SIGNAL)


def test_replacement_at_same_position_does_not_inherit_original_row_policy(monkeypatch):
    def replacement(world):
        world.google_sheets.rows = [row for row in world.google_sheets.rows if row.row_id < 4]
        return google_sheets_add_row(world, spreadsheet='ss_prepaids', worksheet='ws_prepaid_items', cells={
            'Item': 'Replacement eligible item', 'Start Date': '2026-02-01',
            'Remaining': '$1,000', 'Amortized to Date': '$0'})

    _, _, trace = run(monkeypatch, [('replacement-test-fixture', {}, replacement),
                                  update(4, {'Amortized to Date': '$100'})])
    assert not penalties(trace)
    # The custom combined deletion is an explicit observation-scope gap. The
    # observed update is not harm against the deleted original entity, while
    # complete guard compliance cannot be claimed for the unknown operation.
    assert any(r.signal.signal_id == SIGNAL and r.value == 0 for r in terminal_records(trace))
    assert any(r.signal.signal_id == SIGNAL + '.compliance' and r.value is None for r in terminal_records(trace))


def test_moved_original_future_item_retains_observed_harm(monkeypatch):
    def move(world):
        row = next(row for row in world.google_sheets.rows if row.row_id == 4)
        row.row_id = 99
        return {'success': True}

    _, _, trace = run(monkeypatch, [('custom_mutation', {}, move),
        update(99, {'Amortized to Date': '$100', 'Remaining': '$17,900'})])
    # The custom movement leaves action-scope completeness unknown, but the
    # acknowledged financial write on the original object is still observable.
    parts = penalties(trace)
    assert len(parts) == 1 and parts[0].value == -1
    assert parts[0].recipient.execution.invocation_id == 'execution-1'
    assert any(r.signal.signal_id == SIGNAL and r.value == 1 for r in terminal_records(trace))


def test_actual_luna_prepaid_initial_identity_and_native_guard_replay(monkeypatch):
    path, original_bytes, episode, trace, data = recorded('finance.prepaid_amortization')
    declared = contract()
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: declared)
    trace.state = AutomationBenchState(world=trace.info['automationbench']['end_state'], initial_state=data.initial_state,
                                      assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    source = json.loads(trace.assessment_batches[0].source.source_json)
    schedule = declared.sources['schedule']
    assert isinstance(schedule, TableSource)
    table = capture_table(source, schedule)
    assert len(table.rows) == 5 and all(row.native_record_id for row in table.rows)
    assert len({row.native_record_id for row in table.rows}) == 5
    assert all('id' not in row for row in data.initial_state['google_sheets']['rows'])
    assert any(r.signal.signal_id == SIGNAL + '.compliance' and r.value == 1 for r in terminal_records(trace))
    assert not penalties(trace)
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors and not penalties(replay)
    assert path.read_bytes() == original_bytes
