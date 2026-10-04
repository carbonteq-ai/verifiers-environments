"""Support effect adapters over the shared native world and notification indexes.

These bounded checks are not whole-task scorers. Every duplicate action record
is retained even when a reviewed obligation receives one accomplishment. Log
truth is assessed at its write prefix; subsequent delivery cannot erase it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .contracts.jira_effects import JiraIssueSource, _transition
from .effect_evidence import WorldTransition
from .effect_index import EffectIndex
from .hr_rules import Finding
from .notification_evidence import notifications, operation, result_payload, sheet_rows
from .support_rules import DigestClaimContract, EscalationEffect


def _jira_records(world: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    jira = world.get("jira")
    if not isinstance(jira, Mapping) or not isinstance(jira.get("actions"), Mapping):
        raise ValueError("jira_creation_abstraction_unavailable")  # noqa: TRY004
    records = jira["actions"].get("create_issue", ())
    if not isinstance(records, tuple) or any(not isinstance(item, Mapping) for item in records):
        raise ValueError("jira_creation_records_unavailable")
    ids = [item.get("id") for item in records]
    if any(not isinstance(identity, str) or not identity for identity in ids) or len(
        set(ids)
    ) != len(ids):
        raise ValueError("jira_creation_identity_unresolved")
    return records


def jira_creations(index: EffectIndex) -> tuple[EscalationEffect, ...]:
    """Qualified creation occurrences, retaining audit IDs for legacy consumers.

    Current captures use the shared canonical-issue/result/audit transition
    proof. Historical responses can establish only their original audit-action
    append with unchanged issue inventory; they never hydrate or prove a retained
    issue. Absence of effects is not coverage or whole-task completion.
    """
    effects = []
    for item in index.occurrences:
        action = item.action
        if (
            item.evidence_status != "acknowledged"
            or action is None
            or action.status != "returned"
            or action.error_json is not None
            or item.before_json is None
            or item.after_json is None
            or type(item.expected_revision) is not int
            or type(item.applied_revision) is not int
        ):
            continue
        try:
            transition = _transition(item, index, JiraIssueSource())
        except (ValueError, TypeError, KeyError, AttributeError):
            transition = None
        if transition is not None and transition.kind == "create":
            # Shared proof binds the true issue ID separately from this audit ID.
            assert transition.audit_id is not None
            audit = next(
                record
                for record in _jira_records(index.world(item.after_json))
                if record["id"] == transition.audit_id
            )
            effects.append(
                EscalationEffect(
                    item.invocation_id,
                    transition.audit_id,
                    audit["params"],
                    item.expected_revision,
                    item.applied_revision,
                )
            )
            continue
        name, _ = operation(action)
        if name != "jira_create_issue":
            continue
        payload = result_payload(action)
        if not isinstance(payload, Mapping) or payload.get("success") is not True:
            continue
        returned = payload.get("results")
        if not isinstance(returned, (tuple, list)) or len(returned) != 1:
            continue
        result = returned[0]
        if not isinstance(result, Mapping) or not isinstance(result.get("id"), str):
            continue
        # A failed modern proof cannot downgrade into the legacy abstraction.
        if "action_record_id" in result:
            continue
        old_world, new_world = index.world(item.before_json), index.world(item.after_json)
        if old_world.get("jira", {}).get("issues") != new_world.get("jira", {}).get("issues"):
            continue
        before = _jira_records(index.world(item.before_json))
        after = _jira_records(index.world(item.after_json))
        if len(after) != len(before) + 1 or after[:-1] != before:
            continue
        existing = {record["id"] for record in before}
        candidates = [
            record
            for record in after
            if record["id"] == result["id"] and record["id"] not in existing
        ]
        if len(candidates) != 1:
            continue
        record = candidates[0]
        params = record.get("params")
        if (
            record.get("action_key") != "create_issue"
            or not isinstance(params, Mapping)
            or not all(key in result and result[key] == value for key, value in params.items())
        ):
            continue
        effects.append(
            EscalationEffect(
                item.invocation_id,
                record["id"],
                params,
                item.expected_revision,
                item.applied_revision,
            )
        )
    return tuple(effects)


def jira_creation_coverage(index: EffectIndex, effects: tuple[EscalationEffect, ...]) -> bool:
    """Every observed new action record must have a qualified creation join.

    This closes only observed creation/action-log joins in the supplied revision
    chain. It is never retained-issue or whole-task proof. Modern issue births
    also require their linked creation audit; historical unchanged issue lists
    cannot be promoted to a canonical-issue existence claim.
    """
    if not index.service_history(("jira",)).captured_scope_qualified:
        return False
    joined = {(effect.invocation_id, effect.record_id) for effect in effects}
    for item in index.occurrences:
        assert item.before_json is not None and item.after_json is not None
        if (
            item.action is not None
            and operation(item.action)[0] == "jira_create_issue"
            and result_payload(item.action) is None
        ):
            return False
        before = {record["id"] for record in _jira_records(index.world(item.before_json))}
        after = {record["id"] for record in _jira_records(index.world(item.after_json))}
        if any((item.invocation_id, identity) not in joined for identity in after - before):
            return False
        old_jira = index.world(item.before_json)["jira"]
        new_jira = index.world(item.after_json)["jira"]
        old_issues, new_issues = old_jira.get("issues"), new_jira.get("issues")
        if old_issues == new_issues:
            continue
        if not isinstance(old_issues, tuple) or not isinstance(new_issues, tuple):
            return False
        old_ids = [issue.get("id") for issue in old_issues if isinstance(issue, Mapping)]
        new_ids = [issue.get("id") for issue in new_issues if isinstance(issue, Mapping)]
        if (
            len(old_ids) != len(old_issues)
            or len(new_ids) != len(new_issues)
            or any(type(identity) is not str or not identity for identity in (*old_ids, *new_ids))
            or len(set(old_ids)) != len(old_ids)
            or len(set(new_ids)) != len(new_ids)
        ):
            return False
        if any(
            (item.invocation_id, issue.get("creation_action_id")) not in joined
            for issue in new_issues
            if issue["id"] not in old_ids
        ):
            return False
    return True


@dataclass(frozen=True)
class LogClaimEvidence:
    row_id: Any
    native_row_id: str
    invocation_id: str
    expected_revision: int | None
    finding: Finding
    matching_send_ids: tuple[str, ...] = ()


def _prefix(index: EffectIndex, log: WorldTransition) -> EffectIndex | None:
    """Use revision facts, never tuple order, to bound acknowledged prior work."""
    if type(log.expected_revision) is not int:
        return None
    # Revision zero is the acknowledged start of the maintained state window:
    # there are no earlier applied writes. Unknown later captures cannot change
    # this already established empty prefix.
    if log.expected_revision == 0:
        return EffectIndex(())
    if any(type(item.expected_revision) is not int for item in index.occurrences):
        return None
    prior = tuple(
        item
        for item in index.occurrences
        if item.expected_revision is not None and item.expected_revision < log.expected_revision
    )
    if not prior:
        return None
    prefix = EffectIndex(prior)
    chain = prefix.serial_chain()
    if (
        chain.status != "qualified"
        or chain.revision_interval != (0, log.expected_revision)
        or chain.ordered[-1].after_json != log.before_json
    ):
        return None
    return prefix


def _failed_without_gmail_effect(index: EffectIndex, invocation: str) -> bool:
    """Known maintained simulator call failed with an acknowledged unchanged world.

    This applies to the in-memory Gmail abstraction, never an external delivery
    system. A failure with observed mutation remains unresolved.
    """
    matching = [item for item in index.occurrences if item.invocation_id == invocation]
    if len(matching) != 1:
        return False
    item = matching[0]
    if item.action is None or item.action.status not in {"raised", "rejected"}:
        return False
    name, _ = operation(item.action)
    if name not in {
        "gmail_send_email",
        "gmail_create_draft",
        "gmail_create_draft_v2",
        "gmail_create_draft_reply",
    }:
        return False
    return any(
        observation.invocation_id == invocation and observation.status == "unchanged"
        for observation in index.service_history(("gmail",)).observations
    )


def digest_log_claims(
    index: EffectIndex, contract: DigestClaimContract | None
) -> tuple[LogClaimEvidence, ...]:
    """Assess new/changed literal completed claims independently of final sends.

    The current bounded contract requires this run's earlier acknowledged sends;
    fixture log history is ignored. Missing authority, unsupported literal forms,
    ambiguous matching, or incomplete prior capture is explicit unavailability.
    Count correctness and category/threshold policy remain separate properties.
    """
    findings = []
    for item in index.occurrences:
        if item.action is None or item.before_json is None or item.after_json is None:
            continue
        before = sheet_rows(index.world(item.before_json), "ss_digest", "ws_digest_log")
        after = sheet_rows(index.world(item.after_json), "ss_digest", "ws_digest_log")
        old = {row["row_id"]: row for row in before}
        for row in after:
            previous = old.get(row["row_id"])
            cells = row.get("cells")
            if not isinstance(cells, Mapping):
                raise ValueError("digest_log_cells_unavailable")  # noqa: TRY004
            if previous is not None and previous.get("cells") == cells:
                continue
            if (
                previous is not None
                and isinstance(previous.get("cells"), Mapping)
                and all(
                    previous["cells"].get(key) == cells.get(key)
                    for key in ("Action_Taken", "Date", "Category")
                )
            ):
                continue
            native_id = row.get("id")
            if not isinstance(native_id, str) or not native_id:
                raise ValueError("digest_native_row_identity_unavailable")
            key = "hiver.premature_completed_claim:" + native_id
            reason = "completed_claim_authority_unavailable"
            value = None
            matching: tuple[str, ...] = ()
            category = cells.get("Category")
            recipient = (
                contract.recipient(category) if contract and isinstance(category, str) else None
            )
            if (
                item.evidence_status != "acknowledged"
                or item.action.status != "returned"
                or type(item.expected_revision) is not int
            ):
                reason = "log_write_acknowledgement_unavailable"
            elif contract and recipient and isinstance(category, str):
                meaning = contract.claim_meaning(str(cells.get("Action_Taken", "")), recipient)
                if meaning == "pending":
                    reason = "not_a_completed_claim"
                elif meaning == "unavailable":
                    reason = "completed_claim_literal_unavailable"
                elif (
                    contract.prior_evidence != "solver_sends_in_this_window"
                    or not contract.subject_forms
                    or not contract.digest_id
                    or cells.get("Date") != contract.digest_date
                ):
                    reason = "digest_identity_or_prior_evidence_unavailable"
                else:
                    prefix = _prefix(index, item)
                    if prefix is None:
                        reason = "prior_send_capture_unavailable"
                    else:
                        observed = notifications(prefix)
                        matching = tuple(
                            notification.invocation_id
                            for notification in observed
                            if notification.status == "qualified"
                            and notification.kind == "send"
                            and notification.message is not None
                            and recipient.casefold()
                            in {email.casefold() for email in notification.recipients}
                            and contract.subject_matches(
                                str(notification.message.get("subject", "")), category
                            )
                        )
                        covered = (
                            item.expected_revision == 0
                            or prefix.service_history(("gmail",)).captured_scope_qualified
                        ) and all(
                            notification.status == "qualified"
                            or _failed_without_gmail_effect(prefix, notification.invocation_id)
                            for notification in observed
                        )
                        if len(matching) > 1:
                            reason = "matching_prior_send_ambiguous"
                        elif matching:
                            value, reason = 0.0, "earlier_send_acknowledged"
                        elif covered:
                            value, reason = 1.0, "completed_claim_precedes_acknowledged_send"
                        else:
                            reason = "prior_send_capture_unavailable"
            findings.append(
                LogClaimEvidence(
                    row["row_id"],
                    native_id,
                    item.invocation_id,
                    item.expected_revision,
                    Finding(key, value, reason, item.invocation_id),
                    matching,
                )
            )
    return tuple(findings)
