"""Public-data joins and reviewed obligation identity are independent of traces."""

from dataclasses import replace

from automationbench_v1.support_rules import (
    DigestClaimContract,
    EscalationEffect,
    RefundOrder,
    ReviewObligation,
    ReviewPurposeForm,
    escalation_accomplishments,
    join_refund_order,
    order_tokens,
)


def obligation(purpose="repeat_refunder", phrases=("repeat refunder",)):
    return ReviewObligation(
        RefundOrder("ticket", "4508", "Carlos Mendez", "carlos@example.com", "$250.00"),
        purpose,
        "2026-02-01",
        tuple(
            ReviewPurposeForm("Review order {order}", "{customer_email} {amount} " + phrase)
            for phrase in phrases
        ),
        "reviewed_public_policy_v1",
    )


def effect(identity="first", **changes):
    params = {
        "project": "FIN",
        "issuetype": "Task",
        "summary": "Review order 4508",
        "description": "carlos@example.com $250.00 repeat refunder",
    }
    params.update(changes)
    return EscalationEffect(identity, "record_" + identity, params, 0, 1)


def test_exact_order_customer_join_preserves_source_amount_and_rejects_ambiguity():
    ticket = {
        "id": "ticket",
        "subject": "Refund: Order #4501",
        "messages": [],
        "customer": {"name": "Jenny Liu", "email": "jenny@example.com"},
    }
    row = {"cells": {"Order Number": "4501", "Customer Name": "Jenny Liu", "Amount": "$650.00"}}
    found = join_refund_order(ticket, (row,))
    assert (
        found is not None
        and found.amount == "$650.00"
        and found.customer_email == "jenny@example.com"
    )
    assert join_refund_order({**ticket, "subject": "Order 45010"}, (row,)) is None
    assert join_refund_order({**ticket, "subject": "Orders order4501 order 4502"}, (row,)) is None
    assert join_refund_order(ticket, (row, row)) is None
    assert (
        join_refund_order(
            {**ticket, "customer": {"name": "Other", "email": "jenny@example.com"}}, (row,)
        )
        is None
    )
    assert order_tokens("Order #4501 vs order 45010; amount4501") == ("4501", "45010")


def test_duplicate_effects_receive_one_accomplishment_without_inventing_harm():
    first, second = effect(), replace(effect("second"), expected_revision=9, applied_revision=10)
    result = escalation_accomplishments((second, first), (obligation(),), ordered_coverage=True)[0]
    assert result.finding.value == 1 and result.finding.occurrence == "first"
    assert len(result.effects) == 2 and {item.record_id for item in result.effects} == {
        "record_first",
        "record_second",
    }
    assert "duplicate" not in result.finding.reason


def test_different_review_purposes_are_distinct_and_combined_unknown_is_explicit():
    repeat, fraud = obligation(), obligation("fraud", ("fraud review",))
    results = escalation_accomplishments(
        (effect(), effect("fraud", description="carlos@example.com $250.00 fraud review")),
        (repeat, fraud),
        ordered_coverage=True,
    )
    assert [result.finding.value for result in results] == [1, 1]
    combined = effect(description="carlos@example.com $250.00 repeat refunder and fraud review")
    assert all(
        result.finding.value is None
        for result in escalation_accomplishments(
            (combined,), (repeat, fraud), ordered_coverage=True
        )
    )


def test_wrong_project_type_order_customer_amount_and_missing_authority():
    for changes in (
        {"project": "ENG"},
        {"issuetype": "Bug"},
        {"summary": "Review order 45010"},
        {"description": "other@example.com $250.00 repeat refunder"},
        {"description": "carlos@example.com $250 repeat refunder"},
    ):
        assert (
            escalation_accomplishments(
                (effect(**changes),), (obligation(),), ordered_coverage=True
            )[0].finding.value
            == 0
        )
    missing = replace(obligation(), authority_revision="")
    assert (
        escalation_accomplishments((effect(),), (missing,), ordered_coverage=True)[0].finding.value
        is None
    )
    negated = effect(description="carlos@example.com $250.00 not a repeat refunder")
    assert (
        escalation_accomplishments((negated,), (obligation(),), ordered_coverage=True)[
            0
        ].finding.value
        is None
    )
    assert (
        escalation_accomplishments((effect(),), (obligation(),), ordered_coverage=False)[
            0
        ].finding.occurrence
        is None
    )


def test_digest_vocabulary_and_identity_are_explicit_authority():
    contract = DigestClaimContract(
        "reviewed_v1",
        "DIGEST-20260210",
        "2026-02-10",
        (("infrastructure", "ops-lead@company.example.com"),),
        ("Email sent to {recipient}", "email_sent"),
        ("Pending",),
        ("Support digest — {date} — {category}",),
    )
    assert (
        contract.claim_meaning(
            "Email sent to ops-lead@company.example.com", "ops-lead@company.example.com"
        )
        == "completed"
    )
    assert contract.claim_meaning("Pending", "ops-lead@company.example.com") == "pending"
    assert (
        contract.claim_meaning("Intend to email", "ops-lead@company.example.com") == "unavailable"
    )
    assert contract.subject_matches(
        "Support digest — 2026-02-10 — Infrastructure", "infrastructure"
    )
    assert not contract.subject_matches(
        "Support digest — 2026-02-11 — Infrastructure", "infrastructure"
    )
    assert (
        replace(contract, authority_revision="").claim_meaning("email_sent", "x") == "unavailable"
    )


def test_unapproved_preposed_postposed_negation_and_quoted_purpose_are_unavailable():
    for text in (
        "carlos@example.com $250.00 Refund review is not requested",
        "carlos@example.com $250.00 Do not open a refund review",
        "carlos@example.com $250.00 repeat refunder; do not review",
        'carlos@example.com $250.00 quoted: "repeat refunder"',
    ):
        assert (
            escalation_accomplishments(
                (effect(description=text),), (obligation(),), ordered_coverage=True
            )[0].finding.value
            is None
        )
