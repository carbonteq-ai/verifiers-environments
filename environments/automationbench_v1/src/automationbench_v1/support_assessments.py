"""Explicitly configured bounded support assessments through the native publisher.

No default task-level authority is inferred from successful traces. Composition
must supply and review a source-bound contract. Development proposals abstain;
reviewed bounded contracts assess their named predicate only, never full refund
eligibility, digest counts, category precedence or whole-task completion.
"""

from __future__ import annotations

import json
from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field, model_validator

from automationbench.domains.support.tasks import (
    get_support_gorgias_refund_processing_task,
    get_support_hiver_slack_digest_task,
)

from .calibration.inventory import content_digest
from .capture import canonical_json
from .effect_evidence import world_transitions
from .effect_index import EffectIndex
from .hr_assessments import ReviewedHrTask
from .hr_rules import Finding
from .notification_evidence import sheet_rows
from .support_evidence import digest_log_claims, jira_creation_coverage, jira_creations
from .support_rules import (
    DigestClaimContract,
    ReviewObligation,
    escalation_accomplishments,
    join_refund_order,
)
from .taskset import AutomationBenchData, AutomationBenchTaskConfig

GORG = "support.gorgias_refund_processing"
HIVER = "support.hiver_slack_digest"
SUPPORTED = frozenset({GORG, HIVER})


def public_support_source_digest(data: AutomationBenchData) -> str:
    """Public messages and starting world; hidden assertions are excluded."""
    return content_digest(
        {
            "task_name": data.task_name,
            "prompt": data.model_dump(mode="json")["prompt"],
            "initial": data.initial_state,
        }
    )


class SupportAssessmentContract(BaseModel):
    """Versioned composition review, not authentication by a self-authored hash."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    schema_version: Literal[1] = 1
    task_name: Literal["support.gorgias_refund_processing", "support.hiver_slack_digest"]
    public_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_revision: str = Field(min_length=1)
    disposition: Literal["development_proposal", "reviewed_bounded"]
    review_obligations: tuple[ReviewObligation, ...] = ()
    digest_claims: DigestClaimContract | None = None
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_contract(self):
        if self.task_name == GORG and (
            not self.review_obligations or self.digest_claims is not None
        ):
            raise ValueError("gorgias_contract_requires_explicit_review_obligations")
        if self.task_name == HIVER and (self.digest_claims is None or self.review_obligations):
            raise ValueError("hiver_contract_requires_explicit_claim_meanings")
        if self.digest != content_digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("support_contract_digest_mismatch")
        return self


class SupportTaskConfig(AutomationBenchTaskConfig):
    """Optional explicit contract; absence cannot select inferred reward meaning."""

    support_contract: SupportAssessmentContract | None = None


def capture_support_contract(data: AutomationBenchData, **review) -> SupportAssessmentContract:
    """Prepare review input; choosing disposition remains composition's decision."""
    # Normalize native dataclasses before sealing their serialized contract.
    provisional = {
        "schema_version": 1,
        "task_name": data.task_name,
        "public_source_digest": public_support_source_digest(data),
        **review,
    }
    draft = SupportAssessmentContract.model_construct(**provisional, digest="0" * 64)
    body = draft.model_dump(mode="json", exclude={"digest"})
    return SupportAssessmentContract.model_validate({**body, "digest": content_digest(body)})


class ReviewedSupportTask(ReviewedHrTask):
    producer_id = "automationbench.reviewed_support"
    policy_revision = "bounded_support_contract_required_v1"
    coverage_signal = "support.recording_coverage"
    identity_rule = "support_verified_bounded_finding"

    def __init__(self, data: AutomationBenchData, config: SupportTaskConfig | None = None):
        configured = config or SupportTaskConfig()
        super().__init__(data, configured)
        self.support_contract = configured.support_contract
        if self.support_contract is not None:
            # Detached checked copy prevents mutable nested inputs from silently
            # changing the predicate while retaining its rubric revision.
            self.support_contract = SupportAssessmentContract.model_validate_json(
                self.support_contract.model_dump_json()
            )
            self.policy_revision = "bounded_support_v1:" + self.support_contract.digest

    def assessment_source(self, trace):
        source = super().assessment_source(trace)
        source["support_contract"] = (
            self.support_contract.model_dump(mode="json") if self.support_contract else None
        )
        return source

    def _contract(self, evidence) -> SupportAssessmentContract | None:
        raw = evidence["task_evidence"]
        if raw["task_name"] not in SUPPORTED:
            raise ValueError("unsupported_bounded_support_task")
        if self.support_contract is None:
            if raw.get("support_contract") is not None:
                raise ValueError("support_contract_not_selected_by_composition")
            return None
        contract = SupportAssessmentContract.model_validate_json(
            self.support_contract.model_dump_json()
        )
        if raw.get("support_contract") != contract.model_dump(mode="json"):
            raise ValueError("support_source_contract_differs_from_selected_contract")
        public = {"task_name": raw["task_name"], "prompt": raw["prompt"], "initial": raw["initial"]}
        if (
            contract.task_name != raw["task_name"]
            or content_digest(public) != contract.public_source_digest
        ):
            raise ValueError("support_public_source_contract_mismatch")
        factory = (
            get_support_gorgias_refund_processing_task
            if raw["task_name"] == GORG
            else get_support_hiver_slack_digest_task
        )
        approved_user = [item for item in factory()["prompt"] if item["role"] == "user"]
        actual_user = [item for item in raw["prompt"] if item["role"] == "user"]
        if actual_user != approved_user:
            raise ValueError("support_exact_public_request_unresolved")
        initial = raw["initial"]
        if contract.task_name == GORG:
            tickets = initial.get("gorgias", {}).get("tickets", ())
            rows = sheet_rows(initial, "ss_refund_policy", "ws_orders")
            for obligation in contract.review_obligations:
                matching = [
                    ticket for ticket in tickets if ticket.get("id") == obligation.order.ticket_id
                ]
                if len(matching) != 1 or join_refund_order(matching[0], rows) != obligation.order:
                    raise ValueError("support_review_order_public_binding_unresolved")
                if (
                    not initial.get("meta", {})
                    .get("current_time", "")
                    .startswith(obligation.task_window + "T")
                ):
                    raise ValueError("support_review_task_window_unresolved")
        else:
            claims = contract.digest_claims
            assert claims is not None
            recipients = sheet_rows(initial, "ss_digest", "ws_recipients")
            categories = [category for category, _ in claims.recipients]
            if len(set(categories)) != len(categories) or any(
                [
                    row["cells"].get("Recipient_Email")
                    for row in recipients
                    if row["cells"].get("Category") == category
                ]
                != [recipient]
                for category, recipient in claims.recipients
            ):
                raise ValueError("support_digest_recipient_public_binding_unresolved")
            config = sheet_rows(initial, "ss_digest", "ws_config")
            identities = [
                row["cells"].get("Value")
                for row in config
                if row["cells"].get("Key") == "digest_id"
            ]
            if identities != [claims.digest_id] or not initial.get("meta", {}).get(
                "current_time", ""
            ).startswith(claims.digest_date + "T"):
                raise ValueError("support_digest_date_or_identity_public_binding_unresolved")
        return contract

    def evaluate_findings(self, evidence):
        contract = self._contract(evidence)
        if contract is None:
            return (
                Finding("support.contract_binding", None, "explicit_support_contract_required"),
            )
        if contract.disposition != "reviewed_bounded":
            return (
                Finding("support.contract_binding", None, "development_contract_requires_review"),
            )
        index = EffectIndex(world_transitions(evidence))
        chain = index.serial_chain()
        raw = evidence["task_evidence"]
        reconciled = (
            raw.get("complete") is True
            and chain.status == "qualified"
            and chain.revision_interval is not None
            and chain.revision_interval[0] == 0
            and chain.ordered[-1].after_json == canonical_json(raw["final"])
        )
        diagnostics = (
            Finding("support.contract_binding", 1.0, "explicit_reviewed_bounded_contract"),
            Finding(
                self.coverage_signal,
                1.0 if reconciled else None,
                "captured_chain_and_final_world_reconciled"
                if reconciled
                else "recording_or_finalization_unresolved",
            ),
        )
        if contract.task_name == GORG:
            effects = jira_creations(index)
            covered = reconciled and jira_creation_coverage(index, effects)
            results = escalation_accomplishments(
                effects, contract.review_obligations, ordered_coverage=covered
            )
            return tuple(result.finding for result in results) + diagnostics
        claims = digest_log_claims(index, contract.digest_claims)
        return tuple(claim.finding for claim in claims) + diagnostics

    def signal_definition(self, key):
        diagnostic = key in {"support.contract_binding", self.coverage_signal}
        harm = key.startswith("hiver.premature_completed_claim:")
        if not diagnostic and not harm and not key.startswith("gorgias.review_accomplishment:"):
            raise ValueError("unsupported_support_signal")
        return vf.SignalDefinition(
            signal_id=key,
            revision="1",
            semantics="other" if diagnostic else "state_quality" if harm else "outcome",
            description="Explicit contract or captured-chain availability"
            if diagnostic
            else "Completed-send claim lacks prior bounded delivery evidence"
            if harm
            else "One explicitly reviewed Jira escalation accomplishment",
            units="coverage_indicator" if diagnostic else "binary",
            minimum=0,
            maximum=1,
            direction="neutral" if diagnostic else "lower" if harm else "higher",
        )

    def assessment_subject(self, source, finding):
        if finding.key.startswith("hiver.premature_completed_claim:") and finding.occurrence:
            return self.execution_subject(source, finding.occurrence)
        return self.trace_subject(source)

    def credit_context(self, source):
        return self.evaluate_findings(json.loads(source.source_json))

    def credit_recipient(self, source, record, context=None):
        if record.signal.direction == "neutral" or record.status != "valid" or record.value != 1:
            return None
        if record.signal != self.signal_definition(record.signal.signal_id):
            raise ValueError("support_credit_signal_contract_mismatch")
        findings = context if context is not None else self.credit_context(source)
        matching = [
            finding
            for finding in findings
            if finding.key == record.signal.signal_id
            and self.assessment_subject(source, finding) == record.subject
        ]
        if len(matching) != 1 or matching[0].value != record.value:
            raise ValueError("support_credit_finding_membership_unresolved")
        return (
            self.execution_subject(source, matching[0].occurrence)
            if matching[0].occurrence
            else None
        )
