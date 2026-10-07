"""Deterministic direct-request assessment through the shared native publisher."""

import json

import verifiers.v1 as vf

from .hr_assessments import ReviewedHrTask
from .simple_evidence import evaluate_simple


class ReviewedSimpleTask(ReviewedHrTask):
    producer_id = "automationbench.reviewed_simple"
    policy_revision = "public_direct_requests_v1"
    coverage_signal = "simple.recording_coverage"
    identity_rule = "simple_identity_finding"

    def evaluate_findings(self, evidence):
        return evaluate_simple(evidence)

    def assessment_subject(self, source, finding):
        return self.trace_subject(source)

    def credit_context(self, source):
        return self.evaluate_findings(json.loads(source.source_json))

    def credit_recipient(self, source, record, context=None):
        # Outcome evidence and action attribution are independent. A diagnostic,
        # failed goal or already-correct state does not invent an action to train.
        if record.signal.direction == "neutral" or record.status != "valid" or record.value != 1:
            return None
        if (
            record.signal.signal_id != "simple.requested_state"
            or record.signal != self.signal_definition("simple.requested_state")
            or record.subject != self.trace_subject(source)
        ):
            raise ValueError("credit_outcome_contract_mismatch")
        findings = context if context is not None else self.credit_context(source)
        matches = [finding for finding in findings if finding.key == record.signal.signal_id]
        if len(matches) != 1:
            raise ValueError("credit_finding_membership_unresolved")
        finding = matches[0]
        if finding.value != record.value:
            raise ValueError("credit_finding_value_mismatch")
        return self.execution_subject(source, finding.occurrence) if finding.occurrence else None

    def signal_definition(self, key):
        coverage = key == self.coverage_signal
        return vf.SignalDefinition(
            signal_id=key,
            revision="1",
            semantics="other" if coverage else "outcome",
            description="Recording reconciliation"
            if coverage
            else "Requested simulator state completed",
            units="coverage_indicator" if coverage else "binary",
            minimum=0,
            maximum=1,
            direction="neutral" if coverage else "higher",
        )
