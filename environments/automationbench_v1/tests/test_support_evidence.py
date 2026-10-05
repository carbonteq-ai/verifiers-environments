"""Actual retained evidence and fresh executed simulator counterexamples.

Fresh local-tool fixtures construct explicit acknowledged transition inputs;
they exercise domain extraction, not native transport qualification. Retained
tests instead consume actual native receipts through world_transitions.
"""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf

from automationbench.domains.support.tasks import (
    get_support_gorgias_refund_processing_task,
    get_support_hiver_slack_digest_task,
)
from automationbench.schema.world import WorldState
from automationbench_v1.capture import (
    CapturedAction,
    SnapshotStore,
    canonical_json,
    collect_local_evidence,
)
from automationbench_v1.effect_evidence import WorldTransition, world_transitions
from automationbench_v1.effect_index import EffectIndex
from automationbench_v1.notification_evidence import sheet_rows
from automationbench_v1.support_evidence import (
    digest_log_claims,
    jira_creation_coverage,
    jira_creations,
)
from automationbench_v1.support_rules import (
    DigestClaimContract,
    ReviewObligation,
    ReviewPurposeForm,
    escalation_accomplishments,
    join_refund_order,
)
from automationbench_v1.tools import AutomationBenchState, AutomationBenchToolset


def _contract():
    # Authored bounded test contract, not accepted full-task policy.
    return DigestClaimContract(
        "reviewed_test_contract_v1",
        "DIGEST-20260210",
        "2026-02-10",
        (
            ("infrastructure", "ops-lead@company.example.com"),
            ("billing", "finance@company.example.com"),
        ),
        ("Email sent to {recipient}", "email_sent"),
        ("Pending",),
        ("Support digest — {date} — {category}",),
    )


class Fresh:
    def __init__(self, factory, *, jira_projects=None):
        initial = factory()["info"]["initial_state"]
        if jira_projects is not None:
            # Declared positive-test authority, not inferred from the task text
            # or hydrated from historical project/audit records.
            initial.setdefault("jira", {})["projects"] = jira_projects
        self.state = AutomationBenchState(
            world=WorldState.model_validate(initial).model_dump(mode="json"), capture_actions=True
        )
        self.tools = AutomationBenchToolset(vf.ToolsetConfig())
        self.tools._inert_state = self.state
        self.envelopes = []

    def run(self, name, **arguments):
        with collect_local_evidence() as envelopes:
            try:
                self.tools.execute_tool(name, json.dumps(arguments))
            finally:
                self.envelopes.extend(envelopes)

    def index(self):
        store = SnapshotStore(self.envelopes)
        actions = [CapturedAction.model_validate(item["action"]) for item in self.envelopes]
        return EffectIndex(
            tuple(
                WorldTransition(
                    "tool_server",
                    "fresh_" + str(i),
                    action,
                    store.text(action.before_digest),
                    store.text(action.after_digest),
                    "acknowledged",
                    "controlled_fixture_ack",
                    i,
                    i + 1,
                )
                for i, action in enumerate(actions)
            )
        )


def _send(
    fresh,
    *,
    tool="gmail_send_email",
    recipient="ops-lead@company.example.com",
    date="2026-02-10",
    category="Infrastructure",
):
    fresh.run(
        tool, to=recipient, subject=f"Support digest — {date} — {category}", body="Today's digest"
    )


def _log(fresh, action="Email sent to ops-lead@company.example.com"):
    fresh.run(
        "google_sheets_append_row",
        spreadsheet="ss_digest",
        worksheet="ws_digest_log",
        values=["2026-02-10", "infrastructure", 3, action],
    )


def _obligation(world):
    tickets = world["gorgias"]["tickets"]
    ticket = next(
        ticket for ticket in tickets if ticket["customer"]["email"] == "carlos@example.com"
    )
    order = join_refund_order(ticket, sheet_rows(world, "ss_refund_policy", "ws_orders"))
    assert order is not None
    return ReviewObligation(
        order,
        "repeat_refunder",
        "2026-02-01",
        (
            ReviewPurposeForm("Review order {order}", "{customer_email} {amount} repeat refunder"),
            ReviewPurposeForm(
                "Manual refund review: order {order}",
                "Refund request from {customer_name} ({customer_email}) for order {order}. Amount: {amount}. Repeat refunder; escalate for finance review.",
            ),
            ReviewPurposeForm(
                "Manual repeat-refunder review: order {order}",
                "Refund request from {customer_name} ({customer_email}) for order {order}. Amount: {amount}. Customer is on the repeat refunder list; finance review required.",
            ),
        ),
        "reviewed_test_public_policy_v1",
    )


def test_fresh_two_native_jira_creations_are_two_effects_and_one_accomplishment():
    fresh = Fresh(
        get_support_gorgias_refund_processing_task,
        jira_projects=[{"id": "finance", "key": "FIN", "name": "Finance"}],
    )
    obligation = _obligation(fresh.state.world)
    params = {
        "project": "FIN",
        "issuetype": "Task",
        "summary": "Review order 4508",
        "description": "carlos@example.com $250.00 repeat refunder",
    }
    fresh.run("jira_create_issue", **params)
    fresh.run("jira_create_issue", **params)
    index = fresh.index()
    effects = jira_creations(index)
    assert len(effects) == 2 and len({effect.record_id for effect in effects}) == 2
    jira = cast(dict[str, Any], fresh.state.world["jira"])
    assert {effect.record_id for effect in effects} == {
        audit["id"] for audit in jira["actions"]["create_issue"]
    }
    issues = jira["issues"]
    assert len(issues) == 2
    assert {issue["id"] for issue in issues}.isdisjoint(effect.record_id for effect in effects)
    assert {issue["creation_action_id"] for issue in issues} == {
        effect.record_id for effect in effects
    }
    assert jira_creation_coverage(index, effects)
    result = escalation_accomplishments(effects, (obligation,), ordered_coverage=True)[0]
    assert result.finding.value == 1 and result.finding.occurrence == "fresh_0"
    assert len(result.effects) == 2


def test_preexisting_failed_and_unacknowledged_jira_have_no_new_credit():
    fresh = Fresh(
        get_support_gorgias_refund_processing_task,
        jira_projects=[{"id": "finance", "key": "FIN", "name": "Finance"}],
    )
    fresh.run(
        "jira_create_issue",
        project="FIN",
        issuetype="Task",
        summary="Review order 4508",
        description="carlos@example.com $250.00 repeat refunder",
    )
    first = fresh.index().occurrences[0]
    assert first.action is not None
    assert (
        jira_creations(
            EffectIndex((replace(first, evidence_status="unavailable", reason="missing_ack"),))
        )
        == ()
    )
    assert (
        jira_creations(
            EffectIndex(
                (replace(first, action=first.action.model_copy(update={"status": "raised"})),)
            )
        )
        == ()
    )
    same_world = replace(
        first,
        before_json=first.after_json,
        action=first.action.model_copy(update={"before_digest": first.action.after_digest}),
    )
    assert jira_creations(EffectIndex((same_world,))) == ()
    unknown_result = replace(first, action=first.action.model_copy(update={"result_json": None}))
    index = EffectIndex((unknown_result,))
    assert jira_creations(index) == () and not jira_creation_coverage(index, ())


def test_undeclared_project_failure_is_not_synthetic_jira_creation():
    # Explicitly manufacture missing authority; the repaired public fixture now
    # declares the FIN destination required by its request.
    fresh = Fresh(get_support_gorgias_refund_processing_task, jira_projects=[])
    assert cast(dict[str, Any], fresh.state.world["jira"])["projects"] == []
    fresh.run("jira_create_issue", project="FIN", issuetype="Task", summary="Review")
    index = fresh.index()
    action = index.occurrences[0].action
    assert action is not None and action.result_json is not None
    payload = json.loads(json.loads(action.result_json))
    assert payload["success"] is False and payload["error"] == "jira_project_not_found"
    jira = cast(dict[str, Any], fresh.state.world["jira"])
    assert not jira["issues"]
    assert not jira["actions"].get("create_issue")
    assert jira_creations(index) == ()
    unknown = replace(index.occurrences[0], action=action.model_copy(update={"result_json": None}))
    assert not jira_creation_coverage(EffectIndex((unknown,)), ())


@pytest.mark.parametrize(
    "change",
    [
        "missing_issue",
        "wrong_persisted_summary",
        "missing_audit_link",
        "wrong_audit_link",
        "wrong_issue_id",
        "old_response_with_new_issue",
    ],
)
def test_current_jira_response_or_state_gaps_cannot_downgrade_to_legacy_action_proof(change):
    fresh = Fresh(
        get_support_gorgias_refund_processing_task,
        jira_projects=[{"id": "finance", "key": "FIN", "name": "Finance"}],
    )
    fresh.run(
        "jira_create_issue",
        project="FIN",
        issuetype="Task",
        summary="Review",
        description="A declared fixture",
    )
    item = fresh.index().occurrences[0]
    assert (
        item.action is not None
        and item.action.result_json is not None
        and item.after_json is not None
    )
    assert len(jira_creations(EffectIndex((item,)))) == 1
    result = json.loads(json.loads(item.action.result_json))
    after = json.loads(item.after_json)
    if change == "missing_issue":
        after["jira"]["issues"] = []
    elif change == "wrong_persisted_summary":
        after["jira"]["issues"][0]["fields"]["summary"] = "Different"
    elif change == "missing_audit_link":
        result["results"][0].pop("action_record_id")
    elif change == "wrong_audit_link":
        result["results"][0]["action_record_id"] = "foreign-audit"
    elif change == "wrong_issue_id":
        result["results"][0]["id"] = result["results"][0]["action_record_id"]
    else:
        audit = after["jira"]["actions"]["create_issue"][0]
        result["results"][0] = {"id": audit["id"], **audit["params"]}
    encoded = canonical_json(after)
    action = item.action.model_copy(
        update={
            "after_digest": hashlib.sha256(encoded.encode()).hexdigest(),
            "result_json": canonical_json(json.dumps(result)),
        }
    )
    changed = EffectIndex((replace(item, action=action, after_json=encoded),))
    assert jira_creations(changed) == ()
    assert not jira_creation_coverage(changed, ())


def test_fresh_send_before_log_and_pending_then_sent():
    fresh = Fresh(get_support_hiver_slack_digest_task)
    _log(fresh, "Pending")
    _send(fresh)
    _log(fresh)
    claims = digest_log_claims(fresh.index(), _contract())
    assert claims[0].finding.value is None and claims[0].finding.reason == "not_a_completed_claim"
    assert claims[1].finding.value == 0 and claims[1].matching_send_ids == ("fresh_1",)


def test_fresh_log_before_send_stays_premature_after_late_extension():
    fresh = Fresh(get_support_hiver_slack_digest_task)
    _log(fresh)
    prefix = digest_log_claims(fresh.index(), _contract())
    assert prefix[0].finding.value == 1
    _send(fresh)
    assert digest_log_claims(fresh.index(), _contract())[0] == prefix[0]


@pytest.mark.parametrize(
    "change", ["recipient", "date", "category", "draft", "missing_ack", "pending", "failed"]
)
def test_nonmatching_draft_failed_and_missing_prior_evidence(change):
    fresh = Fresh(get_support_hiver_slack_digest_task)
    _send(
        fresh,
        recipient="other@example.com" if change == "recipient" else "ops-lead@company.example.com",
        date="2026-02-11" if change == "date" else "2026-02-10",
        category="Billing" if change == "category" else "Infrastructure",
        tool="gmail_create_draft" if change == "draft" else "gmail_send_email",
    )
    _log(fresh)
    index = fresh.index()
    if change in {"missing_ack", "pending", "failed"}:
        first = index.occurrences[0]
        assert first.action is not None
        if change == "failed":
            first = replace(first, action=first.action.model_copy(update={"status": "raised"}))
        else:
            first = replace(first, evidence_status="unavailable", reason=change)
        index = EffectIndex((first, index.occurrences[1]))
    finding = digest_log_claims(index, _contract())[0].finding
    assert finding.value == (None if change in {"missing_ack", "pending", "failed"} else 1.0)


def test_missing_authority_and_unsupported_claim_are_named_unavailable():
    fresh = Fresh(get_support_hiver_slack_digest_task)
    _log(fresh)
    assert (
        digest_log_claims(fresh.index(), None)[0].finding.reason
        == "completed_claim_authority_unavailable"
    )
    assert (
        digest_log_claims(fresh.index(), replace(_contract(), subject_forms=()))[0].finding.value
        is None
    )
    unsupported = Fresh(get_support_hiver_slack_digest_task)
    _log(unsupported, "Maybe we notified ops")
    assert (
        digest_log_claims(unsupported.index(), _contract())[0].finding.reason
        == "completed_claim_literal_unavailable"
    )


def test_executed_failed_send_then_completed_claim_has_no_delivery_evidence():
    fresh = Fresh(get_support_hiver_slack_digest_task)
    with pytest.raises(TypeError, match="body"):
        fresh.run(
            "gmail_send_email",
            to="ops-lead@company.example.com",
            subject="Support digest — 2026-02-10 — Infrastructure",
        )
    assert fresh.envelopes[0]["action"]["status"] == "raised"
    _log(fresh)
    assert digest_log_claims(fresh.index(), _contract())[0].finding.value == 1


def test_two_matching_sends_are_not_arbitrarily_joined_to_one_claim():
    fresh = Fresh(get_support_hiver_slack_digest_task)
    _send(fresh)
    _send(fresh)
    _log(fresh)
    claim = digest_log_claims(fresh.index(), _contract())[0]
    assert claim.finding.value is None and claim.finding.reason == "matching_prior_send_ambiguous"
    assert claim.matching_send_ids == ("fresh_0", "fresh_1")


def test_missing_log_ack_retains_explicit_unavailable_claim():
    fresh = Fresh(get_support_hiver_slack_digest_task)
    _log(fresh)
    item = replace(
        fresh.index().occurrences[0],
        evidence_status="unavailable",
        reason="missing_ack",
        expected_revision=None,
        applied_revision=None,
    )
    claims = digest_log_claims(EffectIndex((item,)), _contract())
    assert len(claims) == 1 and claims[0].finding.value is None
    assert claims[0].finding.reason == "log_write_acknowledgement_unavailable"


def test_revision_zero_claim_does_not_change_when_unknown_later_capture_is_added():
    fresh = Fresh(get_support_hiver_slack_digest_task)
    _log(fresh)
    index = fresh.index()
    original = digest_log_claims(index, _contract())[0]
    unknown = WorldTransition(
        "tool_server",
        "later_unknown",
        None,
        None,
        None,
        "unavailable",
        "world_capture_missing",
        None,
        None,
    )
    extended = EffectIndex((*index.occurrences, unknown))
    assert original.finding.value == 1
    assert digest_log_claims(extended, _contract())[0] == original


def test_sent_label_on_a_native_draft_cannot_back_completed_send_claim():
    fresh = Fresh(get_support_hiver_slack_digest_task)
    fresh.run(
        "gmail_create_draft",
        to="ops-lead@company.example.com",
        subject="Support digest — 2026-02-10 — Infrastructure",
        body="Digest",
        label_ids="SENT",
    )
    _log(fresh)
    assert digest_log_claims(fresh.index(), _contract())[0].finding.value == 1


def _retained(attempt, digest):
    path = (
        Path(
            "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01/remaining700/timed"
        )
        / attempt
        / "episode.json"
    )
    if not path.exists():
        pytest.skip("retained development trace unavailable")
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest
    return EffectIndex(world_transitions(json.loads(data)["traces"][0]))


def test_actual_gorgias_distinct_record_ids_one_carlos_obligation():
    index = _retained(
        "2878a0c3de63445213dd815588dd2f3cecb8b1bc706d8938a1b67c7fa6f93f1b",
        "5ee086c5ab9f98fab677154c2e583f77b2a6325087ba6b325d39023f3b244adb",
    )
    effects = jira_creations(index)
    assert len(effects) == 4 and jira_creation_coverage(index, effects)
    # This archived simulator version created audit actions only. The adapter
    # preserves that historical evidence without inventing canonical issues.
    for item in index.occurrences:
        if item.invocation_id not in {effect.invocation_id for effect in effects}:
            continue
        assert item.before_json is not None and item.after_json is not None
        assert index.world(item.before_json)["jira"].get("issues") == index.world(item.after_json)[
            "jira"
        ].get("issues")
    initial = index.serial_chain().ordered[0].before_json
    assert initial is not None
    obligation = _obligation(index.world(initial))
    result = escalation_accomplishments(effects, (obligation,), ordered_coverage=True)[0]
    assert len(result.effects) == 2 and result.finding.value == 1
    assert [effect.expected_revision for effect in result.effects] == [9, 29]


def test_actual_hiver_two_logs_precede_sends_with_explicit_reviewed_meanings():
    index = _retained(
        "1089adbdb940956d19a1fee792e3a1f5fa45368fb52fb6a75a7db009b3c544f2",
        "9f6f6d5f35cbc4f0f2c4d3f3b6a5d88bc5c86b5af7bbedd5812ddac48ed406e6",
    )
    claims = digest_log_claims(index, _contract())
    assert [claim.finding.value for claim in claims] == [1, 1, None]
    assert [claim.expected_revision for claim in claims[:2]] == [9, 10]
    assert all(claim.finding.value is None for claim in digest_log_claims(index, None))
