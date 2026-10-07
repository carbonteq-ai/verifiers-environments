"""Native simulator executions distinguish sends, drafts and label manipulation."""

import copy
import hashlib
import json

import pytest

from automationbench.schema.world import WorldState
from automationbench.tools.api.impl.gmail import gmail_drafts_send
from automationbench.tools.zapier.gmail.draft import gmail_create_draft
from automationbench.tools.zapier.gmail.message import gmail_reply_to_email, gmail_send_email
from automationbench_v1.capture import CapturedAction, canonical_json
from automationbench_v1.effect_evidence import world_transitions
from automationbench_v1.effect_index import EffectIndex
from automationbench_v1.notification_evidence import notifications, operation, sheet_rows


def run_operations(initial, operations):
    """Execute real simulator handlers and retain their acknowledged local effects."""
    world = WorldState.model_validate(copy.deepcopy(initial))
    hydrated = world.model_dump(mode="json")
    events, writes = [], []
    for index, (name, args, handler) in enumerate(operations):
        before = canonical_json(world.model_dump(mode="json"))
        result = handler(world)
        after = canonical_json(world.model_dump(mode="json"))
        snapshots = {hashlib.sha256(value.encode()).hexdigest(): value for value in (before, after)}
        capture = CapturedAction(
            occurrence_index=index,
            tool_name=name,
            arguments_json=canonical_json(args),
            before_digest=hashlib.sha256(before.encode()).hexdigest(),
            after_digest=hashlib.sha256(after.encode()).hexdigest(),
            status="returned",
            result_json=canonical_json(result),
        )
        invocation = f"execution-{index}"
        receipt = {
            "invocation_id": invocation,
            "phase": "returned",
            "state_read_revision": index,
            "state_write_revision": index + 1,
            "state_persistence": "applied",
            "state_conflict": False,
            "evidence_json": [
                canonical_json(
                    {
                        "kind": "automationbench_raw_action",
                        "action": capture.model_dump(mode="json"),
                        "snapshots": snapshots,
                    }
                )
            ],
        }
        events.append({"source": "tool_server", "receipt_json": canonical_json(receipt)})
        writes.append(
            {
                "write_id": invocation,
                "expected_revision": index,
                "applied_revision": index + 1,
                "conflict": False,
            }
        )
    return {
        "tool_execution_events": events,
        "state_write_receipts": writes,
        "task_evidence": {
            "initial": hydrated,
            "final": world.model_dump(mode="json"),
            "complete": True,
        },
    }


def zapier(name, args, handler):
    return "execute_tool", {"tool_name": name, "arguments": canonical_json(args)}, handler


def test_draft_with_sent_label_is_still_not_a_send():
    args = {
        "to": "person@example.com",
        "subject": "Draft",
        "body": "Not delivered",
        "label_ids": "SENT",
    }
    source = run_operations(
        {}, [zapier("gmail_create_draft", args, lambda world: gmail_create_draft(world, **args))]
    )
    notices = notifications(EffectIndex(world_transitions(source)))
    assert len(notices) == 1
    assert notices[0].kind == "draft" and notices[0].status == "qualified"
    assert "SENT" in notices[0].message["label_ids"]


def test_send_existing_draft_uses_operation_result_and_native_effect():
    draft_args = {"to": "person@example.com", "subject": "Draft", "body": "Real delivery"}
    initial = WorldState.model_validate({})
    gmail_create_draft(initial, **draft_args)
    draft_id = initial.gmail.drafts[0].id
    source = run_operations(
        initial.model_dump(mode="json"),
        [
            (
                "api_fetch",
                {
                    "method": "POST",
                    "url": "/gmail/v1/users/me/drafts/send",
                    "body": {"id": draft_id},
                },
                lambda world: gmail_drafts_send(world, id=draft_id),
            )
        ],
    )
    (notice,) = notifications(EffectIndex(world_transitions(source)))
    assert notice.kind == "send" and notice.status == "qualified"
    assert notice.message_id != initial.gmail.drafts[0].message_id
    assert notice.recipients == ("person@example.com",)


def test_reply_and_duplicate_content_keep_two_execution_identities():
    initial = WorldState.model_validate({})
    gmail_send_email(initial, "person@example.com", "Original", "Original")
    thread = initial.gmail.messages[0].thread_id
    args = {"thread_id": thread, "body": "Reply", "to": "person@example.com"}
    source = run_operations(
        initial.model_dump(mode="json"),
        [
            zapier("gmail_reply_to_email", args, lambda world: gmail_reply_to_email(world, **args)),
            zapier("gmail_reply_to_email", args, lambda world: gmail_reply_to_email(world, **args)),
        ],
    )
    notices = notifications(EffectIndex(world_transitions(source)))
    assert len(notices) == 2 and all(item.status == "qualified" for item in notices)
    assert {item.invocation_id for item in notices} == {"execution-0", "execution-1"}
    assert len({item.message_id for item in notices}) == 2


def test_read_status_change_does_not_become_unknown_send():
    initial = WorldState.model_validate({})
    gmail_send_email(initial, "person@example.com", "Original", "Original")

    def read(world):
        world.gmail.messages[0].is_read = not world.gmail.messages[0].is_read
        return "{}"

    source = run_operations(initial.model_dump(mode="json"), [zapier("gmail_find_email", {}, read)])
    assert notifications(EffectIndex(world_transitions(source))) == ()


def test_missing_ack_and_forged_result_id_do_not_establish_delivery():
    args = {
        "to": "Person <person@example.com>",
        "subject": "Sent",
        "body": "Real delivery",
        "cc": "copy@example.com",
        "bcc": "hidden@example.com",
    }
    source = run_operations(
        {}, [zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))]
    )
    (notice,) = notifications(EffectIndex(world_transitions(source)))
    assert notice.status == "qualified"
    assert notice.recipients == ("person@example.com", "copy@example.com", "hidden@example.com")
    no_ack = copy.deepcopy(source)
    no_ack["state_write_receipts"] = []
    assert notifications(EffectIndex(world_transitions(no_ack)))[0].status == "unavailable"
    receipt = json.loads(source["tool_execution_events"][0]["receipt_json"])
    envelope = json.loads(receipt["evidence_json"][0])
    envelope["action"]["result_json"] = canonical_json({"message": {"id": "wrong"}})
    receipt["evidence_json"] = [canonical_json(envelope)]
    source["tool_execution_events"][0]["receipt_json"] = canonical_json(receipt)
    assert notifications(EffectIndex(world_transitions(source)))[0].status == "unavailable"


def test_labels_only_do_not_prove_send_and_nested_operation_unwrap_is_exact():
    initial = WorldState.model_validate({})
    gmail_create_draft(initial, to="person@example.com", body="Draft")

    def modify(world):
        world.gmail.messages[0].label_ids = ["SENT"]
        return "{}"

    source = run_operations(
        initial.model_dump(mode="json"),
        [("api_fetch", {"method": "POST", "url": "/gmail/v1/users/me/messages/id/modify"}, modify)],
    )
    (notice,) = notifications(EffectIndex(world_transitions(source)))
    assert notice.kind == "unknown" and notice.status == "unavailable"
    action = world_transitions(source)[0].action
    name, args = operation(action)
    assert name == "api_fetch" and args["method"] == "POST"
    with pytest.raises(TypeError):
        args["method"] = "GET"


def test_scoped_sheet_rows_normalize_nested_and_flat_without_global_row_join():
    initial = {
        "google_sheets": {
            "spreadsheets": [
                {
                    "id": "ss",
                    "title": "Sheet",
                    "worksheets": [
                        {
                            "id": "ws",
                            "title": "Tab",
                            "headers": ["Value"],
                            "rows": [{"row_id": 2, "cells": {"Value": "A"}}],
                        }
                    ],
                }
            ]
        }
    }
    world = WorldState.model_validate(copy.deepcopy(initial)).model_dump(mode="json")
    assert sheet_rows(initial, "ss", "ws")[0]["cells"] == sheet_rows(world, "ss", "ws")[0]["cells"]
    with pytest.raises(ValueError, match="population"):
        sheet_rows(world, "ss", "absent")
    world["google_sheets"]["rows"].append(copy.deepcopy(world["google_sheets"]["rows"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        sheet_rows(world, "ss", "ws")


def test_duplicate_other_message_identity_cannot_hide_a_notification_mutation():
    initial = {
        "gmail": {
            "messages": [
                {"id": "duplicate", "subject": "First", "to": ["first@example.com"]},
                {"id": "duplicate", "subject": "Second", "to": ["second@example.com"]},
            ]
        }
    }

    def mutate(world):
        world.gmail.messages[0].label_ids = ["SENT"]
        return "{}"

    source = run_operations(
        initial,
        [
            (
                "api_fetch",
                {"method": "POST", "url": "/gmail/v1/users/me/messages/duplicate/modify"},
                mutate,
            )
        ],
    )
    (notice,) = notifications(EffectIndex(world_transitions(source)))
    assert notice.status == "unavailable"
    assert notice.reason == "message_population_identity_unresolved"
