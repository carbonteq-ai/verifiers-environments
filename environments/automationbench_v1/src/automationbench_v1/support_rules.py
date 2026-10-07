"""Bounded support predicates with explicit, independently reviewed authority.

Contracts describe one review obligation or literal log vocabulary. They do not
resolve overlapping refund policies, digest categories or threshold equality.
No duplicate penalty is inferred from deduplicated accomplishment credit.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .hr_rules import Finding


def literal_token(text: str, token: str) -> bool:
    if "@" in token:
        left, right = r"(?<![\w@.])", r"(?![\w@]|\.[A-Za-z0-9])"
    elif token.startswith("$"):
        left, right = r"(?<![\w$.])", r"(?!\w|\.\d)"
    else:
        left, right = r"(?<!\w)", r"(?!\w)"
    return bool(re.search(left + re.escape(token) + right, text, re.IGNORECASE))


def order_tokens(text: str) -> tuple[str, ...]:
    """Explicit order syntax; 4501 never matches 45010 or an unrelated number."""
    return tuple(sorted(set(re.findall(r"\border\s*#?\s*(\d+)\b", text, re.IGNORECASE))))


@dataclass(frozen=True)
class RefundOrder:
    ticket_id: str
    order: str
    customer_name: str
    customer_email: str
    amount: str


def join_refund_order(
    ticket: Mapping[str, Any], rows: tuple[Mapping[str, Any], ...]
) -> RefundOrder | None:
    """Orders expose customer names, not emails; email comes from the ticket.

    Exact customer-name agreement is required; this is not fuzzy identity or
    eligibility classification. Ambiguous ticket order references or row matches
    remain unresolved. Source amount spelling is retained.
    """
    customer = ticket.get("customer")
    messages = ticket.get("messages", ())
    if not isinstance(customer, Mapping) or not isinstance(messages, (tuple, list)):
        return None
    if any(not isinstance(message, Mapping) for message in messages):
        return None
    text = (
        str(ticket.get("subject", ""))
        + " "
        + " ".join(str(message.get("body_text", "")) for message in messages)
    )
    orders = order_tokens(text)
    if len(orders) != 1:
        return None
    email, name, ticket_id = customer.get("email"), customer.get("name"), ticket.get("id")
    if (
        not isinstance(email, str)
        or not email
        or not isinstance(name, str)
        or not name
        or not isinstance(ticket_id, str)
        or not ticket_id
    ):
        return None
    if any(
        message.get("sender_type") == "customer"
        and (
            not isinstance(message.get("sender_email", email), str)
            or message.get("sender_email", email).casefold() != email.casefold()
        )
        for message in messages
    ):
        return None
    matches = [
        row.get("cells", {})
        for row in rows
        if isinstance(row.get("cells"), Mapping)
        and row["cells"].get("Order Number") == orders[0]
        and row["cells"].get("Customer Name") == name
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("Amount"), str):
        return None
    return RefundOrder(ticket_id, orders[0], name, email, matches[0]["Amount"])


@dataclass(frozen=True)
class ReviewPurposeForm:
    """A finite approved full summary/description template, not substring intent."""

    summary: str
    description: str

    def matches(self, params: Mapping[str, Any], order: RefundOrder) -> bool:
        values = {
            "order": order.order,
            "customer_name": order.customer_name,
            "customer_email": order.customer_email,
            "amount": order.amount,
        }
        return params.get("summary") == self.summary.format(**values) and params.get(
            "description"
        ) == self.description.format(**values)


@dataclass(frozen=True)
class ReviewObligation:
    """Reviewed public-policy decision, not a classifier inferred from a trace."""

    order: RefundOrder
    purpose: str
    task_window: str
    purpose_forms: tuple[ReviewPurposeForm, ...]
    authority_revision: str

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (
            self.order.order,
            self.order.customer_email.casefold(),
            self.purpose,
            self.task_window,
        )


@dataclass(frozen=True)
class EscalationEffect:
    invocation_id: str
    record_id: str
    params: Mapping[str, Any]
    expected_revision: int
    applied_revision: int


@dataclass(frozen=True)
class EscalationAccomplishment:
    obligation: ReviewObligation
    effects: tuple[EscalationEffect, ...]
    finding: Finding


def escalation_accomplishments(
    effects: tuple[EscalationEffect, ...],
    obligations: tuple[ReviewObligation, ...],
    *,
    ordered_coverage: bool,
) -> tuple[EscalationAccomplishment, ...]:
    identities = [item.identity for item in obligations]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate_review_obligation")
    matches: dict[tuple[str, str, str, str], list[EscalationEffect]] = {
        identity: [] for identity in identities
    }
    ambiguous: set[tuple[str, str, str, str]] = set()
    for effect in effects:
        params = effect.params
        if params.get("project") != "FIN" or params.get("issuetype") != "Task":
            continue
        text = str(params.get("summary", "")) + " " + str(params.get("description", ""))
        identity_candidates = [
            item
            for item in obligations
            if item.authority_revision
            and item.task_window
            and item.purpose_forms
            and order_tokens(text) == (item.order.order,)
            and literal_token(text, item.order.customer_email)
            and literal_token(text, item.order.amount)
        ]
        candidates = []
        for item in identity_candidates:
            if any(form.matches(params, item.order) for form in item.purpose_forms):
                candidates.append(item)
        if len(candidates) == 1:
            matches[candidates[0].identity].append(effect)
        elif candidates:
            ambiguous.update(item.identity for item in candidates)
        else:
            ambiguous.update(item.identity for item in identity_candidates)
    results = []
    for obligation in obligations:
        selected = tuple(
            sorted(matches[obligation.identity], key=lambda item: item.expected_revision)
        )
        key = "gorgias.review_accomplishment:" + ":".join(obligation.identity)
        authority = bool(
            obligation.authority_revision and obligation.task_window and obligation.purpose_forms
        )
        if not authority:
            finding = Finding(key, None, "review_authority_or_purpose_unresolved")
        elif selected:
            finding = Finding(
                key,
                1.0,
                "acknowledged_review_action_record",
                selected[0].invocation_id if ordered_coverage else None,
            )
        elif obligation.identity in ambiguous:
            finding = Finding(key, None, "review_authority_or_purpose_unresolved")
        else:
            finding = Finding(
                key,
                0.0 if ordered_coverage else None,
                "review_not_created" if ordered_coverage else "review_capture_unresolved",
            )
        results.append(EscalationAccomplishment(obligation, selected, finding))
    return tuple(results)


@dataclass(frozen=True)
class DigestClaimContract:
    """Authored literal meanings and message-identity alternatives.

    Empty authority or forms keep the relevant property unavailable. Subject
    forms are exact templates, not an unrestricted semantic prose classifier.
    This says nothing about conversation categories or notification thresholds.
    """

    authority_revision: str
    digest_id: str
    digest_date: str
    recipients: tuple[tuple[str, str], ...]
    completed_forms: tuple[str, ...]
    pending_forms: tuple[str, ...]
    subject_forms: tuple[str, ...]
    prior_evidence: str = "solver_sends_in_this_window"

    def recipient(self, category: str) -> str | None:
        matches = [email for key, email in self.recipients if key == category]
        return matches[0] if len(matches) == 1 else None

    def claim_meaning(self, text: str, recipient: str) -> str:
        if not self.authority_revision or not self.completed_forms:
            return "unavailable"
        if text in self.pending_forms:
            return "pending"
        if any(text == form.format(recipient=recipient) for form in self.completed_forms):
            return "completed"
        return "unavailable"

    def subject_matches(self, subject: str, category: str) -> bool:
        return any(
            subject.casefold()
            == form.format(
                date=self.digest_date, digest_id=self.digest_id, category=category
            ).casefold()
            for form in self.subject_forms
        )
