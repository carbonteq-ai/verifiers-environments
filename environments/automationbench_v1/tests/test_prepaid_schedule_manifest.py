"""Qualification of the installed schedule component, not whole-task success.

The single hash-bound Luna replay is real. Alternative executions use genuine
simulator handlers inside manufactured, validated native execution envelopes.
The public draft owns policy; benchmark assertions never define these checks.
"""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_batch01_manifests import recorded
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_notification_evidence import run_operations
from test_prepaid_manifest_guard import update

from automationbench_v1 import manifest_assessments
from automationbench_v1.contracts import load_contract, load_task_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_retained_assessments import RETAINED_OUTPUT
from automationbench_v1.taskset import AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

DRAFT = Path(__file__).resolve().parents[1] / 'manifest-drafts' / 'legacy' / 'prepaid-schedule-draft.json'
RECORDED_SHA = "aceee3e62e4cdbc0f6938294dc879975dbae77afb155e442e6cb55e891dddede"
INSURANCE_EXECUTION = "9327ad3bab1143ceb89777654a9f08a0"
HOSTING_EXECUTION = "dd8f0d1f486a4445859819f04c161a91"
STANDARD = "standard-schedule-retained"
INSURANCE = "insurance-schedule-retained"
SOFTWARE = "software-schedule-retained"
CORRECT = {
    2: {"Amortized to Date": "$18,000", "Remaining": "$6,000"},
    3: {"Total": "$7,200", "Amortized to Date": "$1,100", "Remaining": "$6,100"},
    6: {"Amortized to Date": "$300", "Remaining": "$3,300"},
}


@pytest.fixture(scope="module")
def saved():
    return recorded("finance.prepaid_amortization")


@pytest.fixture
def draft(monkeypatch):
    if not DRAFT.exists():
        pytest.skip("local uninstalled prepaid schedule draft unavailable")
    declared = load_contract(DRAFT.read_text())
    installed = load_task_contract('finance.prepaid_amortization')
    # Revision v4 appends the outcome-only report line; schedule checks are unchanged.
    assert installed.checks[:len(declared.checks)] == declared.checks
    assert installed.credit == declared.credit and installed.bindings == declared.bindings
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    return declared


def assert_clean(trace):
    assert not trace.assessment_errors and not trace.credit_errors
    assert not [b for b in trace.assessment_batches if b.run.status in {"failed", "interrupted"}]


def outcomes(trace):
    result = {}
    for batch in trace.assessment_batches:
        if batch.run.status != "complete":
            continue
        for receipt in batch.run.execution_evidence:
            if receipt.kind == RETAINED_OUTPUT:
                payload = json.loads(receipt.payload_json)
                if payload["kind"] == "finding":
                    result[payload["check_id"], payload["candidate_identity"][-1]] = payload
    return result


def completions(trace):
    result = {}
    for assignment in trace.credit_assignments:
        if assignment.status != "complete":
            continue
        config = json.loads(assignment.request.rule.configuration_json)
        for part in assignment.contributions:
            if part.transformation == "retained_completion_identity@1":
                consumption = config["consumption"]
                key = consumption["check_id"], consumption["candidate_identity"][-1]
                assert key not in result, "one completion per stable obligation"
                assert part.value == 1 and part.recipient.kind == "execution"
                result[key] = part.recipient.execution.invocation_id
    return result


def simulated(saved, calls, *, initial=None, missing_ack=None):
    original = saved[-1]
    initial = copy.deepcopy(original.initial_state if initial is None else initial)
    material = run_operations(initial, calls)
    _, episode, trace = native_fixture(material, missing_ack=missing_ack)
    data = original.model_copy(update={"initial_state": initial, "assertions": ()})
    trace.task = vf.TraceTask(type="Task", data=data)
    cast(Any, episode).task = trace.task
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar
    assert_clean(trace)
    return task, episode, trace


def test_actual_hash_bound_luna_schedule_findings_recipients_reload_and_scalar(saved, draft):
    path, original_bytes, episode, trace, data = saved
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
    assert_clean(trace)
    assert trace.rewards == scalar
    found = outcomes(trace)
    assert len(found) == 15
    assert sum(f["status"] == "valid" for f in found.values()) == 3
    assert sum(f["status"] == "inapplicable" for f in found.values()) == 12
    assert found[INSURANCE, 2]["value"] == 1, found[INSURANCE, 2]["reason"]
    assert found[SOFTWARE, 3]["required"] is True and found[SOFTWARE, 3]["value"] == 0
    assert found[STANDARD, 6]["value"] == 1
    assert found[STANDARD, 4]["status"] == "inapplicable"
    assert found[STANDARD, 5]["status"] == "inapplicable"
    expected = {(INSURANCE, 2): INSURANCE_EXECUTION, (STANDARD, 6): HOSTING_EXECUTION}
    assert completions(trace) == expected
    assert not [part for part in penalties(trace) if part.value < 0]
    assignments = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert_clean(trace)
    assert tuple(trace.credit_assignments) == assignments and trace.rewards == scalar
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    assert tuple(replay.credit_assignments) == assignments
    asyncio.run(task.score(replay))
    assert_clean(replay)
    assert tuple(replay.credit_assignments) == assignments
    assert completions(replay) == expected and replay.rewards == scalar
    assert path.read_bytes() == original_bytes
    guard = [
        r
        for r in terminal_records(trace)
        if r.signal.signal_id == "finance.prepaid_ineligible_balance_recognition"
    ]
    assert guard and all(r.value == 0 for r in guard)
    print(
        "PREPAID_REPLAY",
        json.dumps(
            {
                "episode_sha256": RECORDED_SHA,
                "retained_findings": len(found),
                "required_true": 3,
                "retained_successes": 2,
                "retained_failures": 1,
                "inapplicable": 12,
                "guard_records_in_history_after_rescore": len(guard),
                "harm_contributions": 0,
                "completion_recipients": list(expected.values()),
                "rescore_reload_assignments_unchanged": True,
                "original_bytes_unchanged": True,
            }
        ),
    )


@pytest.mark.parametrize("split", [False, True])
def test_real_simulator_all_three_branches_combined_or_split(saved, draft, split):
    calls, expected = [], {}
    for row, check in ((2, INSURANCE), (3, SOFTWARE), (6, STANDARD)):
        if split:
            calls.extend(update(row, {key: value}) for key, value in CORRECT[row].items())
        else:
            calls.append(update(row, CORRECT[row]))
        expected[check, row] = f"execution-{len(calls) - 1}"
    _, _, trace = simulated(saved, calls)
    assert all(outcomes(trace)[key]["value"] == 1 for key in expected), outcomes(trace)
    assert completions(trace) == expected


@pytest.mark.parametrize(
    "tail,value,recipient",
    [
        ([{"Remaining": "$3,000"}], 0, None),
        ([{"Remaining": "$3,000"}, {"Remaining": "$3,300"}], 1, "execution-2"),
        ([CORRECT[6]], 1, "execution-0"),
        ([{"Notes": "Reviewed"}], 1, "execution-0"),
    ],
)
def test_damage_repair_noop_and_notes_have_distinct_completion(
    saved, draft, tail, value, recipient
):
    _, _, trace = simulated(saved, [update(6, CORRECT[6]), *(update(6, cells) for cells in tail)])
    assert outcomes(trace)[STANDARD, 6]["value"] == value
    assert completions(trace) == ({(STANDARD, 6): recipient} if recipient else {})


def test_changed_public_amounts_and_name_drive_derived_goal(saved, draft):
    initial = copy.deepcopy(saved[-1].initial_state)
    initial["google_sheets"]["rows"][4]["cells"].update(
        {"Item": "Different ordinary prepaid", "Total": "$4,800", "Remaining": "$4,800"}
    )
    _, _, wrong = simulated(saved, [update(6, CORRECT[6])], initial=initial)
    assert outcomes(wrong)[STANDARD, 6]["value"] == 0 and not completions(wrong)
    _, _, correct = simulated(
        saved, [update(6, {"Amortized to Date": "$400", "Remaining": "$4,400"})], initial=initial
    )
    assert outcomes(correct)[STANDARD, 6]["value"] == 1
    assert completions(correct) == {(STANDARD, 6): "execution-0"}


@pytest.mark.parametrize("case", ["insufficient-balance", "inconsistent-baseline", "rounding-orders", "rounding-tie"])
def test_unsupported_accounting_calculations_keep_required_goal_unavailable(saved, draft, case):
    initial = copy.deepcopy(saved[-1].initial_state)
    row, check = (2, INSURANCE) if case.startswith("rounding") else (6, STANDARD)
    cells = initial["google_sheets"]["rows"][0 if row == 2 else 4]["cells"]
    if case == "insufficient-balance":
        cells.update({"Total": "$3,600", "Amortized to Date": "$3,500", "Remaining": "$100"})
        update_cells = {"Amortized to Date": "$3,800", "Remaining": "-$200"}
    elif case == "inconsistent-baseline":
        cells.update({"Total": "$3,600", "Amortized to Date": "$0", "Remaining": "$3,300"})
        update_cells = CORRECT[6]
    else:
        total = "$12.04" if case == "rounding-orders" else "$12.06"
        cells.update({"Total": total, "Amortized to Date": "$0", "Remaining": total})
        update_cells = {"Amortized to Date": "$2.01", "Remaining": "$10.03" if case == "rounding-orders" else "$10.05"}
    _, _, trace = simulated(saved, [update(row, update_cells)], initial=initial)
    finding = outcomes(trace)[check, row]
    assert finding["required"] is True and finding["status"] == "abstained"
    assert finding["value"] is None
    assert finding["reason"] in {"retained_calculation_domain_unsupported", "retained_calculation_domain_unavailable"}
    assert not completions(trace)


@pytest.mark.parametrize("term", ["0", "-1", "1.5"])
def test_invalid_term_is_unknown_not_inapplicable_or_credited(saved, draft, term):
    initial = copy.deepcopy(saved[-1].initial_state)
    initial["google_sheets"]["rows"][4]["cells"]["Term (Months)"] = term
    _, _, trace = simulated(saved, [update(6, CORRECT[6])], initial=initial)
    finding = outcomes(trace)[STANDARD, 6]
    assert finding["status"] == "abstained" and finding["required"] is None
    assert finding["value"] is None and not completions(trace)


def test_non_first_of_month_is_outside_qualified_schedule_domain(saved, draft):
    initial = copy.deepcopy(saved[-1].initial_state)
    initial["google_sheets"]["rows"][4]["cells"]["Start Date"] = "2026-01-15"
    _, _, trace = simulated(saved, [update(6, CORRECT[6])], initial=initial)
    finding = outcomes(trace)[STANDARD, 6]
    assert finding["status"] == "abstained" and finding["value"] is None
    assert not completions(trace)


def test_public_policy_binding_tamper_cannot_publish_completion(saved, draft):
    initial = copy.deepcopy(saved[-1].initial_state)
    initial["gmail"]["messages"][0]["body_plain"] = "A different unreviewed amortization policy."
    _, _, trace = simulated(saved, [update(6, CORRECT[6])], initial=initial)
    assert all(finding["value"] is None for finding in outcomes(trace).values())
    assert not completions(trace) and not penalties(trace)


def test_copied_total_must_preserve_public_string_not_only_numeric_value(saved, draft):
    _, _, trace = simulated(saved, [update(6, {**CORRECT[6], "Total": "$3600"})])
    assert outcomes(trace)[STANDARD, 6]["value"] == 0
    assert not completions(trace)


@pytest.mark.parametrize("service", ["gmail", "slack"])
def test_added_competing_policy_preserves_original_bindings_but_invalidates_inventory(saved, draft, service):
    initial = copy.deepcopy(saved[-1].initial_state)
    message = copy.deepcopy(initial[service]["messages"][0])
    message["id"] = "new-competing-policy"
    if service == "gmail":
        message["date"] = "2026-02-01T12:00:00Z"
        message["body_plain"] = "Updated controller policy: do not recognize amortization this month."
    else:
        message["ts"] = "1769947200.000000"
        message["text"] = "Superseding policy: postpone all prepaid recognition."
    initial[service]["messages"].append(message)
    _, _, trace = simulated(saved, [update(6, CORRECT[6])], initial=initial)
    assert all(finding["value"] is None for finding in outcomes(trace).values())
    assert not completions(trace) and not penalties(trace)


def test_ambiguous_cent_rounding_is_unavailable_without_invented_tie_rule(saved, draft):
    initial = copy.deepcopy(saved[-1].initial_state)
    initial["google_sheets"]["rows"][4]["cells"].update(
        {"Total": "$1", "Remaining": "$1", "Term (Months)": "8"}
    )
    _, _, trace = simulated(
        saved, [update(6, {"Amortized to Date": "$0.12", "Remaining": "$0.88"})], initial=initial
    )
    assert outcomes(trace)[STANDARD, 6]["status"] == "abstained"
    assert not completions(trace)


@pytest.mark.parametrize("missing_ack,recipient", [(0, None), (1, "execution-0")])
def test_missing_update_ack_withholds_credit_but_later_notes_gap_does_not(
    saved, draft, missing_ack, recipient
):
    _, _, trace = simulated(
        saved, [update(6, CORRECT[6]), update(6, {"Notes": "Reviewed"})], missing_ack=missing_ack
    )
    # Public prepaid rows omit generated native IDs. Losing the first ACK also
    # removes the initial identity bridge; later retained data cannot invent it.
    expected_value = None if missing_ack == 0 else 1
    assert outcomes(trace)[STANDARD, 6]["value"] == expected_value
    assert completions(trace) == ({(STANDARD, 6): recipient} if recipient else {})


def test_ineligible_recognition_repair_keeps_harm_without_completion(saved, draft):
    _, _, trace = simulated(
        saved, [update(4, {"Amortized to Date": "$750"}), update(4, {"Amortized to Date": "$0"})]
    )
    harm = [part for part in penalties(trace) if part.value < 0]
    assert len(harm) == 1 and harm[0].recipient.execution.invocation_id == "execution-0"
    assert not completions(trace)


def test_moved_midmonth_future_item_keeps_known_harm_despite_scope_gap(saved, draft):
    initial = copy.deepcopy(saved[-1].initial_state)
    initial["google_sheets"]["rows"][2]["cells"]["Start Date"] = "2026-04-15"

    def move(world):
        world.google_sheets.rows[2].row_id = 8
        return {"moved": True}

    _, _, trace = simulated(
        saved,
        [("custom_move_fixture", {}, move), update(8, {"Amortized to Date": "$750"})],
        initial=initial,
    )
    harm = [part for part in penalties(trace) if part.value < 0]
    assert len(harm) == 1 and harm[0].recipient.execution.invocation_id == "execution-1"
    assert not completions(trace)
    # Known harm proves noncompliance even when the custom move leaves other
    # action inventory incomplete; that gap must not erase the positive witness.
    assert any(
        r.value == 0
        for r in terminal_records(trace)
        if r.signal.signal_id == "finance.prepaid_ineligible_balance_recognition.compliance"
    )
