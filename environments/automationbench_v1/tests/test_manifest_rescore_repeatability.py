"""Rescoring a trace reproduces identical manifest inputs (no wall-clock capture)."""

import asyncio
import json

from test_batch01_manifests import recorded

from automationbench_v1.contracts.evidence import target_record
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_obligation_assessments import OBLIGATION_OUTPUT
from automationbench_v1.taskset import AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState


class Selector:
    object_type = "Contact"
    record_id = "003X"


def test_absent_salesforce_timestamps_stay_absent_instead_of_now():
    world = {"salesforce": {"contacts": [{"id": "003X", "first_name": "Ada", "last_name": "Lovelace"}]}}
    first, second = target_record(world, Selector()), target_record(world, Selector())
    assert first == second
    assert "created_date" not in first and "last_modified_date" not in first
    stamped = {"salesforce": {"contacts": [{"id": "003X", "last_name": "Lovelace",
                                            "created_date": "2026-01-02T03:04:05Z"}]}}
    assert target_record(stamped, Selector())["created_date"] == "2026-01-02T03:04:05Z"


def scope_receipts(trace):
    found = []
    for batch in trace.assessment_batches:
        if batch.run.status != "complete":
            continue
        for receipt in batch.run.execution_evidence:
            payload = json.loads(receipt.payload_json) if receipt.kind == OBLIGATION_OUTPUT else {}
            if payload.get("kind") == "scope":
                found.append((payload["check_id"], payload["input_digest"]))
    return found


def test_rescoring_the_installed_contact_contract_adds_no_new_scope_inputs():
    name = "simple.email_sf_contact_assistant_update"
    _, _, _, trace, data = recorded(name)
    trace.state = AutomationBenchState(world=trace.info["automationbench"]["end_state"],
                                       initial_state=data.initial_state, assertions=data.assertions,
                                       artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    asyncio.run(task.score(trace))
    first, rewards, credit = scope_receipts(trace), list(trace.rewards), list(trace.credit_assignments)
    assert first and not trace.assessment_errors and not trace.credit_errors
    asyncio.run(task.score(trace))
    second = scope_receipts(trace)
    assert set(second) == set(first)
    assert list(trace.rewards) == rewards and len(trace.credit_assignments) == len(credit)
