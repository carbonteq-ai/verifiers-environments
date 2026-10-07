"""Manifest-selected AutomationBench checks through existing native records.

Every check gets a native run, so independent obligations can share a subject
and signal without changing their meaning or colliding on the native target key.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from typing import cast

import verifiers.v1 as vf

from .authored_output_source import build_authored_output_material
from .capture import canonical_json
from .contracts.credit import select_credit
from .contracts.engine import Evaluation, compile_contract, evaluate_contract, restore_evidence
from .contracts.evidence import capture_records
from .contracts.loader import canonical_contract_digest, load_contract, load_task_contract
from .contracts.models import CheckSpec, RecordSource
from .manifest_created_assessments import (
    CREATED_PRODUCER,
    assess_created,
    capture_created_inputs,
    created_requests,
    manifest_created_identity,
    plan_created_credit,
)
from .manifest_credit_history import assert_manifest_credit_revision
from .manifest_guard_assessments import (
    GUARD_PRODUCER,
    assess_guard,
    capture_guard_inputs,
    guard_requests,
    manifest_penalty,
    plan_guard_credit,
)
from .manifest_no_clarification_assessments import (
    NO_CLARIFICATION_PRODUCER,
    assess_no_clarification,
    no_clarification_requests,
)
from .manifest_obligation_assessments import (
    OBLIGATION_PRODUCER,
    assess_obligation,
    capture_obligation_inputs,
    manifest_obligation_identity,
    obligation_requests,
    plan_obligation_credit,
)
from .manifest_record_retained_assessments import (
    RECORD_RETAINED_PRODUCER,
    assess_record_retained,
    capture_record_retained_inputs,
    manifest_record_retained_identity,
    plan_record_retained_credit,
    record_retained_requests,
)
from .manifest_retained_assessments import (
    RETAINED_PRODUCER,
    assess_retained,
    capture_retained_inputs,
    manifest_retained_identity,
    plan_retained_credit,
    retained_requests,
)
from .manifest_source import admit_manifest_source, manifest_source_material, trace_finalized
from .manifest_summary_assessments import (
    SUMMARY_PRODUCER,
    SummaryBackend,
    assess_summary,
    summary_requests,
)
from .manifest_summary_credit import manifest_summary_penalty, plan_summary_credit
from .public_state import public_initial_state
from .taskset import AutomationBenchTask
from .tools import AutomationBenchState

OUTPUT_KIND = "automationbench.manifest_evaluation@1"
PRODUCER = "automationbench.manifest_checks"


def _validate_credit_overlap(requests):
    seen = set()
    for _, request in requests:
        for target in request.targets:
            execution = target.recipient.execution
            if execution is None:
                raise ValueError("manifest_execution_recipient_required")
            key = execution.occurrence_id, target.channel
            if key in seen:
                raise ValueError("manifest_credit_aggregation_required")
            seen.add(key)
    return requests


def _signal(check) -> vf.SignalDefinition:
    diagnostic = check.role == "diagnostic"
    return vf.SignalDefinition(
        signal_id=check.signal_id, revision="1",
        semantics="other" if diagnostic else "outcome",
        description="Manifest-declared evidence coverage" if diagnostic else "Manifest-declared record goal",
        units="coverage_indicator" if diagnostic else "binary", minimum=0, maximum=1,
        direction="neutral" if diagnostic else "higher",
    )


def _trace_subject(source) -> vf.SubjectRef:
    return vf.SubjectRef(
        kind="trace", snapshot_id=source.snapshot_id, episode_id=source.episode_id,
        trace_id=json.loads(source.source_json)["trace_id"],
    )


def _execution_subject(source, occurrence) -> vf.SubjectRef:
    matches = [item for item in source.executions
               if item.origin == "tool_server" and item.invocation_id == occurrence]
    if len(matches) != 1:
        raise ValueError("manifest_execution_membership_unresolved")
    return vf.SubjectRef(
        kind="execution", snapshot_id=source.snapshot_id, episode_id=source.episode_id,
        trace_id=matches[0].trace_id, execution=matches[0],
    )


def _source_material(source):
    return manifest_source_material(json.loads(source.source_json))


class ManifestAssessmentTask(AutomationBenchTask):
    """Installed catalog entries select task data; all tasks share this code."""

    summary_backends: dict[str, SummaryBackend]
    """Optional per-task registry bound by host composition, never by manifests."""

    no_clarification_backends: dict[str, SummaryBackend]
    """Independent producer selection for the outcome-only clarification guard."""

    def assessment_source(self, trace):
        state = cast(AutomationBenchState, trace.state)
        retained = trace.info.get("automationbench", {})
        final = retained.get("end_state", state.world)
        return {
            "task_name": self.data.task_name,
            "initial": public_initial_state(self.data.initial_state), "final": final,
            "prompt": self.data.model_dump(mode="json")["prompt"],
            "complete": trace_finalized(trace),
            "authored_outputs": build_authored_output_material(trace),
        }

    def assessment_requests(self, source):
        contract = load_task_contract(self.data.task_name)
        compile_contract(contract)
        safe = _source_material(source)
        record_sources = {key: spec for key, spec in contract.sources.items() if isinstance(spec, RecordSource)}
        evidence = capture_records(safe, record_sources)
        subject = _trace_subject(source)
        material = {
            "source": safe, "contract": contract.model_dump(mode="json"),
            "record_evidence_json": canonical_json({key: asdict(value) for key, value in evidence.items()}),
            **capture_guard_inputs(safe, contract),
            **capture_obligation_inputs(safe, contract),
            **capture_retained_inputs(safe, contract),
            **capture_created_inputs(safe, contract),
            **capture_record_retained_inputs(safe, contract),
        }
        view = vf.ObservationView.capture(
            material, snapshot_id=source.snapshot_id, builder_revision="automationbench.manifest_inputs@1",
            scope="retrospective", subjects=(subject, *(
                vf.SubjectRef(kind="execution", snapshot_id=source.snapshot_id,
                              episode_id=source.episode_id, trace_id=execution.trace_id,
                              execution=execution)
                for execution in source.executions if execution.origin == "tool_server"
            )),
        )
        requests = []
        for check in contract.checks:
            if not isinstance(check, CheckSpec):
                continue
            run = vf.AssessmentRun(
                run_id=uuid.uuid4().hex, producer_id=PRODUCER, producer_revision="1",
                rubric_revision=contract.revision, snapshot_id=source.snapshot_id,
                invocation_id=uuid.uuid4().hex, attempt_id=uuid.uuid4().hex,
                configuration_json=canonical_json({
                    "contract_digest": canonical_contract_digest(contract), "check_id": check.check_id,
                }),
                expected=(vf.AssessmentTarget(subject=subject, signal=_signal(check)),),
            )
            requests.append(("manifest_check", vf.AssessmentRequest(
                source=source.identity, run=run, views=(view,),
            )))
        requests.extend(guard_requests(source, contract, view, material, subject))
        requests.extend(summary_requests(source, contract, view))
        requests.extend(no_clarification_requests(source, contract, view))
        requests.extend(obligation_requests(source, contract, view, material, subject))
        requests.extend(retained_requests(source, contract, view, material, subject))
        requests.extend(created_requests(source, contract, view, material, subject))
        requests.extend(record_retained_requests(source, contract, view, material, subject))
        return requests

    @vf.credit
    async def manifest_penalty(self, request: vf.CreditRequest):
        return await manifest_penalty(self, request)

    @vf.credit
    async def manifest_obligation_identity(self, request: vf.CreditRequest):
        return await manifest_obligation_identity(self, request)

    @vf.credit
    async def manifest_retained_identity(self, request: vf.CreditRequest):
        return await manifest_retained_identity(self, request)

    @vf.credit
    async def manifest_record_retained_identity(self, request: vf.CreditRequest):
        return await manifest_record_retained_identity(self, request)

    @vf.credit
    async def manifest_created_identity(self, request: vf.CreditRequest):
        return await manifest_created_identity(self, request)

    @vf.credit
    async def manifest_summary_penalty(self, request: vf.CreditRequest):
        return await manifest_summary_penalty(self, request)

    @vf.assessment
    async def manifest_check(self, request: vf.AssessmentRequest, context: vf.AssessmentContext):
        if request.run.producer_id == SUMMARY_PRODUCER:
            return await assess_summary(self, request, context)
        if request.run.producer_id == NO_CLARIFICATION_PRODUCER:
            return await assess_no_clarification(self, request, context)
        if request.run.producer_id == GUARD_PRODUCER:
            return assess_guard(self, request, context)
        if request.run.producer_id == OBLIGATION_PRODUCER:
            return assess_obligation(self, request, context)
        if request.run.producer_id == RETAINED_PRODUCER:
            return assess_retained(self, request, context)
        if request.run.producer_id == CREATED_PRODUCER:
            return assess_created(self, request, context)
        if request.run.producer_id == RECORD_RETAINED_PRODUCER:
            return assess_record_retained(self, request, context)
        material = admit_manifest_source(self, request, context).decode()
        contract = load_contract(canonical_json(material["contract"]))
        config = json.loads(request.run.configuration_json)
        if config["contract_digest"] != canonical_contract_digest(contract):
            raise ValueError("manifest_requested_contract_mismatch")
        evaluation = evaluate_contract(
            material["source"], contract, check_ids=(config["check_id"],),
            evidence=restore_evidence(material["record_evidence_json"]),
        )
        context.record_evidence(OUTPUT_KIND, evaluation.model_dump(mode="json"),
                                invocation_id=request.run.invocation_id)
        result = evaluation.results[0]
        target = request.run.expected[0]
        check = next(item for item in contract.checks if item.check_id == result.check_id)
        if target.signal != _signal(check):
            raise ValueError("manifest_requested_signal_mismatch")
        return (vf.Assessment(
            assessment_id=uuid.uuid4().hex, run_id=request.run.run_id,
            subject=target.subject, view_id=request.views[0].view_id,
            signal=target.signal, status=result.status, value=result.value, reason=result.reason,
            invocation_ids=(request.run.invocation_id,),
        ),)

    def plan_credit(self, source, assessments, context):
        if context.source != source.identity:
            raise ValueError("manifest_credit_source_mismatch")
        contract = load_task_contract(self.data.task_name)
        digest = canonical_contract_digest(contract)
        assert_manifest_credit_revision(source, context.prior_assignments, digest)
        current = {(run.run_id, run.invocation_id, run.attempt_id)
                   for run in context.current_assessment_runs}
        terminal = {}
        for batch in assessments:
            if (batch.run.run_id, batch.run.invocation_id, batch.run.attempt_id) not in current:
                continue
            if batch.run.producer_id not in (PRODUCER, GUARD_PRODUCER, OBLIGATION_PRODUCER, RETAINED_PRODUCER, CREATED_PRODUCER, RECORD_RETAINED_PRODUCER, SUMMARY_PRODUCER, NO_CLARIFICATION_PRODUCER) or batch.run.producer_revision != "1":
                raise ValueError("manifest_credit_producer_mismatch")
            previous = terminal.get(batch.run.run_id)
            if previous is not None:
                if previous.run.status in ("complete", "failed", "interrupted"):
                    if previous != batch:
                        raise ValueError("manifest_assessment_history_regression")
                    continue
                # Lifecycle status/reason and append-only evidence may advance.
                # Compare every other run field, including producer/rubric and
                # snapshot metadata, before handling failure or completion.
                mutable = {"status", "reason", "execution_evidence", "output_evidence"}
                if (previous.source, previous.views, previous.dependencies,
                    previous.run.model_dump(mode="python", exclude=mutable)) != (
                    batch.source, batch.views, batch.dependencies,
                    batch.run.model_dump(mode="python", exclude=mutable)
                ) or previous.assessments != batch.assessments[:len(previous.assessments)] or (
                    previous.run.execution_evidence != batch.run.execution_evidence[:len(previous.run.execution_evidence)]
                    or previous.run.output_evidence != batch.run.output_evidence[:len(previous.run.output_evidence)]
                ):
                    raise ValueError("manifest_assessment_history_conflict")
            if batch.run.status in ("failed", "interrupted"):
                previous = terminal.get(batch.run.run_id)
                if previous is not None and previous.run.status == "complete":
                    raise ValueError("manifest_assessment_history_regression")
                # A failed assessor cannot authorize credit from its partial
                # output. Retain that evidence in history, but do not consume it.
                terminal[batch.run.run_id] = batch
                continue
            if batch.run.status not in ("complete", "partial"):
                continue
            if batch.run.run_id in terminal:
                previous = terminal[batch.run.run_id]
                if previous.run.status == "partial":
                    # Python-mode re-admission also checks appended declared targets.
                    vf.AssessmentBatch.model_validate(batch.model_dump(mode="python"))
                    terminal[batch.run.run_id] = batch
                elif previous.run.status != batch.run.status or (
                    previous.assessments != batch.assessments
                    or previous.run.execution_evidence != batch.run.execution_evidence
                ):
                    raise ValueError("manifest_assessment_history_regression")
                continue
            terminal[batch.run.run_id] = batch
        terminal = {key: batch for key, batch in terminal.items()
                    if batch.run.status in ("complete", "partial") and batch.assessments}
        requests, planned_keys = [], set()
        evaluations, parents = [], {}
        for batch in terminal.values():
            if batch.run.producer_id in (GUARD_PRODUCER, OBLIGATION_PRODUCER, RETAINED_PRODUCER, CREATED_PRODUCER, RECORD_RETAINED_PRODUCER, SUMMARY_PRODUCER, NO_CLARIFICATION_PRODUCER):
                continue
            config = json.loads(batch.run.configuration_json)
            if config["contract_digest"] != digest or batch.source.snapshot_id != source.snapshot_id:
                raise ValueError("manifest_credit_configuration_mismatch")
            receipts = [item for item in batch.run.execution_evidence if item.kind == OUTPUT_KIND]
            if len(receipts) != 1 or receipts[0].invocation_id != batch.run.invocation_id:
                raise ValueError("manifest_evaluation_receipt_unresolved")
            evaluation = Evaluation.model_validate_json(receipts[0].payload_json)
            material = json.loads(batch.views[0].input_json)
            if canonical_json(material["source"]) != canonical_json(_source_material(source)):
                raise ValueError("manifest_evaluation_current_source_mismatch")
            if canonical_contract_digest(load_contract(canonical_json(material["contract"]))) != digest:
                raise ValueError("manifest_evaluation_input_contract_mismatch")
            if evaluation.evidence_json != material["record_evidence_json"]:
                raise ValueError("manifest_evaluation_input_evidence_mismatch")
            if evaluation.source_digest != hashlib.sha256(canonical_json(material["source"]).encode()).hexdigest():
                raise ValueError("manifest_evaluation_source_mismatch")
            if len(evaluation.results) != 1 or evaluation.results[0].check_id != config["check_id"]:
                raise ValueError("manifest_evaluation_check_mismatch")
            record = batch.assessments[0]
            result = evaluation.results[0]
            if (record.signal.signal_id, record.status, record.value, record.reason) != (
                result.signal_id, result.status, result.value, result.reason
            ):
                raise ValueError("manifest_evaluation_published_result_mismatch")
            if result.check_id in parents:
                raise ValueError("manifest_duplicate_current_check")
            parents[result.check_id] = record
            evaluations.append(evaluation)
        guard_batches = tuple(batch for batch in terminal.values() if batch.run.producer_id == GUARD_PRODUCER)
        requests.extend(plan_guard_credit(source, guard_batches, context, contract))
        obligation_batches = tuple(batch for batch in terminal.values() if batch.run.producer_id == OBLIGATION_PRODUCER)
        requests.extend(plan_obligation_credit(source, obligation_batches, context, contract))
        retained_batches = tuple(batch for batch in terminal.values() if batch.run.producer_id == RETAINED_PRODUCER)
        requests.extend(plan_retained_credit(source, retained_batches, context, contract))
        created_batches = tuple(batch for batch in terminal.values() if batch.run.producer_id == CREATED_PRODUCER)
        requests.extend(plan_created_credit(source, created_batches, context, contract))
        record_retained_batches = tuple(batch for batch in terminal.values() if batch.run.producer_id == RECORD_RETAINED_PRODUCER)
        requests.extend(plan_record_retained_credit(source, record_retained_batches, context, contract))
        summary_batches = tuple(batch for batch in terminal.values() if batch.run.producer_id == SUMMARY_PRODUCER)
        requests.extend(plan_summary_credit(self, source, summary_batches, context, contract))
        if not evaluations:
            return _validate_credit_overlap(requests)
        first = evaluations[0]
        if any((item.source_digest, item.evidence_json, item.contract_digest) !=
               (first.source_digest, first.evidence_json, first.contract_digest) for item in evaluations):
            raise ValueError("manifest_current_evidence_conflict")
        combined = Evaluation(
            contract_digest=digest, source_digest=first.source_digest,
            results=tuple(result for item in evaluations for result in item.results),
            evidence_json=first.evidence_json,
        )
        for selection in select_credit(contract, combined):
                accepted = tuple(parents[key] for key in selection.check_ids)
                record = accepted[0]
                if any(parent.signal != record.signal for parent in accepted):
                    raise ValueError("manifest_joint_signal_mismatch")
                recipient = _execution_subject(source, selection.occurrence)
                execution = recipient.execution
                if execution is None:
                    raise ValueError("manifest_execution_recipient_required")
                rule = vf.CreditRule(
                    rule_id="automationbench.manifest_verified_transition_once", revision="1",
                    configuration_json=canonical_json({
                        "contract_digest": digest, "check_ids": selection.check_ids, "policy": selection.policy,
                    }),
                )
                key = (execution.occurrence_id, selection.channel)
                consumed = False
                for assignment in context.prior_assignments:
                    if assignment.request.source.episode_id != source.episode_id or assignment.request.rule != rule:
                        continue
                    for contribution in assignment.contributions:
                        if contribution.status == "valid" and contribution.channel == selection.channel:
                            if contribution.value != selection.value or contribution.signal != record.signal:
                                raise ValueError("manifest_prior_credit_conflict")
                            consumed = True
                if not consumed:
                    if key in planned_keys:
                        raise ValueError("manifest_credit_aggregation_required")
                    planned_keys.add(key)
                    requests.append(("manifest_identity", vf.CreditRequest(
                        source=source.identity, invocation_id=uuid.uuid4().hex, attempt_id=uuid.uuid4().hex,
                        rule=rule, accepted=accepted,
                        targets=(vf.CreditTarget(recipient=recipient, channel=selection.channel),),
                        allocation="turn_boundary", overlap_policy="reject",
                    )))
        return _validate_credit_overlap(requests)

    @vf.credit
    async def manifest_identity(self, request: vf.CreditRequest):
        parent, target = request.accepted[0], request.targets[0]
        joint = len(request.accepted) > 1
        if any(item.status != "valid" or item.value != 1 or item.signal != parent.signal
               for item in request.accepted):
            raise ValueError("manifest_credit_parent_invalid")
        return (vf.CreditContribution(
            contribution_id=uuid.uuid4().hex,
            parent_assessment_ids=tuple(item.assessment_id for item in request.accepted),
            recipient=target.recipient, channel=target.channel, signal=parent.signal,
            transformation="joint_verified_transition_once@1" if joint else "identity",
            status="valid", value=parent.value,
            allocation=request.allocation, attribution="joint" if joint else "coarse", reason=parent.reason,
        ),)
