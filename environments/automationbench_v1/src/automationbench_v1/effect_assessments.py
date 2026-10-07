"""Shared native transport for independently verified domain effect findings.

Domain evaluators own policy, coverage and which effect deserves attribution.
This base only rederives membership and publishes explicit learning recipients.
"""

import json

from .hr_assessments import ReviewedHrTask


class ReviewedEffectTask(ReviewedHrTask):
    """Trace outcomes and execution harms with independently derived credit."""

    def assessment_subject(self, source, finding):
        if self.signal_definition(finding.key).direction == "lower" and finding.occurrence:
            return self.execution_subject(source, finding.occurrence)
        return self.trace_subject(source)

    def credit_context(self, source):
        # The shared planner calls this once per invocation, never across sources.
        return self.evaluate_findings(json.loads(source.source_json))

    def credit_recipient(self, source, record, context=None):
        if record.signal.direction == "neutral" or record.status != "valid" or record.value != 1:
            return None
        if record.signal != self.signal_definition(record.signal.signal_id):
            raise ValueError("credit_outcome_contract_mismatch")
        findings = context if context is not None else self.credit_context(source)
        matched = [
            finding
            for finding in findings
            if finding.key == record.signal.signal_id
            and self.assessment_subject(source, finding) == record.subject
        ]
        if len(matched) != 1 or matched[0].value != record.value:
            raise ValueError("credit_finding_membership_unresolved")
        finding = matched[0]
        return self.execution_subject(source, finding.occurrence) if finding.occurrence else None
