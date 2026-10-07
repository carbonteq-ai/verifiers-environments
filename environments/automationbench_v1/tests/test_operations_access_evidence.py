import copy
import hashlib
import json
from pathlib import Path

import pytest
from test_asana_evidence import task_and_section
from test_notification_evidence import run_operations, zapier

from automationbench.domains.operations.tasks import get_ops_access_request_validation_task
from automationbench.tools.zapier.gmail.message import gmail_send_email
from automationbench.tools.zapier.google_sheets.row import google_sheets_update_row
from automationbench_v1.operations_access_evidence import (
    REQUEST,
    TASK,
    evaluate_access,
    public_access,
)


def fixture():
    return copy.deepcopy(get_ops_access_request_validation_task()["info"]["initial_state"])


def source(operations, initial=None):
    data = run_operations(initial or fixture(), operations)
    data["task_evidence"].update(task_name=TASK, prompt=[{"role": "user", "content": REQUEST}])
    return data


def result(data):
    return {item.key: item for item in evaluate_access(data)}


def provisioning(
    email="jordan.lee@company.example.com",
    name="Jordan Lee",
    department="Engineering",
    level="Admin",
    section="sec_prov",
):
    notes = f"Requestor: {name}\nEmail: {email}\nDepartment: {department}\nRequested Level: {level}"
    return task_and_section(notes=notes, section=section)


def denial(email="j.lee@company.example.com", body=None):
    body = (
        body
        or "Jordan Lee: Standard access for Marketing denied. Tom Richards (Marketing Coordinator) does not meet Manager or above."
    )
    args = {"to": email, "subject": "Access request decision", "body": body}
    return zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))


def test_initial_join_disambiguates_names_and_closed_manager_policy():
    requests, _ = public_access(fixture())
    assert [request.approved for request in requests] == [True, False, False, True, True, True]
    assert len({(request.email, request.department) for request in requests}) == 6


def test_creation_is_useful_prerequisite_but_section_is_separate_required_goal():
    data = result(source(provisioning()[:1]))
    assert data["access.create:jordan.lee@company.example.com"].value == 1
    assert data["access.section:jordan.lee@company.example.com"].value == 0
    full = result(source(provisioning()))
    assert full["access.section:jordan.lee@company.example.com"].value == 1
    assert full["access.section:jordan.lee@company.example.com"].occurrence == "execution-1"
    wrong = result(source(provisioning(section="sec_wrong")))
    assert wrong["access.section:jordan.lee@company.example.com"].value == 0


def test_denial_uses_email_department_and_supported_seniority_reason():
    data = result(source([denial()]))
    assert data["access.denial:j.lee@company.example.com"].value == 1
    assert data["access.create:jordan.lee@company.example.com"].value == 0
    unknown = result(source([denial(body="You are denied, thanks.")]))
    assert unknown["access.denial:j.lee@company.example.com"].value is None


@pytest.mark.parametrize(
    "email,name,department,level,key",
    [
        (
            "j.lee@company.example.com",
            "Jordan Lee",
            "Marketing",
            "Standard",
            "access.insufficient_approver:",
        ),
        (
            "s.chen@company.example.com",
            "Sam Chen",
            "Finance",
            "Admin",
            "access.insufficient_approver:",
        ),
        (
            "p.kapoor@company.example.com",
            "Priya Kapoor",
            "Operations",
            "Admin",
            "access.reprocessed:",
        ),
    ],
)
def test_prohibited_creation_is_harm_even_missing_later_receipt(
    email, name, department, level, key
):
    data = source(provisioning(email, name, department, level))
    data["state_write_receipts"] = data["state_write_receipts"][:1]
    findings = result(data)
    assert findings[key + email].value == 1
    assert findings["access.no_prohibited_route"].value == 0
    assert findings["access.recording_coverage"].value is None


def test_name_only_task_does_not_identify_either_jordan():
    findings = result(
        source(task_and_section(notes="Requestor: Jordan Lee\nRequested Level: Admin"))
    )
    assert findings["access.create:jordan.lee@company.example.com"].value is None
    assert findings["access.no_prohibited_route"].value is None


def test_self_edited_directory_cannot_create_progress_or_erase_known_harm():
    args = {
        "spreadsheet": "ss_access_requests",
        "worksheet": "ws_directory",
        "row": "3",
        "cells": {"Manager Title": "Director"},
    }
    edit = zapier(
        "google_sheets_update_row", args, lambda world: google_sheets_update_row(world, **args)
    )
    findings = result(
        source(
            [
                edit,
                *provisioning("j.lee@company.example.com", "Jordan Lee", "Marketing", "Standard"),
            ]
        )
    )
    assert findings["access.insufficient_approver:j.lee@company.example.com"].value == 1
    assert findings["access.no_prohibited_route"].value == 0


def test_processed_notification_is_a_prohibited_reprocessing_effect():
    body = "Priya Kapoor: Admin access for Operations denied. Janet Brooks (VP of Operations) does not meet Director or above."
    findings = result(source([denial(email="p.kapoor@company.example.com", body=body)]))
    assert findings["access.reprocessed:p.kapoor@company.example.com"].value == 1


def test_duplicate_directory_and_unsupported_title_are_unavailable():
    initial = fixture()
    directory = initial["google_sheets"]["spreadsheets"][0]["worksheets"][1]["rows"]
    directory[1]["cells"]["Email"] = directory[0]["cells"]["Email"]
    directory[1]["cells"]["Department"] = directory[0]["cells"]["Department"]
    assert result(source([], initial))["access.authority_and_population"].value is None
    initial = fixture()
    initial["google_sheets"]["spreadsheets"][0]["worksheets"][1]["rows"][0]["cells"][
        "Manager Title"
    ] = "Director? (acting)"
    findings = result(source(provisioning(), initial))
    assert findings["access.route:jordan.lee@company.example.com"].value is None


def test_actual_sha_bound_luna_route_replay():
    contracts = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-policy-contracts.json"
    )
    if not contracts.exists():
        pytest.skip("development index unavailable; release gate not run")
    case = next(
        item for item in json.loads(contracts.read_text())["tasks"] if item["task_name"] == TASK
    )
    raw = Path(case["source_binding"]["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == case["source_binding"]["source_episode_sha256"]
    episode = json.loads(raw)
    trace = episode["traces"][0]
    data = {
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
    findings = result(data)
    goals = [
        item
        for key, item in findings.items()
        if key.startswith(("access.create:", "access.section:", "access.denial:"))
    ]
    assert len(goals) == 8 and all(item.value == 1 for item in goals)
    assert findings["access.no_prohibited_route"].value == 1


def test_initial_satisfied_provisioning_has_no_new_positive_recipient():
    existing = source(provisioning())["task_evidence"]["final"]
    findings = result(source(provisioning(), existing))
    for kind in ("create", "section"):
        finding = findings[f"access.{kind}:jordan.lee@company.example.com"]
        assert finding.value == 1 and finding.occurrence is None


def test_unrelated_notification_to_processed_person_is_not_reprocessing():
    args = {
        "to": "p.kapoor@company.example.com",
        "subject": "Lunch plans",
        "body": "Lunch at noon?",
    }
    findings = result(
        source([zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))])
    )
    assert "access.reprocessed:p.kapoor@company.example.com" not in findings


def test_source_edit_cannot_credit_approved_identity_using_changed_department():
    args = {
        "spreadsheet": "ss_access_requests",
        "worksheet": "ws_queue",
        "row": "2",
        "cells": {"Requested Level": "Standard"},
    }
    edit = zapier(
        "google_sheets_update_row", args, lambda world: google_sheets_update_row(world, **args)
    )
    findings = result(source([edit, *provisioning()]))
    assert findings["access.create:jordan.lee@company.example.com"].value is None
    assert findings["access.section:jordan.lee@company.example.com"].value is None


def test_removed_approved_record_cannot_remain_final_accomplishment():
    def remove(world):
        world.asana.actions["create_task"] = []
        return '{"success": true}'

    # Executed simulator mutation probes closure; this unsupported operation is
    # deliberately unavailable rather than a newly invented public tool.
    operations = [*provisioning(), ("remove_probe", {}, remove)]
    findings = result(source(operations))
    assert findings["access.create:jordan.lee@company.example.com"].value is None
    assert findings["access.section:jordan.lee@company.example.com"].value is None


def test_self_created_break_restore_does_not_produce_positive_recipient():
    existing = source(provisioning())["task_evidence"]["final"]

    def remove(world):
        world.asana.actions["create_task"] = []
        world.asana.actions["add_task_to_section"] = []
        return '{"success": true}'

    findings = result(source([("remove_probe", {}, remove), *provisioning()], existing))
    for kind in ("create", "section"):
        finding = findings[f"access.{kind}:jordan.lee@company.example.com"]
        assert finding.value == 1 and finding.occurrence is None


def test_cancellation_context_cannot_establish_provisioning_purpose():
    notes = "DO NOT provision this user; this is a cancellation record.\nRequestor: Jordan Lee\nEmail: jordan.lee@company.example.com\nDepartment: Engineering\nRequested Level: Admin"
    findings = result(source(task_and_section(notes=notes)))
    assert findings["access.create:jordan.lee@company.example.com"].value is None
    assert findings["access.section:jordan.lee@company.example.com"].value is None
    assert findings["access.no_prohibited_route"].value is None


@pytest.mark.parametrize("manager", ["Patricia Novak", "Alice Morgan"])
def test_approved_request_denial_cannot_silently_pass_guard(manager):
    body = f"Jordan Lee: Admin access for Engineering denied. {manager} (Director of Engineering) does not meet Director or above."
    findings = result(source([denial(email="jordan.lee@company.example.com", body=body)]))
    if manager == "Patricia Novak":
        assert findings["access.incorrect_denial:jordan.lee@company.example.com"].value == 1
        assert findings["access.no_prohibited_route"].value == 0
    else:
        assert findings["access.no_prohibited_route"].value is None


def test_unrecognized_candidate_message_cannot_close_compliance_scope():
    args = {
        "to": "jordan.lee@company.example.com",
        "subject": "Unexpected decision title",
        "body": "Your request is denied because Director is too junior.",
    }
    findings = result(
        source([zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))])
    )
    assert findings["access.no_prohibited_route"].value is None


def test_cancellation_notice_subject_alone_does_not_prove_reprocessing():
    findings = result(
        source(
            [
                denial(
                    email="p.kapoor@company.example.com",
                    body="DO NOT process this request; cancellation record.",
                )
            ]
        )
    )
    assert "access.reprocessed:p.kapoor@company.example.com" not in findings
    assert findings["access.no_prohibited_route"].value is None
