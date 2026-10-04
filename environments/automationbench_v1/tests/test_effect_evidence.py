"""Receipt qualification does not label a domain action as successful."""

import copy
import json
from pathlib import Path

import pytest
import verifiers.v1 as vf
from test_hr_assessments import _source

from automationbench_v1.capture import canonical_json
from automationbench_v1.effect_evidence import world_transitions


def test_existing_object_transition_and_failed_local_action_remain_distinct():
    before = {"gmail": {"messages": [{"id": "mail", "draft": True}]}}
    after = {"gmail": {"messages": [{"id": "mail", "draft": False}]}}
    for status in ("returned", "raised", "rejected"):
        observed = world_transitions(_source(before, after, local_status=status))[0]
        assert observed.evidence_status == "acknowledged"
        assert observed.action.status == status
        assert observed.changed_services == ("gmail",)
    read = world_transitions(_source(before, before))[0]
    assert read.evidence_status == "acknowledged" and read.changed_services == ()


@pytest.mark.parametrize(
    "change,reason",
    [
        ("missing_ack", "state_acknowledgement_missing"),
        ("conflict", "state_write_conflict"),
        ("revision", "state_revision_mismatch"),
        ("capture", "world_capture_missing"),
        ("pending", "pending_execution_at_cutoff"),
    ],
)
def test_missing_or_conflicting_evidence_never_acknowledged(change, reason):
    source = _source({}, {"jira": {"tasks": [{"id": "ticket"}]}})
    if change == "missing_ack":
        source["state_write_receipts"] = []
    if change == "conflict":
        source["state_write_receipts"][0]["conflict"] = True
    if change == "revision":
        source["state_write_receipts"][0]["applied_revision"] = 99
    if change in {"capture", "pending"}:
        receipt = json.loads(source["tool_execution_events"][0]["receipt_json"])
        receipt["evidence_json"] = []
        if change == "pending":
            receipt["phase"] = "dispatch"
        source["tool_execution_events"][0]["receipt_json"] = canonical_json(receipt)
    finding = world_transitions(source)[0]
    assert finding.evidence_status == "unavailable" and finding.reason == reason


def test_equal_payloads_do_not_collapse_distinct_invocations():
    source = _source({}, {"jira": {"tasks": [{"id": "ticket"}]}})
    duplicate = copy.deepcopy(source["tool_execution_events"][0])
    receipt = json.loads(duplicate["receipt_json"])
    receipt["invocation_id"] = "second"
    duplicate["receipt_json"] = canonical_json(receipt)
    source["tool_execution_events"].append(duplicate)
    source["state_write_receipts"].append(
        {**source["state_write_receipts"][0], "write_id": "second"}
    )
    assert [item.invocation_id for item in world_transitions(source)] == ["invocation", "second"]
    source["tool_execution_events"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate_execution_lifecycle"):
        world_transitions(source)


def test_tampered_world_is_rejected_before_domain_evaluation():
    source = _source({}, {"jira": {}})
    receipt = json.loads(source["tool_execution_events"][0]["receipt_json"])
    capture = json.loads(receipt["evidence_json"][0])
    capture["snapshots"][capture["action"]["after_digest"]] = "{}"
    receipt["evidence_json"] = [canonical_json(capture)]
    source["tool_execution_events"][0]["receipt_json"] = canonical_json(receipt)
    with pytest.raises(ValueError, match="snapshot_digest_mismatch"):
        world_transitions(source)


def test_missing_matching_revision_values_cannot_qualify_ack():
    source = _source({}, {})
    receipt = json.loads(source["tool_execution_events"][0]["receipt_json"])
    receipt.pop("state_read_revision")
    source["state_write_receipts"][0].pop("expected_revision")
    source["tool_execution_events"][0]["receipt_json"] = canonical_json(receipt)
    record = world_transitions(source)[0]
    assert record.evidence_status == "unavailable"
    assert record.reason == "state_revision_unavailable"


def test_later_return_cannot_change_earlier_prefix_finding():
    complete = _source({}, {"gmail": {"messages": [{"id": "sent"}]}})
    prefix = copy.deepcopy(complete)
    dispatch = json.loads(prefix["tool_execution_events"][0]["receipt_json"])
    dispatch["phase"] = "dispatch"
    dispatch["evidence_json"] = []
    prefix["tool_execution_events"][0]["receipt_json"] = canonical_json(dispatch)
    prefix["state_write_receipts"] = []
    earlier = world_transitions(prefix)
    assert earlier[0].reason == "pending_execution_at_cutoff"
    assert world_transitions(complete)[0].evidence_status == "acknowledged"
    assert world_transitions(prefix) == earlier


def test_duplicate_acknowledgements_are_ambiguous_not_last_write_wins():
    source = _source({}, {})
    source["state_write_receipts"].append(copy.deepcopy(source["state_write_receipts"][0]))
    with pytest.raises(ValueError, match="duplicate_state_write_identity"):
        world_transitions(source)


def test_retained_development_receipts_all_preserved():
    directory = Path(
        "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01/hr-firstpass/b03c8dc88e1661f65e7150a31c48e55a20e3f372d6ceedd4bb37753bb55ef9cb"
    )
    if not directory.exists():
        pytest.skip("retained development bank not present")
    episode = vf.WireEpisode.model_validate_json((directory / "episode.json").read_text())
    trace = episode.traces[0]
    source = {
        "tool_execution_events": [
            item.model_dump(mode="json") for item in trace.tool_execution_events
        ],
        "state_write_receipts": [
            item.model_dump(mode="json") for item in trace.state_write_receipts
        ],
    }
    transitions = world_transitions(source)
    assert len(transitions) == len(trace.state_write_receipts)
    assert len({(item.origin, item.invocation_id) for item in transitions}) == len(transitions)
    assert any(item.changed_services for item in transitions)
    assert all(item.action is not None for item in transitions)
