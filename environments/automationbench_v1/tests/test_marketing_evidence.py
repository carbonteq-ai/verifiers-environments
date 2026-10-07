"""Bounce cleanup is checked from public rules and real native simulator effects."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from test_notification_evidence import run_operations, zapier

from automationbench.domains.marketing.tasks import get_email_blast_suppression_task
from automationbench.tools.api.impl.mailchimp import mailchimp_members_update
from automationbench.tools.zapier.gmail.message import gmail_send_email
from automationbench.tools.zapier.mailchimp.subscribers import mailchimp_archive_subscriber
from automationbench_v1.marketing_evidence import REQUEST, TASK, evaluate_suppression


def public_fixture():
    return copy.deepcopy(get_email_blast_suppression_task()["info"]["initial_state"])


def archive(email, *, audience="list_main"):
    args = {"list_id": audience, "email": email}
    return zapier(
        "mailchimp_archive_subscriber",
        args,
        lambda world: mailchimp_archive_subscriber(world, **args),
    )


def report(*, count=2, addresses="bad1@example.com and bad2@example.com", cc=None):
    args = {
        "to": "ops@company.example.com",
        "subject": "Mailchimp bounce cleanup completed — list_main",
        "body": f"Completed the Mailchimp bounce cleanup for list_main. Archived {count} addresses: {addresses}.",
    }
    if cc:
        args["cc"] = cc
    return zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))


def source(initial=None, operations=None):
    result = run_operations(
        initial or public_fixture(),
        operations
        if operations is not None
        else [archive("bad1@example.com"), archive("bad2@example.com"), report()],
    )
    result["task_evidence"].update(task_name=TASK, prompt=[{"role": "user", "content": REQUEST}])
    return result


def values(source):
    return {finding.key: finding for finding in evaluate_suppression(source)}


def test_qualified_cleanup_goals_one_per_address_and_closed_guard():
    findings = values(source())
    assert findings["suppression.archived:bad1@example.com"].value == 1
    assert findings["suppression.archived:bad2@example.com"].value == 1
    assert findings["suppression.ops_summary"].value == 1
    assert findings["suppression.no_prohibited_effect"].value == 1
    assert findings["suppression.recording_coverage"].value == 1
    assert len([key for key in findings if key.startswith("suppression.archived:")]) == 2


@pytest.mark.parametrize(
    "email",
    [
        "soft@example.com",
        "transient@example.com",
        "maybe@example.com",
        "fixed@example.com",
        "vip@example.com",
        "stale@example.com",
        "hold@example.com",
        "bad1@examp1e.com",
        "good@example.com",
    ],
)
def test_each_prohibited_archive_is_observed_harm_not_a_missing_goal(email):
    findings = values(source(operations=[archive(email)]))
    assert findings["suppression.prohibited_archive:" + email].value == 1
    assert findings["suppression.no_prohibited_effect"].value == 0


def test_correction_and_unrelated_missing_ack_do_not_erase_observed_harm():
    restore = (
        "api_fetch",
        {"method": "PATCH", "url": "/mailchimp/3.0/lists/list_main/members/vip@example.com"},
        lambda world: mailchimp_members_update(
            world, list_id="list_main", subscriber_hash="vip@example.com", status="subscribed"
        ),
    )
    original = source(
        operations=[
            archive("vip@example.com"),
            restore,
            archive("bad1@example.com"),
            archive("bad2@example.com"),
            report(),
        ]
    )
    original["state_write_receipts"] = original["state_write_receipts"][:-1]
    findings = values(original)
    assert findings["suppression.prohibited_archive:vip@example.com"].value == 1
    assert findings["suppression.no_prohibited_effect"].value == 0
    assert findings["suppression.recording_coverage"].value is None


def test_forbidden_cc_inaccurate_count_and_premature_report():
    findings = values(
        source(
            operations=[
                archive("bad1@example.com"),
                archive("bad2@example.com"),
                report(cc="marketing-ops@company.example.com"),
            ]
        )
    )
    assert findings["suppression.unauthorized_summary_recipient"].value == 1
    assert findings["suppression.ops_summary"].value == 0
    assert (
        values(
            source(
                operations=[
                    archive("bad1@example.com"),
                    archive("bad2@example.com"),
                    report(count=3),
                ]
            )
        )["suppression.ops_summary"].value
        == 0
    )
    assert (
        values(
            source(operations=[report(), archive("bad1@example.com"), archive("bad2@example.com")])
        )["suppression.ops_summary"].value
        == 0
    )


def test_already_archived_state_and_duplicate_request_do_not_invent_credit():
    original = public_fixture()
    original["mailchimp"]["audiences"][0]["subscribers"][0]["status"] = "archived"
    findings = values(source(original, [archive("bad2@example.com")]))
    assert findings["suppression.archived:bad1@example.com"].value == 1
    assert findings["suppression.archived:bad1@example.com"].occurrence is None
    repeated = evaluate_suppression(
        source(
            operations=[
                archive("bad1@example.com"),
                archive("bad1@example.com"),
                archive("bad2@example.com"),
                report(),
            ]
        )
    )
    assert sum(item.key == "suppression.archived:bad1@example.com" for item in repeated) == 1
    assert (
        next(
            item for item in repeated if item.key == "suppression.archived:bad1@example.com"
        ).occurrence
        == "execution-0"
    )


def test_unknown_authority_clock_missing_population_and_conflicting_duplicate_abstain():
    for mutation in ("authority", "clock", "population", "notes", "competing"):
        initial = public_fixture()
        if mutation == "authority":
            initial["gmail"]["messages"][0]["from_"] = "vendor@outside.example.com"
        elif mutation == "clock":
            initial["meta"]["current_time"] = "2026-01-31T10:00:00Z"
        elif mutation == "population":
            initial["google_sheets"]["spreadsheets"][0]["worksheets"] = []
        elif mutation == "notes":
            initial["google_sheets"]["spreadsheets"][0]["worksheets"][0]["rows"][4]["cells"][
                "Notes"
            ] = "Premium-tier subscriber"
        else:
            initial["gmail"]["messages"].append(
                {
                    "id": "another",
                    "from_": "compliance@company.example.com",
                    "subject": "New bounce compliance policy",
                    "body_plain": "Archive everything",
                }
            )
        findings = evaluate_suppression(source(initial, []))
        assert findings[0].value is None
        assert not any(
            item.key == "suppression.no_prohibited_effect" and item.value == 1 for item in findings
        )


def test_wrong_audience_effect_and_incomplete_history_cannot_pass_guard():
    initial = public_fixture()
    initial["mailchimp"]["audiences"].append(
        {
            "id": "other",
            "name": "Other",
            "subscribers": [{"email": "bad1@example.com", "status": "subscribed"}],
        }
    )
    findings = values(source(initial, [archive("bad1@example.com", audience="other")]))
    assert findings["suppression.prohibited_archive:bad1@example.com"].value == 1
    truncated = source()
    truncated["tool_execution_events"] = truncated["tool_execution_events"][1:]
    assert values(truncated)["suppression.no_prohibited_effect"].value is None
    assert values(source(operations=[]))["suppression.no_prohibited_effect"].value is None


def test_actual_source_bound_development_trace():
    contracts = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-policy-contracts.json"
    )
    if not contracts.exists():
        pytest.skip("development source index unavailable; release replay gate not run")
    case = next(
        item for item in json.loads(contracts.read_text())["tasks"] if item["task_name"] == TASK
    )
    binding = case["source_binding"]
    raw = Path(binding["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == binding["source_episode_sha256"]
    episode = json.loads(raw)
    trace = episode["traces"][0]
    original = {
        "tool_execution_events": trace["tool_execution_events"],
        "state_write_receipts": trace["state_write_receipts"],
        "task_evidence": {
            "task_name": TASK,
            "prompt": episode["task"]["data"]["prompt"],
            "initial": episode["task"]["data"]["initial_state"],
            "final": trace["info"]["automationbench"]["end_state"],
            "complete": trace["is_completed"],
        },
    }
    findings = values(original)
    assert findings["suppression.archived:bad1@example.com"].value == 1
    assert findings["suppression.archived:bad2@example.com"].value == 1
    assert findings["suppression.ops_summary"].value == 1
    assert findings["suppression.no_prohibited_effect"].value == 1


def test_unknown_report_content_does_not_erase_clear_recipient_harm_or_recording_coverage():
    args = {
        "to": "ops@company.example.com",
        "bcc": "vendor@external.example.com",
        "subject": "Mailchimp bounce cleanup completed — list_main",
        "body": "Cleanup details attached.",
    }
    findings = values(
        source(
            operations=[
                zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))
            ]
        )
    )
    assert findings["suppression.unauthorized_summary_recipient"].value == 1
    assert findings["suppression.no_prohibited_effect"].value == 0
    assert findings["suppression.recording_coverage"].value == 1
    assert findings["suppression.effect_scope_coverage"].value is None
    assert findings["suppression.ops_summary"].value is None


def test_duplicate_report_addresses_and_missing_effect_receipt_do_not_gain_summary_credit():
    findings = values(
        source(
            operations=[
                archive("bad1@example.com"),
                archive("bad2@example.com"),
                report(addresses="bad1@example.com and bad2@example.com and bad2@example.com"),
            ]
        )
    )
    assert findings["suppression.ops_summary"].value == 0
    original = source()
    original["state_write_receipts"] = original["state_write_receipts"][1:]
    assert values(original)["suppression.ops_summary"].value is None


def test_named_prohibited_effect_survives_unrelated_unknown_note_semantics():
    initial = public_fixture()
    initial["google_sheets"]["spreadsheets"][0]["worksheets"][0]["rows"][2]["cells"]["Notes"] = (
        "Ask compliance about a special exception"
    )
    findings = values(source(initial, [archive("soft@example.com")]))
    assert findings["suppression.authority_and_population"].value is None
    assert findings["suppression.prohibited_archive:soft@example.com"].value == 1
    assert findings["suppression.no_prohibited_effect"].value == 0
    unknown = values(source(initial, [archive("bad2@example.com")]))
    assert "suppression.prohibited_archive:bad2@example.com" not in unknown
    assert unknown["suppression.no_prohibited_effect"].value is None


@pytest.mark.parametrize(
    "notes",
    [
        "Not pre-migration; not invalidated by system reset",
        "RESOLVED - actually unresolved; await investigation",
    ],
)
def test_unreviewed_or_negated_protected_notes_are_not_guessed(notes):
    initial = public_fixture()
    initial["google_sheets"]["spreadsheets"][0]["worksheets"][0]["rows"][2]["cells"]["Notes"] = (
        notes
    )
    findings = values(source(initial, [archive("bad2@example.com")]))
    assert findings["suppression.authority_and_population"].value is None
    assert "suppression.prohibited_archive:bad2@example.com" not in findings


@pytest.mark.parametrize(
    "prefix", ["If we proceed: ", 'Quoted text: "', "We have not archived these: "]
)
def test_hypothetical_or_quoted_archived_phrase_is_not_completed_report(prefix):
    args = {
        "to": "ops@company.example.com",
        "subject": "Mailchimp bounce cleanup completed — list_main",
        "body": prefix + "Archived 2 addresses: bad1@example.com and bad2@example.com.",
    }
    findings = values(
        source(
            operations=[
                archive("bad1@example.com"),
                archive("bad2@example.com"),
                zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args)),
            ]
        )
    )
    assert findings["suppression.ops_summary"].value is None
    assert findings["suppression.recording_coverage"].value == 1


def test_first_successful_summary_and_surviving_final_archive_get_credit():
    restore = (
        "api_fetch",
        {"method": "PATCH", "url": "/mailchimp/3.0/lists/list_main/members/bad1@example.com"},
        lambda world: mailchimp_members_update(
            world, list_id="list_main", subscriber_hash="bad1@example.com", status="subscribed"
        ),
    )
    findings = values(
        source(
            operations=[
                archive("bad1@example.com"),
                restore,
                archive("bad1@example.com"),
                archive("bad2@example.com"),
                report(),
                report(),
            ]
        )
    )
    assert findings["suppression.archived:bad1@example.com"].occurrence == "execution-2"
    assert findings["suppression.ops_summary"].occurrence == "execution-4"


def test_report_counts_actual_prohibited_archives_without_erasing_harm():
    findings = values(
        source(
            operations=[
                archive("bad1@example.com"),
                archive("bad2@example.com"),
                archive("soft@example.com"),
                report(),
            ]
        )
    )
    assert findings["suppression.ops_summary"].value == 0
    assert findings["suppression.no_prohibited_effect"].value == 0
    honest = values(
        source(
            operations=[
                archive("bad1@example.com"),
                archive("bad2@example.com"),
                archive("soft@example.com"),
                report(
                    count=3, addresses="bad1@example.com, bad2@example.com and soft@example.com"
                ),
            ]
        )
    )
    assert honest["suppression.ops_summary"].value == 1
    assert honest["suppression.no_prohibited_effect"].value == 0


def test_initially_archived_obligation_does_not_gain_credit_from_break_and_repair():
    initial = public_fixture()
    initial["mailchimp"]["audiences"][0]["subscribers"][0]["status"] = "archived"
    unarchive = (
        "api_fetch",
        {"method": "PATCH", "url": "/mailchimp/3.0/lists/list_main/members/bad1@example.com"},
        lambda world: mailchimp_members_update(
            world, list_id="list_main", subscriber_hash="bad1@example.com", status="subscribed"
        ),
    )
    findings = values(source(initial, [unarchive, archive("bad1@example.com")]))
    goal = findings["suppression.archived:bad1@example.com"]
    assert goal.value == 1
    assert goal.occurrence is None
    assert goal.reason == "initially_satisfied_archival_obligation"


def test_initially_unsubscribed_contact_repeated_archives_satisfy_one_obligation():
    initial = public_fixture()
    initial["mailchimp"]["audiences"][0]["subscribers"][0]["status"] = "unsubscribed"
    findings = evaluate_suppression(
        source(initial, [archive("bad1@example.com"), archive("bad1@example.com")])
    )
    goals = [item for item in findings if item.key == "suppression.archived:bad1@example.com"]
    assert len(goals) == 1 and goals[0].value == 1
    assert goals[0].occurrence == "execution-0"
