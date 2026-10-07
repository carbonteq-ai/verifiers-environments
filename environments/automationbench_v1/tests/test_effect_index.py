"""Captured-chain qualification is independent of task success and guard coverage."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from test_hr_assessments import _source

from automationbench_v1.effect_evidence import world_transitions
from automationbench_v1.effect_index import EffectIndex


def _transition(before, after, *, invocation="first", revision=0):
    original = world_transitions(_source(before, after))[0]
    return replace(
        original,
        invocation_id=invocation,
        expected_revision=revision,
        applied_revision=revision + 1,
    )


def test_out_of_order_reads_keep_execution_order_but_reconstruct_serial_order():
    initial = {"gmail": {"messages": []}}
    sent = {"gmail": {"messages": [{"id": "mail"}]}}
    read = _transition(initial, initial, invocation="read")
    send = _transition(initial, sent, invocation="send", revision=1)
    index = EffectIndex((send, read))
    assert [item.invocation_id for item in index.occurrences] == ["send", "read"]
    chain = index.serial_chain()
    assert chain.status == "qualified" and chain.revision_interval == (0, 2)
    assert [item.invocation_id for item in chain.ordered] == ["read", "send"]
    history = index.service_history(("gmail",))
    assert [item.status for item in history.observations] == ["changed", "unchanged"]
    assert history.captured_scope_qualified


@pytest.mark.parametrize(
    "modification,reason",
    [
        ("branch", "revision_branch"),
        ("gap", "revision_gap"),
        ("world", "world_link_conflict"),
        ("conflict", "unqualified_occurrence"),
        ("revision", "revision_transition_unqualified"),
    ],
)
def test_branches_gaps_conflicts_never_invent_a_serial_chain(modification, reason):
    first = _transition({"gmail": {}}, {"gmail": {"x": 1}})
    second = _transition({"gmail": {"x": 1}}, {"gmail": {"x": 2}}, invocation="second", revision=1)
    if modification == "branch":
        second = replace(second, expected_revision=0, applied_revision=1)
    elif modification == "gap":
        second = replace(second, expected_revision=2, applied_revision=3)
    elif modification == "world":
        second = _transition({"gmail": {}}, {"gmail": {"x": 2}}, invocation="second", revision=1)
    elif modification == "conflict":
        second = replace(second, evidence_status="unavailable", reason="state_write_conflict")
    else:
        second = replace(second, applied_revision=9)
    index = EffectIndex((first, second))
    assert index.serial_chain().reason == reason
    assert index.serial_chain().ordered == ()
    assert len(index.occurrences) == 2
    assert not index.service_history(("gmail",)).captured_scope_qualified


def test_correction_retains_harmful_intermediate_world_and_occurrences():
    initial = {"gmail": {"messages": [{"id": "mail", "draft": True}]}}
    harmful = {"gmail": {"messages": [{"id": "mail", "draft": False}]}}
    send = _transition(initial, harmful, invocation="send")
    correct = _transition(harmful, initial, invocation="correct", revision=1)
    index = EffectIndex((correct, send))
    chain = index.serial_chain()
    assert chain.status == "qualified" and index.snapshot_count == 2
    sent_world = chain.ordered[0].after_json
    assert sent_world is not None
    assert index.collection(sent_world, "gmail", "messages")[0]["draft"] is False
    assert [item.invocation_id for item in chain.ordered] == ["send", "correct"]


def test_snapshots_are_decoded_once_and_recursively_immutable():
    state = {"gmail": {"messages": [{"id": "mail", "labels": ["one"]}]}}
    first = _transition(state, state)
    second = replace(first, invocation_id="second", expected_revision=1, applied_revision=2)
    assert first.before_json is not None and second.after_json is not None
    original_loads = json.loads
    with patch("automationbench_v1.effect_index.json.loads", wraps=original_loads) as loads:
        index = EffectIndex((first, second))
        assert loads.call_count == 1
        assert index.world(first.before_json) is index.world(second.after_json)
        record = index.collection(first.before_json, "gmail", "messages")[0]
        with pytest.raises(TypeError):
            record["id"] = "other"  # pyright: ignore[reportIndexIssue]
        assert record["labels"] == ("one",)
        with pytest.raises(TypeError):
            index.world(first.before_json)["gmail"]["messages"][0]["labels"][0] = "other"
        assert loads.call_count == 1
    assert len(index.occurrences) == 2 and index.snapshot_count == 1


def test_unknown_capture_cannot_be_excluded_from_a_service_scope():
    known = _transition({"gmail": {}, "slack": {}}, {"gmail": {}, "slack": {"x": 1}})
    unknown = replace(
        known,
        invocation_id="unknown",
        action=None,
        before_json=None,
        after_json=None,
        evidence_status="unavailable",
        reason="world_capture_missing",
    )
    index = EffectIndex((known, unknown))
    history = index.service_history(("gmail",))
    assert [item.status for item in history.observations] == ["unchanged", "unavailable"]
    assert not history.captured_scope_qualified
    absent = EffectIndex((known,)).service_history(("salesforce",))
    assert absent.observations[0].status == "unavailable"
    assert absent.observations[0].reason == "scoped_service_schema_unavailable"


def test_json_type_changes_remain_observed_and_missing_collections_are_unavailable():
    transition = _transition({"gmail": {"flag": True}}, {"gmail": {"flag": 1}})
    assert transition.before_json is not None
    index = EffectIndex((transition,))
    assert index.service_history(("gmail",)).observations[0].status == "changed"
    with pytest.raises(ValueError, match="record_collection_unavailable"):
        index.collection(transition.before_json, "gmail", "messages")
    with pytest.raises(ValueError, match="snapshot_not_in_evidence_index"):
        index.world("{}")


def test_empty_inventory_and_duplicate_identity_are_explicit():
    assert EffectIndex(()).serial_chain().reason == "empty_occurrence_inventory"
    transition = _transition({}, {})
    with pytest.raises(ValueError, match="duplicate_execution_identity"):
        EffectIndex((transition, transition))
    with pytest.raises(ValueError, match="service_scope_must_be_explicit"):
        EffectIndex((transition,)).service_history(())


def test_retained_development_trace_reconstructs_chain_without_dropping_reads():
    path = Path(
        "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/"
        "luna-reference-campaign-01/hr-firstpass/"
        "b03c8dc88e1661f65e7150a31c48e55a20e3f372d6ceedd4bb37753bb55ef9cb/episode.json"
    )
    if not path.exists():
        pytest.skip("retained development bank not present")
    original = path.read_bytes()
    transitions = world_transitions(json.loads(original)["traces"][0])
    index = EffectIndex(reversed(transitions))
    chain = index.serial_chain()
    assert chain.status == "qualified" and chain.revision_interval == (0, 16)
    assert chain.ordered == transitions
    assert len(index.occurrences) == 16 and index.snapshot_count == 10
    gmail = index.service_history(("gmail",))
    assert gmail.captured_scope_qualified
    assert sum(item.status == "changed" for item in gmail.observations) == 5
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(original).digest()
