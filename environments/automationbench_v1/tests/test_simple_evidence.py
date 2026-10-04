"""Direct-request rewards use public data and effects, without a model judge."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
import verifiers.v1 as vf
from test_hr_assessments import _source

from automationbench_v1.simple_assessments import ReviewedSimpleTask
from automationbench_v1.simple_evidence import REQUESTS, _declared_fields_match, evaluate_simple
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchData,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState


def _case(before, after, *, acknowledged=True, complete=True):
    source = _source(before, after, acknowledged=acknowledged)
    source["task_evidence"] = {
        "initial": before,
        "final": after,
        "complete": complete,
        "task_name": "simple.sf_case_priority_high",
        "prompt": [
            {"role": "user", "content": "Update Salesforce case 500002 priority to 'High'."}
        ],
    }
    return source


def test_correct_field_target_and_unacknowledged_completion():
    before = {"salesforce": {"cases": [{"id": "500002", "priority": "Low"}]}}
    after = {"salesforce": {"cases": [{"id": "500002", "priority": "High"}]}}
    findings = evaluate_simple(_case(before, after))
    assert findings[0].value == 1 and findings[0].occurrence == "invocation"
    assert findings[1].value == 1
    assert evaluate_simple(_case(before, after, acknowledged=False))[0].value is None
    assert evaluate_simple(_case(before, after, complete=False))[0].value is None
    wrong = {"salesforce": {"cases": [{"id": "500002", "priority": "Low", "description": "High"}]}}
    assert evaluate_simple(_case(before, wrong))[0].value == 0
    wrong_id = {"salesforce": {"cases": [{"id": "500003", "priority": "High"}]}}
    assert evaluate_simple(_case(before, wrong_id))[0].value == 0


def test_normal_loader_only_selects_the_four_reviewed_requests():
    config = AutomationBenchConfig(
        domains=["simple"], task=AutomationBenchTaskConfig(reviewed_simple_assessments=True)
    )
    tasks = AutomationBenchTaskset(config).load()
    reviewed = [task for task in tasks if isinstance(task, ReviewedSimpleTask)]
    assert {task.data.task_name for task in reviewed} == set(REQUESTS)
    assert len(tasks) > len(reviewed)


async def _native_score(trace, data, case):
    task_data = AutomationBenchData.model_validate(data)
    task = ReviewedSimpleTask(task_data, AutomationBenchTaskConfig(capture_actions=True))
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=task_data.initial_state,
        assertions=task_data.assertions,
    )
    original = trace.rewards["partial_credit"]
    await task.score(trace)
    assert not trace.assessment_errors and not trace.credit_errors
    assert trace.rewards["partial_credit"] == original
    batch = trace.assessment_batches[-1]
    assert batch.run.producer_id == "automationbench.reviewed_simple"
    goal = next(
        record
        for record in batch.assessments
        if record.signal.signal_id == "simple.requested_state"
    )
    assert goal.value == 1 and goal.subject.kind == "trace"
    assignments = [
        assignment
        for assignment in trace.credit_assignments
        if assignment.request.rule.rule_id == "simple_identity_finding"
        and assignment.status == "complete"
        and any(
            goal.assessment_id in item.parent_assessment_ids for item in assignment.contributions
        )
    ]
    assert len(assignments) == 1
    contribution = assignments[0].contributions[0]
    assert contribution.channel == "simple.requested_state"
    assert contribution.recipient.kind == "execution"
    assert contribution.recipient.execution.invocation_id in case["reviewed_occurrence_ids"]
    assert contribution.parent_assessment_ids == (goal.assessment_id,)
    assert len(task.credit_requests(batch.source, (batch, batch))) == 1
    for field in ("producer_revision", "rubric_revision"):
        stale = batch.model_copy(update={"run": batch.run.model_copy(update={field: "stale"})})
        assert task.credit_requests(batch.source, (stale,)) == []
    for changed in (
        goal.model_copy(update={"subject": contribution.recipient}),
        goal.model_copy(update={"signal": goal.signal.model_copy(update={"units": "altered"})}),
    ):
        with pytest.raises(ValueError, match="credit_outcome_contract_mismatch"):
            task.credit_recipient(batch.source, changed)
    assert task.credit_recipient(batch.source, goal.model_copy(update={"value": 0})) is None
    diagnostic = next(
        record for record in batch.assessments if record.signal.direction == "neutral"
    )
    assert task.credit_recipient(batch.source, diagnostic) is None
    assert "assertions" not in batch.views[0].input_json
    restored = vf.WireTrace.model_validate(trace.model_dump(mode="json"))
    assert restored.assessment_batches == trace.assessment_batches
    assert restored.credit_assignments == trace.credit_assignments


def test_already_correct_does_not_require_a_pointless_write():
    state = {"salesforce": {"cases": [{"id": "500002", "priority": "High"}]}}
    finding = evaluate_simple(_case(state, state))[0]
    assert finding.value == 1 and finding.occurrence is None
    assert finding.reason == "already_correct_state"


def test_changed_public_request_cannot_reuse_old_constants():
    source = _case({}, {})
    source["task_evidence"]["prompt"][0]["content"] = "Update case 500003 to Low"
    with pytest.raises(ValueError, match="public_request_revision_unresolved"):
        evaluate_simple(source)


def test_public_initial_projection_preserves_types_lists_and_nulls():
    assert _declared_fields_match({"a": None}, {"a": None, "hydrated": "default"})
    assert not _declared_fields_match({"a": None}, {})
    assert not _declared_fields_match({"a": False}, {"a": 0})
    assert not _declared_fields_match({"a": [1, 2]}, {"a": [2, 1]})
    assert not _declared_fields_match({"a": []}, {"a": [1]})
    assert not _declared_fields_match({"a": {"b": 1}}, {"a": {"b": 2}})


@pytest.mark.parametrize(
    "service",
    [
        "bad",
        {"actions": []},
        {"actions": {"create_task": ["bad"]}},
        {"actions": {"create_task": [{"id": "task", "params": []}]}},
    ],
)
def test_malformed_asana_state_is_a_typed_unavailable_condition(service):
    source = _case({"asana": service}, {"asana": service})
    source["task_evidence"].update(
        task_name="simple.asana_api_docs_task",
        prompt=[{"role": "user", "content": REQUESTS["simple.asana_api_docs_task"]}],
    )
    with pytest.raises(ValueError, match="schema_unresolved"):
        evaluate_simple(source)


def test_final_state_mismatch_keeps_outcome_without_action_attribution():
    before = {"salesforce": {"cases": [{"id": "500002", "priority": "Low"}]}}
    after = {"salesforce": {"cases": [{"id": "500002", "priority": "High"}]}}
    source = _case(before, after)
    source["task_evidence"]["final"] = {**after, "unobserved_service": {"field": "changed"}}
    goal, coverage = evaluate_simple(source)
    assert goal.value == 1 and goal.occurrence is None
    assert coverage.value is None


def test_reconciled_subchain_does_not_claim_full_initial_capture():
    before = {"salesforce": {"cases": [{"id": "500002", "priority": "Low"}]}}
    after = {"salesforce": {"cases": [{"id": "500002", "priority": "High"}]}}
    source = _case(before, after)
    receipt = json.loads(source["tool_execution_events"][0]["receipt_json"])
    receipt.update(state_read_revision=1, state_write_revision=2)
    source["tool_execution_events"][0]["receipt_json"] = json.dumps(receipt)
    source["state_write_receipts"][0].update(expected_revision=1, applied_revision=2)
    goal, coverage = evaluate_simple(source)
    assert goal.value == 1 and goal.occurrence is None
    assert coverage.value is None


def test_duplicate_creation_preserves_two_effects_but_one_first_accomplishment():
    params = {
        "name": "Update API documentation",
        "workspace": "ws_prod",
        "project": "proj_eng",
        "dueDate": "2026-03-07",
    }
    first = {"id": "first", "params": params}
    second = {"id": "second", "params": params}
    before = {"asana": {"actions": {}}}
    middle = {"asana": {"actions": {"create_task": [first]}}}
    after = {"asana": {"actions": {"create_task": [first, second]}}}
    source = _case(before, middle)
    later = _source(middle, after)
    event = later["tool_execution_events"][0]
    receipt = json.loads(event["receipt_json"])
    receipt.update(invocation_id="second_invocation", state_read_revision=1, state_write_revision=2)
    event["receipt_json"] = json.dumps(receipt)
    source["tool_execution_events"].append(event)
    source["state_write_receipts"].append(
        {
            "write_id": "second_invocation",
            "expected_revision": 1,
            "applied_revision": 2,
            "conflict": False,
        }
    )
    source["task_evidence"].update(
        task_name="simple.asana_api_docs_task",
        final=after,
        prompt=[{"role": "user", "content": REQUESTS["simple.asana_api_docs_task"]}],
    )
    goal, coverage = evaluate_simple(source)
    assert goal.value == 1 and goal.occurrence == "invocation"
    assert coverage.value == 1
    assert len(source["tool_execution_events"]) == 2


def test_calendar_equivalent_offsets_and_wrong_duration():
    before = {"google_calendar": {"events": []}}
    event = {
        "id": "event",
        "calendarid": "cal_primary",
        "summary": "1:1 with Jordan",
        "start__dateTime": "2026-02-26T11:00:00-05:00",
        "end__dateTime": "2026-02-26T11:30:00-05:00",
        "attendees": ["jordan.lee@company.example.com"],
    }
    source = _case(before, {"google_calendar": {"events": [event]}})
    source["task_evidence"].update(
        task_name="simple.gcal_one_on_one",
        prompt=[
            {
                "role": "user",
                "content": REQUESTS["simple.gcal_one_on_one"],
            }
        ],
    )
    assert evaluate_simple(source)[0].value == 1
    bad = {**event, "end__dateTime": "2026-02-26T12:00:00-05:00"}
    source = _case(before, {"google_calendar": {"events": [bad]}})
    source["task_evidence"].update(
        task_name="simple.gcal_one_on_one",
        prompt=[
            {
                "role": "user",
                "content": REQUESTS["simple.gcal_one_on_one"],
            }
        ],
    )
    assert evaluate_simple(source)[0].value == 0
    malformed = _case(
        before,
        {"google_calendar": {"events": [{**event, "attendees": "jordan.lee@company.example.com"}]}},
    )
    malformed["task_evidence"].update(
        task_name="simple.gcal_one_on_one",
        prompt=[{"role": "user", "content": REQUESTS["simple.gcal_one_on_one"]}],
    )
    with pytest.raises(ValueError, match="attendee_schema_unresolved"):
        evaluate_simple(malformed)


@pytest.mark.parametrize(
    "task_name",
    [
        "simple.sf_case_priority_high",
        "simple.hs_update_contact_phone",
        "simple.asana_api_docs_task",
        "simple.gcal_one_on_one",
    ],
)
def test_actual_source_bound_development_request(task_name):
    report = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-policy-contracts.json"
    )
    if not report.exists():
        pytest.skip("retained development registry unavailable")
    case = next(
        item for item in json.loads(report.read_text())["tasks"] if item["task_name"] == task_name
    )
    binding = case["source_binding"]
    raw = Path(binding["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == binding["source_episode_sha256"]
    episode = vf.WireEpisode.model_validate_json(raw)
    trace = episode.traces[0]
    data = episode.task.data.model_dump(mode="json")
    source = {
        "task_evidence": {
            "task_name": task_name,
            "prompt": data["prompt"],
            "initial": data["initial_state"],
            "final": trace.info["automationbench"]["end_state"],
            "complete": trace.is_completed and trace.ok and not trace.errors,
        },
        "tool_execution_events": [
            item.model_dump(mode="json") for item in trace.tool_execution_events
        ],
        "state_write_receipts": [
            item.model_dump(mode="json") for item in trace.state_write_receipts
        ],
    }
    findings = evaluate_simple(source)
    assert findings[0].value == 1 and findings[0].occurrence in case["reviewed_occurrence_ids"]
    assert findings[1].value == 1
    # Receipt arrival order does not establish serial effect order. Preserve each
    # invocation lifecycle while reversing the independent arrival groups.
    grouped = {}
    for event in source["tool_execution_events"]:
        receipt = json.loads(event["receipt_json"])
        grouped.setdefault((event["source"], receipt["invocation_id"]), []).append(event)
    source["tool_execution_events"] = [
        event for group in reversed(tuple(grouped.values())) for event in group
    ]
    source["state_write_receipts"].reverse()
    assert evaluate_simple(source) == findings
    asyncio.run(_native_score(trace, data, case))
