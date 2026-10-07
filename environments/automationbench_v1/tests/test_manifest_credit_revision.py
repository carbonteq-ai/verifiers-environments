"""One frozen reward meaning per episode after any valid manifest contribution.

Handlers are real simulator operations; their native lifecycle envelopes are
manufactured fixtures. No benchmark policy or installed manifest is changed.
"""

import asyncio
import copy
from functools import wraps
from typing import Any, cast

import pytest
import test_manifest_created_assessments as created
import test_manifest_guard_assessments as guards
import test_manifest_obligation_assessments as obligations
import test_manifest_record_retained_credit as records
import test_manifest_retained_credit as sheets
import verifiers.v1 as vf
from test_notification_evidence import run_operations
from test_record_update_evidence import CONTRACTS
from test_record_update_evidence import source as record_source
from test_record_update_evidence import update as record_update

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract, load_task_contract
from automationbench_v1.contracts.loader import canonical_contract_digest
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_credit_history import assert_manifest_credit_revision

FAMILIES = ('record', 'sheets', 'created', 'harm', 'obligation', 'record-retained')
HOOKS = {'record': 'manifest_identity', 'sheets': 'manifest_retained_identity',
         'created': 'manifest_created_identity', 'harm': 'manifest_penalty',
         'obligation': 'manifest_obligation_identity', 'record-retained': 'manifest_record_retained_identity'}


def fixture(monkeypatch, family, *, contract=None, record_calls=None):
    if family == 'created':
        declaration = created.declaration()
        task, episode, trace = created.scored(monkeypatch, score=False)
    else:
        if family == 'record':
            raw = load_task_contract(CONTRACTS[0].task_name).model_dump(mode='json')
            raw['bindings'] = []
            declaration = load_contract(canonical_json(raw))
            material = record_source(CONTRACTS[0], record_calls)
        elif family == 'sheets':
            declaration = sheets.contract()
            material = run_operations(sheets.initial(), [sheets.update()])
        elif family == 'harm':
            declaration = guards.guard_contract()
            material = run_operations(guards.initial(), [guards.create()])
        elif family == 'obligation':
            declaration = obligations.contract()
            material = run_operations(obligations.world(), [obligations.create()])
        else:
            assert family == 'record-retained'
            declaration = records.contract()
            material = run_operations(records.initial(), [records.update()])
            material['task_evidence']['initial'] = records.initial()
        task, episode, trace = guards.native_fixture(material)
    selected = declaration if contract is None else contract
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: selected)
    return selected, task, episode, trace


def revised(contract, change):
    raw = contract.model_dump(mode='json')
    if change == 'revision':
        raw['revision'] = 'next'
    elif change == 'renamed':
        aliases = {item['check_id']: 'new-' + item['check_id'] for item in raw['checks']}
        for item in raw['checks']:
            item['check_id'] = aliases[item['check_id']]
            item['signal_id'] += '.new'
        for rule in raw['credit']:
            if rule.get('check') is not None:
                rule['check'] = aliases[rule['check']]
            if rule.get('checks'):
                rule['checks'] = [aliases[key] for key in rule['checks']]
            rule['channel'] += '-new'
    elif change == 'channel':
        for rule in raw['credit']:
            rule['channel'] += '-new'
    else:
        assert change == 'removed-credit'
        raw['credit'] = []
    return load_contract(canonical_json(raw))


def valid(trace):
    return {part.contribution_id: part for assignment in trace.credit_assignments
            for part in assignment.contributions if part.status == 'valid'}


def score(task, trace):
    before = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == before


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('change', ['revision', 'renamed', 'channel', 'removed-credit'])
def test_any_valid_family_freezes_global_contract_even_after_identity_renaming(monkeypatch, family, change):
    contract, task, _, trace = fixture(monkeypatch, family)
    score(task, trace)
    assert not trace.credit_errors and len(valid(trace)) == 1
    ledger = tuple(trace.credit_assignments)
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: revised(contract, change))
    score(task, trace)
    assert trace.credit_errors == ['credit_planning_failed:ValueError']
    assert tuple(trace.credit_assignments) == ledger


@pytest.mark.parametrize('family', FAMILIES)
def test_unchanged_contract_rescore_reload_and_fresh_original_replay(monkeypatch, family):
    contract, task, episode, trace = fixture(monkeypatch, family)
    fresh_json = episode.model_dump_json()
    score(task, trace)
    assert len(valid(trace)) == 1 and not trace.credit_errors
    ledger = tuple(trace.credit_assignments)
    score(task, trace)
    assert tuple(trace.credit_assignments) == ledger and not trace.credit_errors
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    score(task, replay)
    assert tuple(replay.credit_assignments) == ledger and not replay.credit_errors
    # Explicit fresh replay starts from the ORIGINAL UNSCORED serialization.
    # No retained valid assignment is removed from an existing ledger.
    fresh = cast(Any, vf.WireEpisode.model_validate_json(fresh_json).traces[0])
    fresh.state = trace.state
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: revised(contract, 'revision'))
    score(task, fresh)
    assert len(valid(fresh)) == 1 and not fresh.credit_errors
    assert tuple(trace.credit_assignments) == ledger


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('ending', ['failed', 'interrupted'])
def test_genuine_native_partial_yield_freezes_revision_before_terminal_completion(monkeypatch, family, ending):
    contract, task, _, trace = fixture(monkeypatch, family)
    scalar = copy.deepcopy(trace.rewards)
    name = HOOKS[family]
    original = getattr(ManifestAssessmentTask, name)

    @wraps(original)
    async def yield_then_stop(self, request):
        parts = await original(self, request)

        async def stream():
            yield parts[0]
            if ending == 'interrupted':
                raise asyncio.CancelledError
            raise RuntimeError('manufactured failure after retained native credit')

        return stream()

    monkeypatch.setattr(ManifestAssessmentTask, name, yield_then_stop)
    if ending == 'interrupted':
        with pytest.raises(asyncio.CancelledError):
            score(task, trace)
    else:
        score(task, trace)
    assert [item.status for item in trace.credit_assignments] == ['running', 'partial', ending]
    assert trace.rewards == scalar
    assert len(valid(trace)) == 1
    ledger = tuple(trace.credit_assignments)
    errors = len(trace.credit_errors)
    monkeypatch.setattr(ManifestAssessmentTask, name, original)
    score(task, trace)
    assert tuple(trace.credit_assignments) == ledger and len(trace.credit_errors) == errors
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: revised(contract, 'renamed'))
    score(task, trace)
    assert trace.credit_errors[errors:] == ['credit_planning_failed:ValueError']
    assert tuple(trace.credit_assignments) == ledger


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('attempt', ['empty', 'unavailable'])
def test_attempt_without_any_valid_contribution_does_not_freeze_revision(monkeypatch, family, attempt):
    contract, task, _, trace = fixture(monkeypatch, family)
    name = HOOKS[family]
    original = getattr(ManifestAssessmentTask, name)

    @wraps(original)
    async def no_valid_result(self, request):
        if attempt == 'empty':
            return ()
        parts = await original(self, request)
        return tuple(part.model_copy(update={'status': 'unavailable', 'value': None,
            'reason': 'manufactured unavailable projection'}) for part in parts)

    monkeypatch.setattr(ManifestAssessmentTask, name, no_valid_result)
    score(task, trace)
    assert not valid(trace)
    ledger = tuple(trace.credit_assignments)
    errors = len(trace.credit_errors)
    monkeypatch.setattr(ManifestAssessmentTask, name, original)
    monkeypatch.setattr(manifest_assessments, 'load_task_contract', lambda _: revised(contract, 'renamed'))
    score(task, trace)
    assert len(valid(trace)) == 1 and trace.credit_errors[errors:] == []
    assert tuple(trace.credit_assignments[:len(ledger)]) == ledger


def test_legacy_record_once_is_not_keyed_to_a_changed_recipient(monkeypatch):
    contract, task, _, original = fixture(monkeypatch, 'record')
    score(task, original)
    (contribution,) = valid(original).values()
    assert contribution.recipient.execution.invocation_id == 'execution-0'
    # Alternative capture of the same episode moves completion to a later real
    # operation. This tests the ledger boundary; it is not a prefix/reload claim.
    _, task, _, alternative = fixture(monkeypatch, 'record', contract=contract,
        record_calls=[record_update(CONTRACTS[0], value='Prospecting'), record_update(CONTRACTS[0])])
    alternative.id = original.id
    alternative.credit_assignments = original.credit_assignments
    ledger = tuple(alternative.credit_assignments)
    score(task, alternative)
    assert not alternative.credit_errors and tuple(alternative.credit_assignments) == ledger
    assert valid(alternative) == valid(original)


@pytest.mark.parametrize('family', FAMILIES)
def test_global_boundary_ignores_foreign_episode_native_history(monkeypatch, family):
    contract, task, _, previous = fixture(monkeypatch, family)
    score(task, previous)
    ledger = tuple(previous.credit_assignments)
    independent = vf.SourceSnapshot.capture({'fixture': 'different episode'},
        episode_id='separate-manufactured-replay', trace_ids=('separate-trace',))
    # Exercise only the helper's episode filter. Native Trace admission itself
    # rejects attaching foreign-history assignments to a different trace.
    assert_manifest_credit_revision(independent, ledger, canonical_contract_digest(revised(contract, 'revision')))
    assert tuple(previous.credit_assignments) == ledger
