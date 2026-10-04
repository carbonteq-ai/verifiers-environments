"""Bounded native support publishing requires explicit composition review.

Fixture contracts exercise candidate predicates and transport. They are not a
release decision for whole Gorgias/Hiver task rewards or curriculum eligibility.
"""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
import verifiers.v1 as vf
from test_support_evidence import Fresh, _contract, _log, _obligation, _send
from verifiers.v1.assessment_source import capture_trace_source

from automationbench.domains.support.tasks import get_support_hiver_slack_digest_task
from automationbench_v1.support_assessments import (
    GORG,
    HIVER,
    ReviewedSupportTask,
    SupportTaskConfig,
    capture_support_contract,
)
from automationbench_v1.taskset import AutomationBenchData
from automationbench_v1.tools import AutomationBenchState


def _selected(data, *, disposition="reviewed_bounded"):
    kwargs = (
        {"review_obligations": (_obligation(data.initial_state),)}
        if data.task_name == GORG
        else {"digest_claims": _contract()}
    )
    return capture_support_contract(
        data,
        review_revision="qualification-bounded-test-forms-v1",
        disposition=disposition,
        **kwargs,
    )


def _task(data, *, disposition="reviewed_bounded"):
    contract = _selected(data, disposition=disposition)
    return ReviewedSupportTask(
        data, SupportTaskConfig(capture_actions=True, support_contract=contract)
    )


def _actual(task_name):
    registry = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-policy-contracts.json"
    )
    if not registry.exists():
        pytest.skip("retained development registry unavailable")
    item = next(
        case
        for case in json.loads(registry.read_bytes())["tasks"]
        if case["task_name"] == task_name
    )
    binding = item["source_binding"]
    path = Path(binding["source_episode_path"])
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == binding["source_episode_sha256"]
    episode = vf.WireEpisode.model_validate_json(raw)
    data = AutomationBenchData.model_validate(episode.task.data.model_dump(mode="json"))
    trace = cast(vf.Trace, episode.traces[0])
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state,
        assertions=data.assertions,
    )
    return path, raw, episode, data, trace


@pytest.mark.parametrize("name,credits", [(GORG, 1), (HIVER, 2)])
def test_actual_support_score_native_reload_credit_and_official_parity(name, credits):
    path, raw, episode, data, trace = _actual(name)
    task = _task(data)
    assert task.support_contract is not None
    original_rewards = dict(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    assert trace.rewards == original_rewards
    batch = trace.assessment_batches[-1]
    assert isinstance(batch.source, vf.SourceSnapshot)
    assert batch.run.producer_id == task.producer_id
    assert batch.run.rubric_revision.endswith(task.support_contract.digest)
    diagnostics = [record for record in batch.assessments if record.signal.direction == "neutral"]
    assert len(diagnostics) == 2 and all(record.subject.kind == "trace" for record in diagnostics)
    results = [
        record
        for record in batch.assessments
        if record.signal.direction != "neutral" and record.value == 1
    ]
    assert len(results) == credits
    assert all(
        record.subject.kind == ("trace" if name == GORG else "execution") for record in results
    )
    assignments = [item for item in trace.credit_assignments if item.status == "complete"]
    assert len(assignments) == credits
    assert all(item.contributions[0].recipient.kind == "execution" for item in assignments)
    assert all(item.contributions[0].signal.direction != "neutral" for item in assignments)
    assert all(
        item.contributions[0].parent_assessment_ids == (item.request.accepted[0].assessment_id,)
        for item in assignments
    )
    with patch.object(task, "credit_context", wraps=task.credit_context) as rederive:
        requests = task.credit_requests(batch.source, (batch, batch))
        assert len(requests) == credits and rederive.call_count == 1
    assert batch.views[0].input_json is not None
    assert "assertions" not in batch.views[0].input_json
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    assert restored.traces[0].assessment_batches == trace.assessment_batches
    assert restored.traces[0].credit_assignments == trace.credit_assignments
    assert path.read_bytes() == raw


@pytest.mark.parametrize("name", [GORG, HIVER])
def test_proposals_and_missing_contracts_abstain_without_credit_or_faked_success(name):
    _, _, _, data, trace = _actual(name)
    for task in (_task(data, disposition="development_proposal"), ReviewedSupportTask(data)):
        trace.assessment_batches = []
        trace.credit_assignments = []
        asyncio.run(task.score(trace))
        assert not trace.assessment_errors and not trace.credit_errors
        assert trace.credit_assignments == []
        assert len(trace.assessment_batches[-1].assessments) == 1
        record = trace.assessment_batches[-1].assessments[0]
        assert record.status == "abstained" and record.value is None
        assert record.signal.direction == "neutral"
        assert record.reason in {
            "development_contract_requires_review",
            "explicit_support_contract_required",
        }


def test_contract_binding_rejects_mutated_public_data_and_invalid_recipient_authority():
    _, _, _, data, trace = _actual(HIVER)
    task = _task(data)
    source = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    raw = json.loads(source.source_json)
    raw["task_evidence"]["initial"]["meta"]["current_time"] = "2026-02-11T09:00:00Z"
    with pytest.raises(ValueError, match="public_source_contract_mismatch"):
        task.evaluate_findings(raw)
    from dataclasses import replace

    altered = replace(_contract(), recipients=(("infrastructure", "intruder@example.com"),))
    contract = capture_support_contract(
        data, review_revision="fixture", disposition="reviewed_bounded", digest_claims=altered
    )
    wrong = ReviewedSupportTask(data, SupportTaskConfig(support_contract=contract))
    asyncio.run(wrong.score(trace))
    assert trace.assessment_batches[-1].assessments[0].value is None


def test_conflicting_public_recipient_rows_cannot_select_a_favorable_binding():
    _, _, _, data, trace = _actual(HIVER)
    data = data.model_copy(deep=True)
    data.initial_state["google_sheets"]["rows"].append(
        {
            "spreadsheet_id": "ss_digest",
            "worksheet_id": "ws_recipients",
            "row_id": 99,
            "cells": {"Category": "infrastructure", "Recipient_Email": "other@example.com"},
        }
    )
    task = _task(data)
    source = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    with pytest.raises(ValueError, match="recipient_public_binding_unresolved"):
        task.evaluate_findings(json.loads(source.source_json))


def test_credit_rederives_signal_subject_recipient_and_filters_diagnostics():
    _, _, _, data, trace = _actual(GORG)
    task = _task(data)
    asyncio.run(task.score(trace))
    batch = trace.assessment_batches[-1]
    assert isinstance(batch.source, vf.SourceSnapshot)
    goal = next(
        record
        for record in batch.assessments
        if record.value == 1 and record.signal.direction == "higher"
    )
    recipient = task.credit_recipient(batch.source, goal)
    assert recipient is not None
    assert recipient.kind == "execution"
    with pytest.raises(ValueError, match="signal_contract_mismatch"):
        task.credit_recipient(
            batch.source,
            goal.model_copy(update={"signal": goal.signal.model_copy(update={"units": "altered"})}),
        )
    with pytest.raises(ValueError, match="finding_membership_unresolved"):
        task.credit_recipient(batch.source, goal.model_copy(update={"subject": recipient}))
    assert task.credit_recipient(batch.source, goal.model_copy(update={"value": 0})) is None
    assert all(
        task.credit_recipient(batch.source, record) is None
        for record in batch.assessments
        if record.signal.direction == "neutral"
    )
    stale = batch.model_copy(
        update={"run": batch.run.model_copy(update={"rubric_revision": "stale"})}
    )
    assert task.credit_requests(batch.source, (stale,)) == []


def test_executed_fresh_log_before_send_remains_harm_in_publisher_context():
    fresh = Fresh(get_support_hiver_slack_digest_task)
    data = _actual(HIVER)[3]
    task = _task(data)
    assert task.support_contract is not None
    _log(fresh)
    original = fresh.index()
    # Reuse actual receipt envelope shape, replacing it with fresh executed
    # simulator captures and explicit controlled fixture acknowledgements.
    from test_hr_assessments import _source

    def evidence(index):
        assert task.support_contract is not None
        item = index.occurrences[0]
        assert (
            item.before_json is not None and item.after_json is not None and item.action is not None
        )
        result = _source(json.loads(item.before_json), json.loads(item.after_json))
        receipt = json.loads(result["tool_execution_events"][0]["receipt_json"])
        envelope = {
            "kind": "automationbench_raw_action",
            "action": item.action.model_dump(mode="json"),
            "snapshots": {
                item.action.before_digest: item.before_json,
                item.action.after_digest: item.after_json,
            },
        }
        receipt["evidence_json"] = [json.dumps(envelope)]
        result["tool_execution_events"][0]["receipt_json"] = json.dumps(receipt)
        result["task_evidence"] = {
            "task_name": HIVER,
            "prompt": data.model_dump(mode="json")["prompt"],
            "initial": data.initial_state,
            "final": json.loads(item.after_json),
            "complete": True,
            "support_contract": task.support_contract.model_dump(mode="json"),
        }
        return result

    findings = task.evaluate_findings(evidence(original))
    assert next(item for item in findings if item.key.startswith("hiver.")).value == 1
    _send(fresh)
    assert (
        next(
            item
            for item in task.evaluate_findings(evidence(original))
            if item.key.startswith("hiver.")
        ).value
        == 1
    )
