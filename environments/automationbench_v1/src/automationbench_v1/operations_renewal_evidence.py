"""Public renewal policy and bounded acknowledged actions, without hidden assertions.

These predicates cover sending agreements and procurement delivery, not signed
contracts, summary semantics, whole-task completion or complete guard coverage.
Arbitrary policy prose and date equality require an explicit reviewed contract.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime

from automationbench.domains.operations.tasks import get_ops_contract_renewal_pipeline_task

from .capture import canonical_json
from .docusign_evidence import envelope_sends
from .effect_index import EffectIndex
from .hr_rules import Finding
from .notification_evidence import notifications, sheet_rows


@dataclass(frozen=True)
class RenewalBoundaryContract:
    """Explicit interpretation of the two otherwise ambiguous equality dates."""

    revision: str
    include_expiry_day: bool
    include_window_day: bool


@dataclass(frozen=True)
class RenewalPeriodContract:
    """Explicit reviewed period membership; no inferred custom-field vocabulary.

    IDs identify initial envelopes only. Unlisted matching envelopes have unknown
    period membership, rather than being treated as this task's completed work.
    """

    revision: str
    task_date: date
    current_envelope_ids: tuple[str, ...] = ()
    prior_period_envelope_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenewalVendor:
    row_id: str
    vendor: str
    email: str
    eligible: bool | None
    reason: str
    already_sent: bool | None


@dataclass(frozen=True)
class RenewalPolicy:
    today: date
    window_days: int
    template_id: str
    vendors: tuple[RenewalVendor, ...]
    public_policy_json: str
    boundary_revision: str | None
    source_projection_json: str
    period_revision: str | None
    procurement_email: str = "procurement@ourcompany.example.com"


def compile_renewal_policy(
    initial: Mapping,
    prompt: list | tuple,
    boundary: RenewalBoundaryContract | None = None,
    period: RenewalPeriodContract | None = None,
) -> RenewalPolicy:
    """Resolve this exact public request and declared policy, failing closed on drift.

    Blank notes and the exact public hold note have deterministic semantics.
    Novel notes, ambiguous contacts, or boundary dates remain unavailable rather
    than being interpreted by a substring classifier. No assertion is consulted.
    """
    public = get_ops_contract_renewal_pipeline_task()
    user = lambda messages: [item for item in messages if item.get("role") == "user"]
    if user(prompt) != user(public["prompt"]):
        raise ValueError("renewal_exact_public_request_unresolved")
    today = date(2026, 2, 9)  # The bound public request explicitly supplies this date.
    if not str(initial.get("meta", {}).get("current_time", "")).startswith(today.isoformat() + "T"):
        raise ValueError("renewal_public_clock_conflict")
    if boundary is not None and not boundary.revision:
        raise ValueError("renewal_boundary_contract_revision_required")
    rows = sheet_rows(initial, "ss_contracts", "ws_policy")
    baseline = sheet_rows(public["info"]["initial_state"], "ss_contracts", "ws_policy")
    declared = [(row["cells"].get("Policy Item"), dict(row["cells"])) for row in rows]
    expected = [(row["cells"].get("Policy Item"), dict(row["cells"])) for row in baseline]
    if sorted(declared, key=str) != sorted(expected, key=str):
        raise ValueError("renewal_public_policy_grammar_unresolved")
    templates = initial.get("docusign", {}).get("templates", ())
    matching_templates = [
        item for item in templates if item.get("name") == "Vendor Contract Renewal"
    ]
    if len(matching_templates) != 1 or not isinstance(matching_templates[0].get("id"), str):
        raise ValueError("renewal_template_identity_unresolved")
    template = matching_templates[0]["id"]
    initial_envelopes = initial.get("docusign", {}).get("envelopes", ())
    if period is not None:
        ids = period.current_envelope_ids + period.prior_period_envelope_ids
        if (
            not period.revision
            or period.task_date != today
            or len(ids) != len(set(ids))
            or any(
                len([envelope for envelope in initial_envelopes if envelope.get("id") == identity])
                != 1
                for identity in ids
            )
        ):
            raise ValueError("renewal_period_contract_binding_unresolved")
    registry = sheet_rows(initial, "ss_contracts", "ws_active")
    emails = [row["cells"].get("Contact Email") for row in registry]
    vendors = []
    for row in registry:
        cells = row["cells"]
        vendor, email = cells.get("Vendor"), cells.get("Contact Email")
        if not isinstance(vendor, str) or not vendor or not isinstance(email, str) or not email:
            raise ValueError("renewal_vendor_identity_unresolved")
        eligible, reason = None, "renewal_row_semantics_unresolved"
        if emails.count(email) != 1:
            reason = "renewal_contact_ambiguous"
        elif cells.get("Status") in {"Renewed", "Terminated"}:
            eligible, reason = False, "not_active"
        elif cells.get("Status") != "Active":
            reason = "renewal_status_grammar_unresolved"
        elif cells.get("Auto-Renew") == "Yes":
            eligible, reason = False, "auto_renew"
        elif cells.get("Auto-Renew") != "No":
            reason = "renewal_auto_renew_grammar_unresolved"
        elif cells.get("Notes") == "under legal dispute - renewal hold until dispute resolution":
            eligible, reason = False, "public_legal_hold"
        elif cells.get("Notes") != "":
            reason = "renewal_notes_semantics_unresolved"
        else:
            try:
                expiry = datetime.strptime(cells["Expiry"], "%m/%d/%Y").replace(tzinfo=UTC).date()
            except (ValueError, TypeError, KeyError):
                reason = "renewal_expiry_unresolved"
            else:
                days = (expiry - today).days
                if days in {0, 60} and boundary is None:
                    reason = "renewal_date_equality_contract_required"
                else:
                    eligible = (
                        0 < days < 60
                        or days == 0
                        and boundary is not None
                        and boundary.include_expiry_day
                        or days == 60
                        and boundary is not None
                        and boundary.include_window_day
                    )
                    reason = "within_public_window" if eligible else "outside_public_window"
        matching = [
            envelope
            for envelope in initial_envelopes
            if envelope.get("template_id") == template
            and envelope.get("status") in {"sent", "completed", "signed"}
            and [signer.get("email") for signer in envelope.get("signers", ())] == [email]
        ]
        current = period.current_envelope_ids if period is not None else ()
        prior = period.prior_period_envelope_ids if period is not None else ()
        already = (
            True
            if any(envelope.get("id") in current for envelope in matching)
            else (None if any(envelope.get("id") not in prior for envelope in matching) else False)
        )
        vendors.append(RenewalVendor(str(row["row_id"]), vendor, email, eligible, reason, already))
    return RenewalPolicy(
        today,
        60,
        template,
        tuple(vendors),
        canonical_json(declared),
        boundary.revision if boundary is not None else None,
        _source_projection(initial),
        period.revision if period is not None else None,
    )


def _source_projection(world: Mapping) -> str:
    """Initial public registry/policy are normative; live edits are not authority."""
    return canonical_json(
        {
            worksheet: sorted(
                [
                    (str(row["row_id"]), dict(row["cells"]))
                    for row in sheet_rows(world, "ss_contracts", worksheet)
                ],
                key=lambda row: row[0],
            )
            for worksheet in ("ws_active", "ws_policy")
        }
    )


def renewal_findings(index: EffectIndex, policy: RenewalPolicy) -> tuple[Finding, ...]:
    """Deduplicate per-vendor accomplishments; retain each observed harmful send.

    Zero accomplishment requires a qualified captured DocuSign chain. It is not
    evidence of a complete invocation inventory. Positive effects remain local
    facts even when unrelated capture is unavailable. Neutral coverage is kept
    separate and must never become action credit.
    """
    effects = envelope_sends(index)
    coverage = index.service_history(("docusign",)).captured_scope_qualified and all(
        effect.status == "qualified" for effect in effects
    )
    findings = [
        Finding(
            "renewal.recording_coverage",
            float(coverage) if coverage else None,
            "captured_docusign_chain_qualified"
            if coverage
            else "captured_docusign_scope_unresolved",
        )
    ]
    drift = False
    source_available = bool(index.occurrences)
    for item in index.occurrences:
        for snapshot in (item.before_json, item.after_json):
            try:
                if snapshot is None:
                    raise ValueError("renewal_source_snapshot_unavailable")
                drift = (
                    drift
                    or _source_projection(index.world(snapshot)) != policy.source_projection_json
                )
            except (ValueError, TypeError, KeyError):
                source_available = False
    source_preserved = source_available and not drift
    findings.append(
        Finding(
            "renewal.live_source_drift",
            1.0 if drift else 0.0 if source_available else None,
            "initial_public_registry_remains_normative_live_drift_observed"
            if drift
            else "captured_registry_and_policy_preserved"
            if source_available
            else "source_projection_unavailable",
        )
    )
    successful: dict[str, list[str]] = {vendor.email: [] for vendor in policy.vendors}
    by_email = {vendor.email: vendor for vendor in policy.vendors}
    for effect in effects:
        if effect.status != "qualified" or effect.envelope is None:
            findings.append(
                Finding(
                    "renewal.send_effect:" + effect.invocation_id,
                    None,
                    effect.reason,
                    effect.invocation_id,
                )
            )
            continue
        envelope = effect.envelope
        signers = tuple(signer["email"] for signer in envelope["signers"])
        for email in signers:
            vendor = by_email.get(email)
            key = "renewal.forbidden_send:" + effect.invocation_id + ":" + email
            if vendor is None:
                # An unrelated DocuSign send is outside this renewal predicate.
                if envelope.get("template_id") == policy.template_id:
                    findings.append(
                        Finding(
                            key,
                            1.0,
                            "renewal_recipient_not_in_public_registry",
                            effect.invocation_id,
                        )
                    )
                continue
            if vendor.eligible is None:
                findings.append(Finding(key, None, vendor.reason, effect.invocation_id))
            elif not vendor.eligible or vendor.already_sent:
                findings.append(
                    Finding(
                        key,
                        1.0,
                        "already_processed" if vendor.already_sent else vendor.reason,
                        effect.invocation_id,
                    )
                )
            elif envelope.get("template_id") != policy.template_id:
                findings.append(Finding(key, 1.0, "wrong_renewal_template", effect.invocation_id))
            elif signers != (email,):
                findings.append(
                    Finding(
                        key, None, "renewal_multiple_signer_contract_required", effect.invocation_id
                    )
                )
            else:
                successful[email].append(effect.invocation_id)
    chain = index.serial_chain()
    order = {item.invocation_id: position for position, item in enumerate(chain.ordered)}
    for vendor in policy.vendors:
        key = "renewal.agreement_sent:" + vendor.row_id
        if vendor.already_sent is None:
            findings.append(
                Finding(
                    "renewal.historical_period_unbound:" + vendor.row_id,
                    None,
                    "initial_matching_envelope_period_contract_required",
                )
            )
        if vendor.eligible is None:
            findings.append(Finding(key, None, vendor.reason))
        elif not vendor.eligible or vendor.already_sent:
            findings.append(
                Finding(
                    key,
                    0.0,
                    "already_correct_no_progress"
                    if vendor.already_sent
                    else "not_a_renewal_obligation",
                )
            )
        elif successful[vendor.email]:
            ids = successful[vendor.email]
            occurrence = (
                min(ids, key=order.__getitem__)
                if chain.status == "qualified"
                else ids[0]
                if len(ids) == 1
                else None
            )
            if not source_preserved or vendor.already_sent is None:
                occurrence = None
            findings.append(
                Finding(key, 1.0, "acknowledged_correct_template_and_signer", occurrence)
            )
        else:
            findings.append(
                Finding(
                    key,
                    0.0 if coverage and vendor.already_sent is not None else None,
                    "no_observed_qualifying_send" if coverage else "send_coverage_unresolved",
                )
            )
    delivered = [
        notice
        for notice in notifications(index)
        if notice.status == "qualified"
        and notice.kind == "send"
        and policy.procurement_email in notice.recipients
    ]
    findings.append(
        Finding(
            "renewal.procurement_delivery",
            1.0 if delivered else None,
            "acknowledged_procurement_delivery_only"
            if delivered
            else "procurement_delivery_not_established",
            delivered[0].invocation_id if len(delivered) == 1 and source_preserved else None,
        )
    )
    findings.append(
        Finding(
            "renewal.procurement_summary_correctness", None, "summary_semantic_contract_required"
        )
    )
    return tuple(findings)
