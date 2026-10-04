"""Bounded native renewal findings; summary semantics remain explicitly unavailable."""

import verifiers.v1 as vf

from .effect_assessments import ReviewedEffectTask
from .effect_evidence import world_transitions
from .effect_index import EffectIndex
from .operations_access_evidence import evaluate_access
from .operations_renewal_evidence import compile_renewal_policy, renewal_findings

RENEWAL_TASK = "operations.contract_renewal_pipeline"
ACCESS_TASK = "operations.access_request_validation"


class ReviewedAccessTask(ReviewedEffectTask):
    producer_id = "automationbench.reviewed_access"
    policy_revision = "public_frozen_initial_access_routing_v1"
    coverage_signal = "access.recording_coverage"
    identity_rule = "access_verified_finding"

    def evaluate_findings(self, evidence):
        return evaluate_access(evidence)

    def signal_definition(self, key):
        diagnostic = key in {
            "access.authority_and_population", "access.recording_coverage",
            "access.effect_scope_coverage",
        } or key.startswith("access.processing_state:")
        harm = key.startswith((
            "access.reprocessed:", "access.insufficient_approver:", "access.incorrect_denial:",
        ))
        return vf.SignalDefinition(
            signal_id=key, revision="1",
            semantics="other" if diagnostic else "state_quality" if harm else "outcome",
            description="Access source and effect availability" if diagnostic
            else "Observed prohibited access decision" if harm
            else "Verified access routing obligation",
            units="coverage_indicator" if diagnostic else "binary",
            minimum=0, maximum=1,
            direction="neutral" if diagnostic else "lower" if harm else "higher",
        )


class ReviewedRenewalTask(ReviewedEffectTask):
    producer_id = "automationbench.reviewed_renewal"
    policy_revision = "public_frozen_initial_manual_renewals_v1"
    coverage_signal = "renewal.recording_coverage"
    identity_rule = "renewal_verified_finding"

    def evaluate_findings(self, evidence):
        task = evidence["task_evidence"]
        if task["task_name"] != RENEWAL_TASK:
            raise ValueError("unsupported_reviewed_renewal_task")
        policy = compile_renewal_policy(task["initial"], task["prompt"])
        return renewal_findings(EffectIndex(world_transitions(evidence)), policy)

    def signal_definition(self, key):
        diagnostic = (
            key in {"renewal.recording_coverage", "renewal.live_source_drift"}
            or key.startswith(("renewal.historical_period_unbound:", "renewal.send_effect:"))
        )
        harm = key.startswith("renewal.forbidden_send:")
        return vf.SignalDefinition(
            signal_id=key, revision="1",
            semantics="other" if diagnostic else "state_quality" if harm else "outcome",
            description="Renewal source and effect availability" if diagnostic
            else "Observed prohibited renewal send" if harm
            else "Bounded renewal obligation",
            units="coverage_indicator" if diagnostic else "binary",
            minimum=0, maximum=1,
            direction="neutral" if diagnostic else "lower" if harm else "higher",
        )
