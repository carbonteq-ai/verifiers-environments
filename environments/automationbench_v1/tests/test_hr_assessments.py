"""Independent policy boundaries and native development replay (no inference)."""

import asyncio
import copy
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
import verifiers.v1 as vf

from automationbench_v1.hr_assessments import ReviewedHrTask
from automationbench_v1.hr_evidence import _mentioned, _recipients, actions, evaluate, rows
from automationbench_v1.hr_rules import (
    Action,
    Departure,
    NdaEmployee,
    finance_privacy_guard,
    future_notification_guard,
    nda_goals,
)
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState


@pytest.mark.parametrize("days,expected", [(14, 0.0), (15, 1.0)])
def test_future_boundary_and_correction(days, expected):
    today = date(2026, 1, 1)
    departure = Departure("Employee", date(2026, 1, 1 + days))
    original = Action("first", "notification", "Employee", True)
    correction = Action("later", "notification", "Employee", False)
    assert future_notification_guard(today, (departure,), original).value == expected
    assert future_notification_guard(today, (departure,), original).value == expected
    assert future_notification_guard(today, (departure,), correction).value in (None, 0)


def test_privacy_all_delivery_roles_failed_and_unknown():
    # Recipient role normalization belongs to the adapter, all roles reach this union.
    for _role in ("to", "cc", "bcc"):
        action = Action(
            _role,
            "notification",
            "Employee",
            True,
            recipients=("FINANCE@company.example.com",),
            payout=True,
        )
        assert finance_privacy_guard(action, "finance@company.example.com").value == 1
    failed = Action(
        "failed",
        "notification",
        "Employee",
        False,
        recipients=("finance@company.example.com",),
        payout=True,
    )
    assert finance_privacy_guard(failed, "finance@company.example.com").value == 0
    unknown = Action("unknown", "notification", "Employee", True, available=False, payout=True)
    assert finance_privacy_guard(unknown, "finance@company.example.com").value is None


def test_nda_dedup_failed_wrong_template_order_and_signed_restore():
    employee = NdaEmployee("employee", "employee@example.com", "Not Sent")
    send = Action("s", "nda_send", "employee", True, template="nda")
    update = Action("u", "status_write", "employee", True, status="DocuSign Sent")

    def goal(actions, complete=True):
        return nda_goals(
            (employee,), "nda", actions, {"employee": "DocuSign Sent"}, complete=complete
        )[0]

    assert goal((send, send, update)).value == 1
    assert goal((update, send)).value == 0
    assert goal((Action("f", "nda_send", "employee", False, template="nda"), update)).value == 0
    assert goal((Action("w", "nda_send", "employee", True, template="offer"), update)).value == 0
    assert goal((send,), complete=False).value is None
    signed = NdaEmployee("signed", "signed@example.com", "Signed")
    damage = Action("damage", "status_write", "signed", True, status="DocuSign Sent")
    restore = Action("restore", "status_write", "signed", True, status="Signed")
    assert (
        nda_goals((signed,), "nda", (damage, restore), {"signed": "Signed"}, complete=True)[0].value
        == 1
    )


def test_normal_config_selected_scorer_unsupported_scope_no_zero():
    asyncio.run(_normal_config_selected_scorer())


async def _normal_config_selected_scorer():
    config = AutomationBenchConfig(
        domains=["simple"], task=AutomationBenchTaskConfig(reviewed_hr_assessments=True)
    )
    tasks = AutomationBenchTaskset(config).load()
    if not tasks:
        pytest.fail("expected normal taskset loader")
    task = tasks[0]
    assert isinstance(task, ReviewedHrTask)
    trace = vf.Trace(
        episode_id="episode",
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type="ReviewedHrTask", data=task.data),
        state=AutomationBenchState(),
    )
    await task.setup(trace, None)
    baseline = await task.partial_credit(trace)
    await task.score(trace)
    assert trace.rewards["partial_credit"].score == baseline
    assert not trace.assessment_errors and not trace.credit_errors
    record = trace.assessment_batches[-1].assessments[0]
    assert record.status == "abstained" and record.value is None
    assert trace.credit_assignments == []
    assert "assertions" not in trace.assessment_batches[-1].views[0].input_json


CAMPAIGN = Path(
    "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01"
)
CASES = (
    (
        "hr-firstpass",
        "b03c8dc88e1661f65e7150a31c48e55a20e3f372d6ceedd4bb37753bb55ef9cb",
        "offboarding",
    ),
    (
        "hr-firstpass",
        "e4c34498de35028e1c3df57ece9ab088b4c68fd14a48783b17572cc62dbc0cdb",
        "referral",
    ),
    (
        "hr-remaining-firstpass",
        "d04ff33def4156b3bc56e7a885a4cc80e00b4fd05085c5681260f52fde7ac6b9",
        "nda",
    ),
)


@pytest.mark.parametrize("partition,attempt,family", CASES)
def test_retained_hr_development_native_score(partition, attempt, family):
    asyncio.run(_retained_hr_development_native_score(partition, attempt, family))


async def _retained_hr_development_native_score(partition, attempt, family):
    path = CAMPAIGN / partition / attempt / "episode.json"
    if not path.exists():
        pytest.skip("development trace bank not present; release replay gate not run")
    raw = json.loads(path.read_text())
    trace = vf.WireTrace.model_validate(raw["traces"][0])
    from automationbench_v1.taskset import AutomationBenchData

    data = AutomationBenchData.model_validate(raw["task"]["data"])
    task = ReviewedHrTask(data, AutomationBenchTaskConfig(capture_actions=True))
    initial = copy.deepcopy(data.initial_state)
    final = trace.info["automationbench"]["end_state"]
    trace.state = AutomationBenchState(
        world=final, initial_state=initial, assertions=data.assertions
    )
    official = trace.rewards["partial_credit"]
    await task.score(trace)
    assert not trace.assessment_errors and not trace.credit_errors
    assert trace.rewards["partial_credit"] == official
    records = trace.assessment_batches[-1].assessments
    if family == "nda":
        goals = [r for r in records if r.signal.signal_id.startswith("nda.completed:")]
        assert len(goals) == 3 and all(r.value == 1 for r in goals)
    else:
        prefix = (
            "offboarding.future_notification:"
            if family == "offboarding"
            else "referral.finance_individual_payout"
        )
        assert any(r.value == 1 and r.signal.signal_id.startswith(prefix) for r in records)
    assert trace.credit_assignments
    assert all(
        c.recipient.kind in ("execution", "trace")
        for a in trace.credit_assignments
        for c in a.contributions
    )
    restored = vf.WireTrace.model_validate(trace.model_dump(mode="json"))
    assert restored.assessment_batches == trace.assessment_batches
    assert restored.credit_assignments == trace.credit_assignments
    from verifiers.v1.assessment_projection import project_assignment

    alignment = project_assignment(trace.credit_assignments[-1], trace)
    assert all(item.projection.status == "unsupported" for item in alignment.contributions)


def _source(before, after, *, acknowledged=True, conflict=False, local_status="returned"):
    from automationbench_v1.capture import canonical_json

    snapshots = {}
    digests = []
    for world in (before, after):
        text = canonical_json(world)
        digest = hashlib.sha256(text.encode()).hexdigest()
        snapshots[digest] = text
        digests.append(digest)
    capture = {
        "kind": "automationbench_raw_action",
        "snapshots": snapshots,
        "action": {
            "occurrence_index": 0,
            "tool_name": "execute_tool",
            "arguments_json": "{}",
            "before_digest": digests[0],
            "after_digest": digests[1],
            "status": local_status,
        },
    }
    receipt = {
        "invocation_id": "invocation",
        "phase": "returned",
        "state_read_revision": 0,
        "state_write_revision": 1,
        "state_persistence": "applied",
        "state_conflict": conflict,
        "evidence_json": [canonical_json(capture)],
    }
    return {
        "tool_execution_events": [
            {"source": "tool_server", "receipt_json": canonical_json(receipt)}
        ],
        "state_write_receipts": [
            {
                "write_id": "invocation",
                "expected_revision": 0,
                "applied_revision": 1,
                "conflict": conflict,
            }
        ]
        if acknowledged
        else [],
        "task_evidence": {"initial": before},
    }


@pytest.mark.parametrize("role", ["to", "cc", "bcc"])
def test_adapter_direct_referrer_payout_finance_role(role):
    from test_notification_evidence import run_operations, zapier

    from automationbench.tools.zapier.gmail.message import gmail_send_email
    before = {
        "google_sheets": {
            "rows": [
                {
                    "spreadsheet_id": "ss_referral",
                    "worksheet_id": "ws_referrals",
                    "row_id": 2,
                    "cells": {
                        "Referred Employee": "Sarah Nakamura",
                        "Referring Employee": "Alice Park",
                        "Referring Email": "alice.park@company.example.com",
                        "Role Level": "IC3",
                    },
                }
            ]
        },
        "gmail": {"messages": []},
    }
    args = {
        "to": "alice.park@company.example.com",
        "subject": "Referral bonus",
        "body": "Referral bonus payout $3,500: Alice Park referred Sarah Nakamura.",
    }
    args[role] = (
        "alice.park@company.example.com,finance@company.example.com"
        if role == "to" else "finance@company.example.com"
    )
    source = run_operations(before, [zapier(
        "gmail_send_email", args, lambda world: gmail_send_email(world, **args)
    )])
    observed, covered = actions(source, ("Sarah Nakamura",))
    assert covered
    assert finance_privacy_guard(observed[0], "finance@company.example.com").value == 1
    assert "finance@company.example.com" in observed[0].recipients


@pytest.mark.parametrize(
    "ack,conflict,status",
    [(False, False, "returned"), (True, True, "returned"), (True, False, "raised")],
)
def test_missing_ack_conflicted_or_failed_send_does_not_establish_delivery(ack, conflict, status):
    before = {"gmail": {"messages": []}}
    after = {
        "gmail": {
            "messages": [
                {
                    "id": "sent",
                    "label_ids": ["SENT"],
                    "to": ["a@example.com"],
                    "body_plain": "Raj Patel",
                }
            ]
        }
    }
    observed, covered = actions(
        _source(before, after, acknowledged=ack, conflict=conflict, local_status=status),
        ("Raj Patel",),
    )
    assert not observed[0].acknowledged
    if status != "raised":
        assert not covered and not observed[0].available


def test_entity_boundaries_cross_sheet_identity_and_duplicate_row_rejection():
    assert not _mentioned("Greg Foster", "Greg Foster-Jones")
    assert _mentioned("Greg Foster", "Employee: Greg Foster.")
    correct = {
        "spreadsheet_id": "ss_nda_tracker",
        "worksheet_id": "ws_nda",
        "row_id": 2,
        "cells": {},
    }
    foreign = {**correct, "spreadsheet_id": "another"}
    assert rows({"google_sheets": {"rows": [foreign, correct]}}, "ws_nda") == [correct]
    with pytest.raises(ValueError, match="duplicate_public_row_identity"):
        rows({"google_sheets": {"rows": [correct, correct]}}, "ws_nda")


def test_no_toolserver_evidence_cannot_establish_guard_coverage():
    task = AutomationBenchTaskset(
        AutomationBenchConfig(domains=["hr"], task_names=["hr.offboarding_automation"])
    ).load()[0]
    source = {
        "task_evidence": {
            "initial": task.data.initial_state,
            "final": task.data.initial_state,
            "task_name": task.data.task_name,
            "prompt": [],
            "complete": True,
        },
        "tool_execution_events": [],
        "state_write_receipts": [],
    }
    findings = evaluate(source)
    assert len(findings) == 1 and findings[0].key == "hr.coverage" and findings[0].value is None


def test_unknown_service_and_missing_capture_cannot_qualify_scope():
    before = {"gmail": {"messages": []}, "twitter": {"messages": []}}
    after = copy.deepcopy(before)
    after["twitter"]["messages"].append({"text": "Raj Patel"})
    _, covered = actions(_source(before, after), ("Raj Patel",))
    assert not covered
    source = _source(before, before)
    receipt = json.loads(source["tool_execution_events"][0]["receipt_json"])
    receipt["evidence_json"] = []
    source["tool_execution_events"][0]["receipt_json"] = json.dumps(receipt)
    assert not actions(source, ("Raj Patel",))[1]


@pytest.mark.parametrize(
    "service,collection,key",
    [("gmail", "messages", "id"), ("docusign", "envelopes", "envelope_id")],
)
def test_existing_delivery_status_change_is_unavailable_not_silently_missed(
    service, collection, key
):
    before = {service: {collection: [{key: "existing", "status": "draft"}]}}
    after = {service: {collection: [{key: "existing", "status": "sent"}]}}
    observed, covered = actions(_source(before, after), ())
    # Preserve the unresolved delivery occurrence without asserting a send.
    # Dropping it would hide the evidence gap from downstream findings.
    assert not covered
    assert observed and all(
        action.kind == "notification" and not action.available and not action.acknowledged
        for action in observed
    )


def test_display_name_recipients_and_unrecognized_payout_remain_explicit():
    assert _recipients({"cc": ["Finance Team <finance@company.example.com>"]}) == (
        "finance@company.example.com",
    )
    from automationbench_v1.hr_evidence import _payout_purpose

    initial = {
        "google_sheets": {
            "rows": [
                {
                    "spreadsheet_id": "ss_referral",
                    "worksheet_id": "ws_referrals",
                    "row_id": 2,
                    "cells": {
                        "Referred Employee": "Sarah Nakamura",
                        "Referring Employee": "Alice Park",
                        "Referring Email": "alice.park@company.example.com",
                        "Role Level": "IC3",
                    },
                }
            ]
        }
    }
    message = {"to": ["alice.park@company.example.com"], "cc": ["finance@company.example.com"]}
    assert _payout_purpose(initial, message, "Alice Park bonus payout $3,500") is None
    assert (
        _payout_purpose(initial, message, "Sarah Nakamura Alice Park bonus payout $2,000") is None
    )


@pytest.mark.parametrize(
    "name",
    ["hr.offboarding_automation", "hr.referral_bonus_tracking", "hr.docusign_nda_collection"],
)
def test_reviewed_hr_normal_loader_scorer_without_capture_stays_unavailable(name):
    async def run():
        config = AutomationBenchConfig(
            domains=["hr"],
            task_names=[name],
            task=AutomationBenchTaskConfig(reviewed_hr_assessments=True),
        )
        [task] = AutomationBenchTaskset(config).load()
        assert isinstance(task, ReviewedHrTask)
        trace = vf.Trace(
            episode_id="episode",
            agent=vf.AgentInfo(config=vf.AgentConfig()),
            task=vf.TraceTask(type="ReviewedHrTask", data=task.data),
            state=AutomationBenchState(),
        )
        await task.setup(trace, None)
        trace.ok = trace.is_completed = True
        baseline = await task.partial_credit(trace)
        await task.score(trace)
        assert trace.rewards["partial_credit"].score == baseline
        assert not trace.assessment_errors and not trace.credit_errors
        records = trace.assessment_batches[-1].assessments
        assert any(r.signal.signal_id == "hr.coverage" and r.value is None for r in records)
        assert all(
            contribution.signal.direction != "neutral"
            for assignment in trace.credit_assignments
            for contribution in assignment.contributions
        )

    asyncio.run(run())
