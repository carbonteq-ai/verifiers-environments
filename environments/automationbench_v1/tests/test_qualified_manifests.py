"""Installed whole-task manifests that passed independent qualification review.

Each task's packaged bytes are the reviewed draft in manifest-drafts/tasks/<task>/
(qualification-review.md records the review and coordinator resolution). The
hash-bound Luna replay scores through the real catalog and must reproduce the
reviewed per-check findings with no abstention, no errors, unchanged scalar
rewards and identical results on rescore.
"""

import asyncio
import copy
import hashlib
import json
from collections import Counter
from importlib.resources import files
from pathlib import Path

import pytest
from test_batch01_manifests import recorded

from automationbench_v1.contracts import load_contract, load_task_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

DRAFTS = Path(__file__).resolve().parents[1] / "manifest-drafts" / "tasks"

QUALIFIED = {
    "simple.email_zendesk_ack_reply": (
        "simple-email-zendesk-ack-reply.json", "513ca4f431da50d1b60749312f23570f0edad409308aa5b3788e542051c8af12"),
    "finance.escrow_tracking": (
        "finance-escrow-tracking.json", "8fe35e6d359a0f17ce8176884f8fede377b916dcfd383338aeb5dd6bdec83048"),
    "hr.airtable_learning_path_assignment": (
        "hr-airtable-learning-path-assignment.json", "6938237d4f7b94929162a4c847af024bea9824d085bce314faf190639219bac6"),
    "operations.zoom_training_setup": (
        "operations-zoom-training-setup.json", "61e8e4bdb9ddfff0d98a495603935ac47ececdd3139fd5f691922caad8772b64"),
    "operations.calendly_equipment_inspection": (
        "operations-calendly-equipment-inspection.json", "eba5ab47899161a7d251857b54ad361684fb1c387cb29950caa0d4c15b4c037b"),
}

# Reviewed Luna outcome per check: "status/value" -> number of candidate findings.
LUNA = json.loads((Path(__file__).with_name("qualified_manifests_luna.json")).read_text())


def findings(trace, start=0):
    found = Counter()
    for batch in trace.assessment_batches[start:]:
        assert batch.run.status not in {"failed", "interrupted"}
        if batch.run.status != "complete":
            continue
        for receipt in batch.run.execution_evidence:
            payload = json.loads(receipt.payload_json)
            if isinstance(payload, dict) and payload.get("kind") == "finding":
                found[payload["check_id"], f"{payload['status']}/{payload['value']}"] += 1
    return found


def summary(found):
    result: dict[str, dict[str, int]] = {}
    for (check, outcome), count in sorted(found.items()):
        result.setdefault(check, {})[outcome] = count
    return result


def replay(task_name):
    path, raw, episode, trace, data = recorded(task_name)
    trace.state = AutomationBenchState(world=trace.info["automationbench"]["end_state"], initial_state=data.initial_state,
                                       assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    first = findings(trace)
    assert not trace.assessment_errors and not trace.credit_errors
    count = len(trace.assessment_batches)
    asyncio.run(task.score(trace))
    assert findings(trace, count) == first
    assert trace.rewards == scalar
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == hashlib.sha256(raw).hexdigest()
    return first


@pytest.mark.parametrize("task_name", sorted(QUALIFIED))
def test_packaged_bytes_are_the_reviewed_draft(task_name):
    filename, sha = QUALIFIED[task_name]
    raw = files("automationbench_v1.contracts").joinpath("tasks", filename).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == sha
    draft = DRAFTS / task_name / "draft.json"
    assert draft.read_bytes() == raw
    assert load_task_contract(task_name) == load_contract(raw)
    assert (DRAFTS / task_name / "qualification-review.md").exists()


@pytest.mark.parametrize("task_name", sorted(QUALIFIED))
def test_luna_replay_reproduces_reviewed_findings(task_name):
    found = replay(task_name)
    assert not any(outcome.startswith("abstained") for _, outcome in found)
    assert summary(found) == LUNA[task_name]
