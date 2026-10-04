"""Qualification of the prepaid controller total line, not of the whole report.

The report component checks one Gmail send for the requested recipient and the
requested ``Total amortization: $X`` line against totals recomputed from public
policy. It does not verify entity names, journal lines, schedule changes or
guards, and it assigns no action credit. The hash-bound Luna replay is real;
alternatives use genuine simulator handlers in validated native envelopes.
"""

import asyncio
import copy
import hashlib
import json
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import native_fixture, terminal_records
from test_notification_evidence import run_operations, zapier
from test_prepaid_manifest_guard import update
from test_prepaid_schedule_manifest import CORRECT, RECORDED_SHA, outcomes, saved, simulated

from automationbench.tools.zapier.gmail.message import gmail_get_email_by_id, gmail_send_email
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract, load_task_contract
from automationbench_v1.contracts.obligations import ObligationCheck
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_guard_assessments import digest
from automationbench_v1.manifest_obligation_assessments import OBLIGATION_OUTPUT
from automationbench_v1.taskset import AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

__all__ = ["saved"]  # module fixture reused from the schedule qualification

DRAFT = Path(__file__).resolve().parents[1] / 'manifest-drafts' / 'legacy' / 'prepaid-report-total-draft.json'
SCHEDULE_DRAFT = DRAFT.with_name("prepaid-schedule-draft.json")
PACKAGED_SHA = "2d934cfd68bb8bcbcbd7497dc2ffa2d66298f5ddd516d231611e103f87427138"
CHECK = "controller-total-line"
SIGNAL = "prepaid.controller_total_line"
CONTROLLER = "controller@company.example.com"


@pytest.fixture
def draft():
    # The packaged revision is the reviewed draft; scoring uses the real catalog.
    installed = load_task_contract("finance.prepaid_amortization")
    if DRAFT.exists():
        assert installed == load_contract(DRAFT.read_text())
    return installed


def send(body, *, to=CONTROLLER, body_type="plain"):
    args = {"to": to, "subject": "February amortization journal entry", "body": body, "body_type": body_type}
    return zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))


def report(line="Total amortization: $4,900"):
    return "Journal entries\n\nAnnual Insurance $4,000\nSoftware License $600\nCloud Hosting $300\n\n" + line


def schedule_updates():
    return [update(row, cells) for row, cells in CORRECT.items()]


def receipts(trace):
    found = []
    for batch in trace.assessment_batches:
        if batch.run.status != "complete":
            continue
        for receipt in batch.run.execution_evidence:
            if receipt.kind == OBLIGATION_OUTPUT:
                payload = json.loads(receipt.payload_json)
                if payload["check_id"] == CHECK:
                    found.append(payload)
    return found


def line(trace):
    findings = [item for item in receipts(trace) if item["kind"] == "finding"]
    assert len(findings) == 1
    return findings[0]


def scope(trace):
    scopes = [item for item in receipts(trace) if item["kind"] == "scope"]
    assert len(scopes) == 1
    return scopes[0]


def credit_for_line(trace):
    return [
        part
        for assignment in trace.credit_assignments
        for part in assignment.contributions
        if part.signal.signal_id == SIGNAL
    ]


def _path_bytes(saved):
    return saved[0].read_bytes()


def test_only_the_prepaid_revision_declares_aggregates():
    from automationbench_v1.contracts.loader import supported_tasks

    # Installed training candidates (installed_candidate_manifests.json) may use
    # aggregates freely; this pins the reviewed installed manifests only.
    candidates = json.loads(Path(__file__).with_name("installed_candidate_manifests.json").read_text())
    declaring = set()
    for name in sorted(set(supported_tasks()) - set(candidates)):
        for check in load_task_contract(name).checks:
            if isinstance(check, ObligationCheck) and "aggregates" in check.model_dump(mode="json"):
                declaring.add((name, check.check_id))
    assert declaring == {("finance.prepaid_amortization", CHECK)}


def test_packaged_revision_matches_reviewed_draft_bytes_and_extends_v3(draft):
    packaged = files("automationbench_v1.contracts").joinpath(
        "tasks/finance-prepaid-schedule-and-guard.json").read_bytes()
    assert hashlib.sha256(packaged).hexdigest() == PACKAGED_SHA
    if DRAFT.exists():
        assert DRAFT.read_bytes() == packaged
    assert draft.revision == "public_batch01_schedule_report_v4"
    if SCHEDULE_DRAFT.exists():
        schedule = load_contract(SCHEDULE_DRAFT.read_text())
        assert draft.checks[:-1] == schedule.checks and draft.credit == schedule.credit
        assert draft.bindings == schedule.bindings
        assert {k: v for k, v in draft.sources.items() if k in schedule.sources} == dict(schedule.sources)
    assert not any(rule.check == CHECK for rule in draft.credit)


def test_actual_luna_send_reaches_controller_but_reports_the_wrong_total(saved, draft):
    _, original_bytes, episode, trace, data = saved
    assert hashlib.sha256(original_bytes).hexdigest() == RECORDED_SHA
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state,
        assertions=data.assertions,
        artifacts=dict(trace.state.artifacts),
    )
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    assert trace.rewards == scalar
    finding = line(trace)
    # Luna wrote "Total amortization: $4,300" and omitted the corrected
    # software licence; public policy totals 4,000 + 300 + 600.
    assert finding["status"] == "valid" and finding["value"] == 0
    assert finding["reason"] == "obligation_required_effect_missing"
    evidence = json.loads(scope(trace)["aggregate_evidence_json"])
    assert [(alias, item["status"], item["canonical_value"]) for alias, item in evidence] == [
        ("insurance", "qualified", "4000"),
        ("standard", "qualified", "300"),
        ("software", "qualified", "600"),
    ]
    assert finding["aggregate_digest"] == digest(evidence)
    assert not credit_for_line(trace)
    # The schedule findings from the installed revision are unchanged.
    schedule = outcomes(trace)
    assert len(schedule) == 15 and sum(f["status"] == "valid" for f in schedule.values()) == 3
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, restored.traces[0])
    assert replay.assessment_batches == trace.assessment_batches
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors and replay.rewards == scalar
    replayed = [item for item in receipts(replay) if item["kind"] == "finding"]
    assert replayed and {(item["value"], item["aggregate_digest"]) for item in replayed} == {
        (0, finding["aggregate_digest"])
    }
    assert hashlib.sha256(_path_bytes(saved)).hexdigest() == RECORDED_SHA
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors and trace.rewards == scalar
    again = [item for item in receipts(trace) if item["kind"] == "finding"]
    assert again and {(item["value"], item["aggregate_digest"]) for item in again} == {
        (0, finding["aggregate_digest"])
    }


@pytest.mark.parametrize(
    "written", ["$4,900", "$4,900.00", "4900", "$4900.00", "4,900.0"]
)
def test_correct_total_in_supported_formats_satisfies_the_line(saved, draft, written):
    _, _, trace = simulated(saved, [send(report("Total amortization: " + written))])
    finding = line(trace)
    assert finding["status"] == "valid" and finding["value"] == 1
    assert len(finding["witnesses"]) == 1 and finding["witnesses"][0]["occurrence"] == "execution-0"
    assert not credit_for_line(trace)


@pytest.mark.parametrize(
    "body,reason",
    [
        (report("Total amortization: $4,300"), "obligation_required_effect_missing"),
        (report("Total amortization: $5,100"), "obligation_required_effect_missing"),
        ("Journal entries attached.", "obligation_required_effect_missing"),
    ],
)
def test_wrong_or_missing_total_is_a_known_zero(saved, draft, body, reason):
    _, _, trace = simulated(saved, [send(body)])
    finding = line(trace)
    assert (finding["status"], finding["value"], finding["reason"]) == ("valid", 0, reason)


def test_wrong_recipient_with_correct_line_is_zero(saved, draft):
    _, _, trace = simulated(saved, [send(report(), to="cfo@company.example.com")])
    assert line(trace)["value"] == 0


def test_recipient_and_line_must_come_from_the_same_send(saved, draft):
    calls = [send("Journal entries attached."), send(report(), to="cfo@company.example.com")]
    _, _, trace = simulated(saved, calls)
    assert line(trace)["value"] == 0


@pytest.mark.parametrize(
    "body",
    [
        report("Total amortization: $4,900\nTotal amortization: $4,800"),
        report("> Total amortization: $4,900"),
        report("**Total amortization:** $4,900"),
        report("total amortization: $4,900"),
        report("Total amortization: $4,900 USD"),
        report("```\nTotal amortization: $4,900\n```"),
        report("Total amortization: $4,900\n```\nTotal amortization: $4,900\n```"),
    ],
)
def test_conflicting_quoted_code_or_unparsed_lines_abstain(saved, draft, body):
    _, _, trace = simulated(saved, [send(body)])
    finding = line(trace)
    assert finding["status"] == "abstained" and finding["value"] is None


def test_identical_repeated_line_is_one_reported_value(saved, draft):
    body = report("Total amortization: $4,900\nTotal amortization: $4,900.00")
    _, _, trace = simulated(saved, [send(body)])
    assert line(trace)["value"] == 1


def test_html_only_body_abstains(saved, draft):
    _, _, trace = simulated(saved, [send("<p>Total amortization: $4,900</p>", body_type="html")])
    finding = line(trace)
    assert finding["status"] == "abstained" and finding["value"] is None


def test_send_without_acknowledgement_abstains(saved, draft):
    _, _, trace = simulated(saved, [send(report())], missing_ack=0)
    finding = line(trace)
    assert finding["status"] == "abstained" and finding["value"] is None


def test_one_correct_send_among_several_satisfies_the_occurrence(saved, draft):
    # Occurrence semantics: a later conflicting report is not a harm signal here.
    calls = [send(report("Total amortization: $4,300")), send(report())]
    _, _, trace = simulated(saved, calls)
    finding = line(trace)
    assert finding["value"] == 1 and [w["occurrence"] for w in finding["witnesses"]] == ["execution-1"]


def test_correct_total_with_incorrect_schedule_keeps_components_separate(saved, draft):
    wrong = update(3, {"Total": "$4,800", "Amortized to Date": "$900", "Remaining": "$3,900"})
    _, _, trace = simulated(saved, [wrong, send(report())])
    assert line(trace)["value"] == 1
    schedule = outcomes(trace)
    assert schedule["software-schedule-retained", 3]["value"] == 0


def test_correct_schedule_and_total_both_hold(saved, draft):
    _, _, trace = simulated(saved, [*schedule_updates(), send(report())])
    assert line(trace)["value"] == 1
    schedule = outcomes(trace)
    assert all(schedule[key]["value"] == 1 for key in [
        ("insurance-schedule-retained", 2), ("software-schedule-retained", 3),
        ("standard-schedule-retained", 6)])


def rows(saved):
    return copy.deepcopy(saved[-1].initial_state)


def item_row(initial, item):
    return next(row for row in initial["google_sheets"]["rows"]
                if row.get("worksheet_id") == "ws_prepaid_items" and row["cells"].get("Item") == item)


def test_totals_follow_public_inputs_rather_than_a_fixed_number(saved, draft):
    initial = rows(saved)
    item_row(initial, "Cloud Hosting Prepaid")["cells"]["Total"] = "$4,800"
    _, _, trace = simulated(saved, [send(report("Total amortization: $5,000"))], initial=initial)
    assert line(trace)["value"] == 1
    _, _, trace = simulated(saved, [send(report())], initial=initial)
    assert line(trace)["value"] == 0


def test_unknown_eligibility_makes_the_line_unknown_not_absent(saved, draft):
    initial = rows(saved)
    # A mid-month start leaves the reviewed coverage-period rule undecided.
    item_row(initial, "Cloud Hosting Prepaid")["cells"]["Start Date"] = "2026-02-15"
    _, _, trace = simulated(saved, [send(report())], initial=initial)
    finding = line(trace)
    assert finding["status"] == "abstained" and finding["reason"] == "obligation_aggregate_unavailable"
    evidence = dict(json.loads(scope(trace)["aggregate_evidence_json"]))
    assert evidence["standard"]["status"] == "unavailable"
    assert evidence["insurance"]["canonical_value"] == "4000"


def test_report_total_uses_the_schedule_obligations_eligibility(saved, draft):
    initial = rows(saved)
    # Expired coverage with a balance left: neither required nor in the total.
    item_row(initial, "Marketing Retainer")["cells"].update({"Remaining": "$1,500", "Term (Months)": "4"})
    # A note on a standard row is not a public exclusion rule.
    item_row(initial, "Cloud Hosting Prepaid")["cells"]["Notes"] = "Prepaid via card"
    _, _, trace = simulated(saved, [send(report())], initial=initial)
    assert line(trace)["value"] == 1
    evidence = dict(json.loads(scope(trace)["aggregate_evidence_json"]))
    assert evidence["standard"]["canonical_value"] == "300"
    schedule = outcomes(trace)
    assert schedule["standard-schedule-retained", 5]["status"] == "inapplicable"
    assert schedule["standard-schedule-retained", 6]["required"] is True


def test_cc_controller_with_correct_line_counts_as_delivered(saved, draft):
    args = {"to": "team@company.example.com", "cc": CONTROLLER, "subject": "Journal entry",
            "body": report()}
    call = zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))
    _, _, trace = simulated(saved, [call])
    assert line(trace)["value"] == 1


def test_reading_the_rules_by_id_keeps_send_scope_closed(saved, draft):
    rules = next(m["id"] for m in saved[-1].initial_state["gmail"]["messages"]
                 if m["subject"] == "Prepaid Amortization Rules")
    args = {"message_id": rules}
    read = zapier("gmail_get_email_by_id", args, lambda world: gmail_get_email_by_id(world, **args))
    _, _, trace = simulated(saved, [read, send(report("Total amortization: $4,300"))])
    finding = line(trace)
    assert (finding["status"], finding["value"]) == ("valid", 0)


def test_duplicate_member_identity_makes_every_total_unavailable(saved, draft):
    initial = rows(saved)
    initial["google_sheets"]["rows"].append(copy.deepcopy(item_row(initial, "Annual Insurance")))
    _, _, trace = simulated(saved, [send(report())], initial=initial)
    finding = line(trace)
    assert finding["status"] == "abstained" and finding["reason"] == "obligation_aggregate_unavailable"
    evidence = json.loads(scope(trace)["aggregate_evidence_json"])
    assert all(item["status"] == "unavailable" for _, item in evidence)


@pytest.mark.parametrize("tamper", ["scope_total", "finding_digest", "drop_digest"])
def test_planner_rejects_forged_aggregate_receipts(saved, draft, monkeypatch, tamper):
    original = ManifestAssessmentTask.plan_credit

    def altered(self, source, assessments, context):
        changed = []
        for batch in assessments:
            evidence = []
            for receipt in batch.run.execution_evidence:
                payload = json.loads(receipt.payload_json) if receipt.kind == OBLIGATION_OUTPUT else None
                if payload is not None and payload["check_id"] == CHECK:
                    if tamper == "scope_total" and payload["kind"] == "scope":
                        totals = json.loads(payload["aggregate_evidence_json"])
                        totals[0][1]["canonical_value"] = "4300"
                        payload["aggregate_evidence_json"] = canonical_json(totals)
                        payload["aggregate_digest"] = digest(totals)
                    elif tamper == "finding_digest" and payload["kind"] == "finding":
                        payload["aggregate_digest"] = "0" * 64
                    elif tamper == "drop_digest" and payload["kind"] == "finding":
                        del payload["aggregate_digest"]
                    # A coherent forger re-mints the native payload digest too.
                    receipt = type(receipt).capture(
                        receipt.kind, payload, invocation_id=receipt.invocation_id
                    )
                evidence.append(receipt)
            changed.append(batch.model_copy(update={"run": batch.run.model_copy(
                update={"execution_evidence": tuple(evidence)})}))
        return original(self, source, tuple(changed), context)

    monkeypatch.setattr(ManifestAssessmentTask, "plan_credit", altered)
    rejected = []
    planner = manifest_assessments.plan_obligation_credit

    def recorded_planner(*args, **kwargs):
        try:
            return planner(*args, **kwargs)
        except ValueError as error:
            rejected.append(str(error))
            raise

    monkeypatch.setattr(manifest_assessments, "plan_obligation_credit", recorded_planner)
    # Built directly: the shared helper requires a clean credit plan.
    original_initial = copy.deepcopy(saved[-1].initial_state)
    _, episode, trace = native_fixture(run_operations(original_initial, [send(report())]))
    data = saved[-1].model_copy(update={"initial_state": original_initial, "assertions": ()})
    trace.task = vf.TraceTask(type="Task", data=data)
    cast(Any, episode).task = trace.task
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    asyncio.run(task.score(trace))
    assert trace.credit_errors
    expected = {
        "scope_total": "obligation_credit_aggregate_mismatch",
        "finding_digest": "obligation_credit_aggregate_mismatch",
        "drop_digest": "obligation_credit_aggregate_mismatch",
    }[tamper]
    assert rejected == [expected]


def test_reload_and_rescore_keep_aggregate_bound_findings(saved, draft):
    task, episode, trace = simulated(saved, [send(report())])
    first = line(trace)
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    assert cast(Any, restored.traces[0]).assessment_batches == trace.assessment_batches
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    again = [item for item in receipts(trace) if item["kind"] == "finding"]
    assert all(item["aggregate_digest"] == first["aggregate_digest"] for item in again)
    assert {item["value"] for item in again} == {1}
    assert all(record.value == 1 for record in terminal_records(trace) if record.signal.signal_id == SIGNAL)
