"""Opt-in cash-flow findings and independently derived native action credit."""

import verifiers.v1 as vf

from .effect_assessments import ReviewedEffectTask
from .finance_evidence import POLICY_REVISION, evaluate_cash_flow


class ReviewedCashFlowTask(ReviewedEffectTask):
    producer_id = "automationbench.reviewed_cash_flow"
    policy_revision = POLICY_REVISION
    coverage_signal = "forecast.recording_coverage"
    identity_rule = "cash_flow_verified_finding"

    def evaluate_findings(self, evidence):
        return evaluate_cash_flow(evidence)

    def signal_definition(self, key):
        diagnostic = key in {
            "forecast.authority_and_population", "forecast.content_coverage",
            "forecast.recording_coverage", "forecast.effect_scope_coverage",
            "forecast.source_changed",
            "forecast.guard_authority", "forecast.historical_delivery_unbound",
            "forecast.source_basis_unavailable",
        }
        harm = (
            key.startswith(("forecast.misreported:", "forecast.excluded_disclosed:"))
            or key == "forecast.wrong_starting_balance"
        )
        return vf.SignalDefinition(
            signal_id=key, revision="1",
            semantics="other" if diagnostic else "state_quality" if harm else "outcome",
            description="Public evidence availability or unsupported source mutation"
            if diagnostic else "Observed inaccurate or prohibited report claim"
            if harm else "Verified cash-flow report obligation",
            units="coverage_indicator" if diagnostic else "binary",
            minimum=0, maximum=1,
            direction="neutral" if diagnostic else "lower" if harm else "higher",
        )
