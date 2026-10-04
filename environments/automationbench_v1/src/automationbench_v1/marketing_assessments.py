"""Opt-in suppression assessments; official scores and algorithm weights stay separate."""

import verifiers.v1 as vf

from .effect_assessments import ReviewedEffectTask
from .marketing_evidence import POLICY_REVISION, evaluate_suppression


class ReviewedSuppressionTask(ReviewedEffectTask):
    producer_id = "automationbench.reviewed_suppression"
    policy_revision = POLICY_REVISION
    coverage_signal = "suppression.recording_coverage"
    identity_rule = "suppression_verified_finding"

    def evaluate_findings(self, evidence):
        return evaluate_suppression(evidence)

    def signal_definition(self, key):
        diagnostic = key in {
            "suppression.authority_and_population",
            "suppression.recording_coverage",
            "suppression.effect_scope_coverage",
        }
        harm = (
            key.startswith("suppression.prohibited_archive:")
            or key == "suppression.unauthorized_summary_recipient"
        )
        return vf.SignalDefinition(
            signal_id=key,
            revision="1",
            semantics="other" if diagnostic else "state_quality" if harm else "outcome",
            description="Public policy and recording availability"
            if diagnostic
            else "Observed prohibited effect"
            if harm
            else "Verified suppression obligation",
            units="coverage_indicator" if diagnostic else "binary",
            minimum=0,
            maximum=1,
            direction="neutral" if diagnostic else "lower" if harm else "higher",
        )
