"""Explicit occurrence bounds preserve conservative closure and native replay."""

import asyncio
from dataclasses import replace

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import native_fixture, terminal_records
from test_manifest_guards import create
from test_manifest_obligation_assessments import contract
from test_manifest_obligations import evaluate, inputs, new_occurrence, world
from test_notification_evidence import run_operations, zapier

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.obligations import ObligationCheck


def bounded(minimum=1, maximum=1):
    return new_occurrence() | {"occurrence_bounds": {"minimum": minimum, "maximum": maximum}}


@pytest.mark.parametrize("count,expected", [(0, None), (1, 1), (2, 0)])
def test_distinct_genuine_persisted_creates_obey_exact_one(count, expected):
    material = run_operations(world(), [create() for _ in range(count)])
    finding = evaluate(material, bounded()).findings[0]
    assert finding.value == expected
    assert len(finding.witnesses) == count


def test_closed_range_and_incomplete_scope_have_distinct_results():
    material = run_operations(world(), [create(), create()])
    assert evaluate(material, bounded(2, 3)).findings[0].value == 1
    evidence = replace(inputs(material)[2], complete=False, reason="incomplete_capture")
    assert evaluate(material, bounded(2, 3), evidence=evidence).findings[0].value is None
    # Two observed occurrences already disprove exact-one despite incomplete capture.
    assert evaluate(material, bounded(), evidence=evidence).findings[0].value == 0


def test_closed_empty_inventory_proves_count_below_minimum():
    from automationbench.tools.zapier.asana.actions import asana_add_task_to_section

    args = {"task_id": "existing", "workspace": "workspace", "projects": "project-access", "section": "section"}
    material = run_operations(world(), [zapier("asana_add_task_to_section", args,
        lambda state: asana_add_task_to_section(state, **args))])
    result = evaluate(material, bounded())
    assert result.scope_complete
    assert result.findings[0].value == 0
    assert result.findings[0].reason == "obligation_occurrence_count_below_minimum"


def test_repeated_inventory_entry_is_not_another_occurrence():
    material = run_operations(world(), [create()])
    evidence = inputs(material)[2]
    evidence = replace(evidence, effects=evidence.effects + evidence.effects)
    finding = evaluate(material, bounded(), evidence=evidence).findings[0]
    assert finding.value == 1 and len(finding.witnesses) == 1


@pytest.mark.parametrize("bounds", [
    {"minimum": True, "maximum": 1}, {"minimum": 0, "maximum": 1},
    {"minimum": 2, "maximum": 1}, {"minimum": 1, "maximum": 65537},
])
def test_invalid_bounds_rejected(bounds):
    with pytest.raises(ValueError):
        ObligationCheck.model_validate(new_occurrence() | {"occurrence_bounds": bounds})


def test_legacy_digest_and_baseline_rejection():
    assert "occurrence_bounds" not in ObligationCheck.model_validate(new_occurrence()).model_dump(mode="json")
    with pytest.raises(ValueError, match="single_source_new_occurrence"):
        ObligationCheck.model_validate(bounded() | {"semantics": "occurrence"})


def native_contract():
    raw = contract(baseline=False, semantics="new_occurrence").model_dump(mode="json")
    raw["checks"][0]["occurrence_bounds"] = {"minimum": 1, "maximum": 1}
    with pytest.raises(ValueError, match="outcome_only"):
        load_contract(canonical_json(raw))
    raw["credit"] = []
    return load_contract(canonical_json(raw))


@pytest.mark.parametrize("count,missing_ack,expected", [(1, None, 1), (2, None, 0), (1, 0, None)])
def test_native_missing_ack_and_scored_reload(monkeypatch, count, missing_ack, expected):
    declared = native_contract()
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, episode, trace = native_fixture(run_operations(world(), [create() for _ in range(count)]),
        missing_ack=missing_ack)
    rewards = trace.rewards.copy()
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors and trace.rewards == rewards
    records = terminal_records(trace)
    goals = [r for r in records if r.signal.signal_id == "access.required_effect"]
    assert goals and all(r.value == expected for r in goals)
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    reloaded = loaded.traces[0]
    reloaded.state = trace.state
    asyncio.run(task.score(reloaded))
    logical = lambda rows: {(r.signal.signal_id, r.status, r.value, r.reason) for r in rows}
    assert logical(terminal_records(reloaded)) == logical(records)
    assert not trace.credit_assignments and not reloaded.credit_assignments
    assert not reloaded.assessment_errors and not reloaded.credit_errors
