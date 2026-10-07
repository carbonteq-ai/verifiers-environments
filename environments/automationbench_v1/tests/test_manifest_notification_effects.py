"""Genuine native Gmail delivery witnesses and scoped inventory uncertainty."""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from test_notification_evidence import run_operations, zapier

from automationbench.schema.world import WorldState
from automationbench.tools.api.impl.gmail import gmail_drafts_send
from automationbench.tools.zapier.gmail.draft import gmail_create_draft
from automationbench.tools.zapier.gmail.message import gmail_reply_to_email, gmail_send_email
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.notification_effects import (
    NotificationEffectSource,
    capture_notification_effects,
)


def initial():
    return {"gmail": {"messages": [], "drafts": []}}


def send(**changes):
    args: dict[str, Any] = {
        "to": "Person <person@example.com>",
        "cc": "copy@example.com",
        "bcc": "hidden@example.com",
        "subject": "Delivery",
        "body": "Exact content",
        **changes,
    }
    return zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))


def capture(data):
    return capture_notification_effects(data, NotificationEffectSource())


def payload(fact):
    assert fact.params_json is not None
    return json.loads(fact.params_json)


def test_native_send_records_acknowledged_identity_content_and_recipient_roles():
    data = run_operations(initial(), [send()])
    evidence = capture(data)
    assert evidence.complete and len(evidence.effects) == 1
    fact = evidence.effects[0]
    assert (
        fact.kind == "send" and fact.status == "qualified" and fact.invocation_id == "execution-0"
    )
    assert (fact.expected_revision, fact.applied_revision) == (0, 1)
    params = payload(fact)
    assert params["message_id"] == fact.effect_id
    assert params["subject"] == "Delivery" and params["body_plain"] == "Exact content"
    assert params["to"] == ["person@example.com"] and params["cc"] == ["copy@example.com"]
    assert params["bcc"] == ["hidden@example.com"]


def test_public_legacy_empty_inbox_binds_real_send_and_still_requires_ack():
    public = {"gmail": {"drafts": [], "emails": []}}
    data = run_operations(public, [send()])
    data["task_evidence"]["initial"] = copy.deepcopy(public)
    evidence = capture(data)
    assert evidence.complete and len(evidence.effects) == 1
    assert evidence.effects[0].status == "qualified"
    assert payload(evidence.effects[0])["body_plain"] == "Exact content"
    data["state_write_receipts"] = []
    missing_ack = capture(data)
    assert not missing_ack.complete
    assert all(fact.status != "qualified" for fact in missing_ack.effects)


@pytest.mark.parametrize("body_type", ["plain", "html"])
def test_native_signature_and_body_representation_are_explicit(body_type):
    evidence = capture(
        run_operations(initial(), [send(body_type=body_type, signature="Signature")])
    )
    assert evidence.complete
    params = payload(evidence.effects[0])
    assert (
        params["body_html" if body_type == "html" else "body_plain"] == "Exact content\n\nSignature"
    )


def test_draft_with_sent_label_never_establishes_delivery():
    args = {
        "to": "person@example.com",
        "subject": "Draft",
        "body": "Draft content",
        "label_ids": "SENT",
    }
    data = run_operations(
        initial(),
        [zapier("gmail_create_draft", args, lambda world: gmail_create_draft(world, **args))],
    )
    evidence = capture(data)
    assert evidence.complete and evidence.effects == ()


def test_label_mutation_is_unsupported_and_never_an_acknowledged_send():
    world = WorldState.model_validate(initial())
    gmail_create_draft(world, to="person@example.com", subject="Draft", body="Draft content")

    def labels(world):
        world.gmail.messages[0].label_ids = ["SENT"]
        return {"success": True, "message": {"id": world.gmail.messages[0].id}}

    evidence = capture(
        run_operations(
            world.model_dump(mode="json"), [zapier("gmail_add_label_to_email", {}, labels)]
        )
    )
    assert not evidence.complete and all(fact.status == "unavailable" for fact in evidence.effects)


def test_existing_draft_send_qualifies_new_native_message_not_draft_identity():
    world = WorldState.model_validate(initial())
    gmail_create_draft(world, to="person@example.com", subject="Draft", body="Draft content")
    draft_id, draft_message = world.gmail.drafts[0].id, world.gmail.drafts[0].message_id
    args = {"method": "POST", "url": "/gmail/v1/users/me/drafts/send", "body": {"id": draft_id}}
    evidence = capture(
        run_operations(
            world.model_dump(mode="json"),
            [("api_fetch", args, lambda state: gmail_drafts_send(state, id=draft_id))],
        )
    )
    assert evidence.complete and evidence.effects[0].status == "qualified"
    assert evidence.effects[0].effect_id != draft_message
    assert payload(evidence.effects[0])["body_plain"] == "Draft content"


def test_native_reply_defaults_bind_exact_parent_and_keep_duplicate_calls_distinct():
    world = WorldState.model_validate(initial())
    gmail_send_email(world, to="person@example.com", subject="Original", body="Original")
    args = {"thread_id": world.gmail.messages[0].thread_id, "body": "Reply"}
    operation = zapier(
        "gmail_reply_to_email", args, lambda state: gmail_reply_to_email(state, **args)
    )
    data = run_operations(world.model_dump(mode="json"), [operation, operation])
    evidence = capture(data)
    assert evidence.complete and evidence.effects[0].status == "qualified"
    assert payload(evidence.effects[0])["subject"] == "Re: Original"
    assert len({fact.effect_id for fact in evidence.effects}) == 2
    data = run_operations(initial(), [send(), send()])
    evidence = capture(data)
    assert evidence.complete and len({fact.effect_id for fact in evidence.effects}) == 2
    assert {fact.invocation_id for fact in evidence.effects} == {"execution-0", "execution-1"}


@pytest.mark.parametrize(
    "gap", ["own-ack", "later-ack", "repair", "initial-collection", "foreign-call", "unmatched-ack"]
)
def test_positive_witnesses_survive_unrelated_gaps_without_false_completeness(gap):
    def repair(world):
        world.gmail.messages = []
        return {"success": True}

    operations: list[Any] = [send(), send()] if gap == "later-ack" else [send()]
    if gap == "repair":
        operations.append(zapier("gmail_delete_message", {}, repair))
    if gap == "foreign-call":
        operations.append(zapier("foreign_tool", {}, lambda world: {}))
    data = run_operations(initial(), operations)
    if gap == "own-ack":
        data["state_write_receipts"] = []
    if gap == "later-ack":
        data["state_write_receipts"] = data["state_write_receipts"][:1]
    if gap == "initial-collection":
        del data["task_evidence"]["initial"]["gmail"]["messages"]
    if gap == "unmatched-ack":
        data["state_write_receipts"].append(
            {
                "write_id": "unobserved",
                "expected_revision": 1,
                "applied_revision": 2,
                "conflict": False,
            }
        )
    evidence = capture(data)
    # An omitted public collection starts at its schema default (empty), which
    # is exactly the native starting world here, so inventory closes.
    assert evidence.complete is (gap == "initial-collection")
    assert evidence.effects[0].status == ("unavailable" if gap == "own-ack" else "qualified")


def test_requested_content_mismatch_cannot_borrow_a_real_send_witness():
    args = {"to": "person@example.com", "subject": "Requested", "body": "Requested"}
    data = run_operations(
        initial(),
        [
            zapier(
                "gmail_send_email",
                args,
                lambda world: gmail_send_email(
                    world, to="person@example.com", subject="Different", body="Different"
                ),
            )
        ],
    )
    evidence = capture(data)
    assert not evidence.complete and evidence.effects[0].status == "unavailable"


@pytest.mark.parametrize("success", [None, 0, 1, False])
def test_zapier_success_ack_requires_exact_native_true(success):
    data = run_operations(initial(), [send()])
    event = data["tool_execution_events"][0]
    receipt = json.loads(event["receipt_json"])
    envelope = json.loads(receipt["evidence_json"][0])
    returned = json.loads(json.loads(envelope["action"]["result_json"]))
    returned["success"] = success
    envelope["action"]["result_json"] = canonical_json(canonical_json(returned))
    receipt["evidence_json"] = [canonical_json(envelope)]
    event["receipt_json"] = canonical_json(receipt)
    evidence = capture(data)
    assert not evidence.complete and evidence.effects[0].status == "unavailable"


def test_retained_source_is_immutable_and_selector_bound():
    data = run_operations(initial(), [send()])
    before = copy.deepcopy(data)
    evidence = capture(data)
    assert data == before
    assert (
        evidence.selector_digest
        == hashlib.sha256(
            canonical_json(NotificationEffectSource().model_dump(mode="json")).encode()
        ).hexdigest()
    )
    assert evidence.source_digest == hashlib.sha256(canonical_json(data).encode()).hexdigest()


@pytest.mark.parametrize(
    "task_name,has_send",
    [("simple.email_airtable_customer_welcome", True), ("simple.gmail_invoice_email", False)],
)
def test_actual_selected_luna_traces_distinguish_send_from_failed_preparation(task_name, has_send):
    path = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate/cross-category-selection.json"
    )
    if not path.exists():
        pytest.skip("selected development source index unavailable")
    selected = next(
        item for item in json.loads(path.read_text())["tasks"] if item["task_name"] == task_name
    )
    raw = Path(selected["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == selected["source_episode_sha256"]
    episode = json.loads(raw)
    trace = episode["traces"][0]
    data = {
        "task_evidence": {
            "initial": episode["task"]["data"]["initial_state"],
            "final": trace["info"]["automationbench"]["end_state"],
            "complete": trace["is_completed"],
        },
        "tool_execution_events": trace["tool_execution_events"],
        "state_write_receipts": trace["state_write_receipts"],
    }
    evidence = capture(data)
    assert (
        any(fact.status == "qualified" and fact.kind == "send" for fact in evidence.effects)
        is has_send
    )
    # Every other call (search, Airtable, ChatGPT, audited Gmail reads) cannot
    # send, so a missing send is now known rather than unknown.
    assert evidence.complete
