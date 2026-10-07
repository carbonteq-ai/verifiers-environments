"""Opt-in development HR assessments; official AutomationBench reward is unchanged.

Select ReviewedHrTask explicitly. Retrospective views contain public policy/world
facts and native receipts, not hidden assertions. Numeric identity assignment keeps
goal and harm channels separate; algorithms still own weighting and advantages.
"""

import json
import uuid
from typing import cast

import verifiers.v1 as vf

from .hr_evidence import evaluate
from .hr_rules import Finding
from .manifest_source import trace_finalized
from .taskset import AutomationBenchTask
from .tools import AutomationBenchState


class ReviewedHrTask(AutomationBenchTask):
    """Explicit alternative task class for the three reviewed policy revisions."""

    producer_id = "automationbench.reviewed_hr"
    producer_revision = "1"
    policy_revision = "public_hr_policy_v1"
    coverage_signal = "hr.coverage"
    identity_rule = "hr_identity_finding"

    def evaluate_findings(self, evidence):
        return evaluate(evidence)

    def signal_definition(self, key):
        return _signal(key)

    def execution_subject(self, source, occurrence):
        refs = [
            ref
            for ref in source.executions
            if ref.origin == "tool_server" and ref.invocation_id == occurrence
        ]
        if len(refs) != 1:
            raise ValueError("execution_membership_unresolved")
        return vf.SubjectRef(
            kind="execution",
            snapshot_id=source.snapshot_id,
            episode_id=source.episode_id,
            trace_id=refs[0].trace_id,
            execution=refs[0],
        )

    def trace_subject(self, source):
        return vf.SubjectRef(
            kind="trace",
            snapshot_id=source.snapshot_id,
            episode_id=source.episode_id,
            trace_id=json.loads(source.source_json)["trace_id"],
        )

    def assessment_subject(self, source, finding):
        return (
            self.execution_subject(source, finding.occurrence)
            if finding.occurrence
            else self.trace_subject(source)
        )

    def credit_context(self, source) -> object | None:
        return None

    def credit_recipient(self, source, record, context=None):
        return None if record.signal.direction == "neutral" else record.subject

    def assessment_source(self, trace):
        retained = trace.info.get("automationbench", {})
        # Avoid evaluating an unavailable legacy State fallback on loaded traces.
        final = (
            retained["end_state"]
            if "end_state" in retained
            else cast(AutomationBenchState, trace.state).world
        )
        return {
            "task_name": self.data.task_name,
            "initial": self.data.initial_state,
            "final": final,
            "prompt": self.data.model_dump(mode="json")["prompt"],
            "complete": trace_finalized(trace),
        }

    def assessment_requests(self, source):
        raw = json.loads(source.source_json)
        safe = {
            "task_evidence": raw["task_evidence"],
            "tool_execution_events": raw.get("tool_execution_events", []),
            "state_write_receipts": raw.get("state_write_receipts", []),
        }
        try:
            findings = self.evaluate_findings(safe)
        except (ValueError, KeyError, TypeError) as error:
            safe["adapter_unavailable"] = type(error).__name__
            findings = (Finding(self.coverage_signal, None, "evidence_or_policy_unresolved"),)
        if not findings:
            findings = (Finding(self.coverage_signal, None, "policy_or_action_scope_unavailable"),)
            safe["empty_scope"] = True
        subjects = {}
        for finding in findings:
            subject = self.assessment_subject(source, finding)
            subjects[(finding.key, finding.occurrence)] = subject
        view = vf.ObservationView.capture(
            safe,
            snapshot_id=source.snapshot_id,
            builder_revision=self.policy_revision,
            scope="retrospective",
            subjects=tuple(dict.fromkeys(subjects.values())),
        )
        expected = tuple(
            vf.AssessmentTarget(
                subject=subjects[(f.key, f.occurrence)], signal=self.signal_definition(f.key)
            )
            for f in findings
        )
        invocation = uuid.uuid4().hex
        run = vf.AssessmentRun(
            run_id=invocation,
            producer_id=self.producer_id,
            producer_revision=self.producer_revision,
            rubric_revision=self.policy_revision,
            snapshot_id=source.snapshot_id,
            invocation_id=invocation,
            attempt_id=uuid.uuid4().hex,
            expected=expected,
        )
        return [
            ("reviewed_hr", vf.AssessmentRequest(source=source.identity, run=run, views=(view,)))
        ]

    @vf.assessment
    async def reviewed_hr(self, request: vf.AssessmentRequest):
        view = request.views[0]
        assert view.input_json is not None
        raw = json.loads(view.input_json)
        findings = (
            (Finding(self.coverage_signal, None, "evidence_or_policy_unresolved"),)
            if raw.get("adapter_unavailable")
            else (Finding(self.coverage_signal, None, "policy_or_action_scope_unavailable"),)
            if raw.get("empty_scope")
            else self.evaluate_findings(raw)
        )
        records = []
        for finding, target in zip(findings, request.run.expected, strict=True):
            records.append(
                vf.Assessment(
                    assessment_id=uuid.uuid4().hex,
                    run_id=request.run.run_id,
                    subject=target.subject,
                    view_id=view.view_id,
                    signal=target.signal,
                    status="valid" if finding.value is not None else "abstained",
                    value=finding.value,
                    reason=finding.reason,
                )
            )
        return tuple(records)

    def plan_credit(self, source, assessments, context):
        if context.source != source.identity:
            raise ValueError("credit_planning_source_mismatch")
        current = {
            (run.run_id, run.attempt_id, run.invocation_id)
            for run in context.current_assessment_runs
        }
        selected = tuple(
            batch
            for batch in assessments
            if (batch.run.run_id, batch.run.attempt_id, batch.run.invocation_id) in current
        )
        planned = self.credit_requests(source, selected)
        retained = []
        for hook, request in planned:
            consumed = False
            for assignment in context.prior_assignments:
                if (
                    assignment.request.source.snapshot_id != source.snapshot_id
                    or assignment.request.rule != request.rule
                ):
                    continue
                for contribution in assignment.contributions:
                    if contribution.status != "valid":
                        continue
                    if not any(
                        target.recipient == contribution.recipient
                        and target.channel == contribution.channel
                        for target in request.targets
                    ):
                        continue
                    record = request.accepted[0]
                    if contribution.signal != record.signal or contribution.value != record.value:
                        raise ValueError("credit_prior_assignment_conflict")
                    consumed = True
            if not consumed:
                retained.append((hook, request))
        return retained

    def credit_requests(self, source, assessments):
        requests = []
        seen = set()
        selected = [
            batch
            for batch in assessments
            if batch.run.producer_id == self.producer_id
            and batch.run.producer_revision == self.producer_revision
            and batch.run.rubric_revision == self.policy_revision
            and batch.run.status in ("complete", "partial")
            and batch.source.snapshot_id == source.snapshot_id
        ]
        # This deterministic producer accepts one assessment attempt per source.
        # Independent attempts are not additional domain accomplishments. A
        # deliberate supersession needs an explicit selection policy, not arrival
        # order or an implicit maximum score.
        if len({batch.run.run_id for batch in selected}) > 1:
            raise ValueError("credit_assessment_attempt_selection_unresolved")
        records_by_id = {}
        context_ready = False
        context = None
        for batch in selected:
            if not context_ready:
                context = self.credit_context(source)
                context_ready = True
            for record in batch.assessments:
                # Native retention includes progress snapshots of the same run.
                # They are evidence history, not additional reward observations.
                if record.assessment_id in seen:
                    if records_by_id[record.assessment_id] != record:
                        raise ValueError("credit_assessment_history_conflict")
                    continue
                seen.add(record.assessment_id)
                records_by_id[record.assessment_id] = record
                recipient = self.credit_recipient(source, record, context)
                if recipient is None:
                    continue
                channel = record.signal.signal_id
                requests.append(
                    (
                        "reviewed_hr_identity",
                        vf.CreditRequest(
                            source=source.identity,
                            invocation_id=uuid.uuid4().hex,
                            attempt_id=uuid.uuid4().hex,
                            rule=vf.CreditRule(rule_id=self.identity_rule, revision="1"),
                            accepted=(record,),
                            targets=(vf.CreditTarget(recipient=recipient, channel=channel),),
                            allocation="turn_boundary",
                            overlap_policy="reject",
                        ),
                    )
                )
        return requests

    @vf.credit
    async def reviewed_hr_identity(self, request: vf.CreditRequest):
        record = request.accepted[0]
        target = request.targets[0]
        contribution = vf.CreditContribution(
            contribution_id=uuid.uuid4().hex,
            parent_assessment_ids=(record.assessment_id,),
            recipient=target.recipient,
            channel=target.channel,
            signal=record.signal,
            transformation="identity_domain_finding_v1",
            status="valid" if record.status == "valid" else "unavailable",
            value=record.value,
            allocation=request.allocation,
            attribution="coarse" if record.status == "valid" else None,
            reason=record.reason,
        )
        return (contribution,)


def _signal(key):
    if key == "hr.coverage":
        return vf.SignalDefinition(
            signal_id=key,
            revision="1",
            semantics="other",
            description="Retained action evidence availability",
            units="coverage_indicator",
            minimum=0,
            maximum=1,
            direction="neutral",
        )
    harm = not key.startswith("nda.completed:")
    return vf.SignalDefinition(
        signal_id=key,
        revision="1",
        semantics="state_quality" if harm else "outcome",
        description="Observed policy harm" if harm else "Per employee NDA accomplishment",
        units="binary",
        minimum=0,
        maximum=1,
        direction="lower" if harm else "higher",
    )
