"""Ten public record-update contracts through one native finding publisher."""

import verifiers.v1 as vf

from .effect_assessments import ReviewedEffectTask
from .simple_record_contracts import evaluate_simple_record_update


class ReviewedRecordUpdateTask(ReviewedEffectTask):
    producer_id = "automationbench.reviewed_record_update"
    policy_revision = "public_sf_opportunity_updates_v1"
    coverage_signal = "simple.recording_coverage"
    identity_rule = "record_update_verified_finding"

    def evaluate_findings(self, evidence):
        return evaluate_simple_record_update(evidence)

    def signal_definition(self, key):
        if key not in {"simple.requested_state", "simple.recording_coverage"}:
            raise ValueError("record_update_signal_unregistered")
        diagnostic = key == "simple.recording_coverage"
        return vf.SignalDefinition(
            signal_id=key, revision="1",
            semantics="other" if diagnostic else "outcome",
            description="Record update evidence availability" if diagnostic
            else "Exact public requested record state",
            units="coverage_indicator" if diagnostic else "binary",
            minimum=0, maximum=1,
            direction="neutral" if diagnostic else "higher",
        )
