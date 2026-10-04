"""Native retained-row outcomes; verified state never invents action credit."""

import json
import uuid
from collections import OrderedDict
from dataclasses import asdict, replace
from typing import Literal, cast

import verifiers.v1 as vf
from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from .capture import canonical_json
from .contracts.base import FrozenModel
from .contracts.engine import binding_reason
from .contracts.loader import canonical_contract_digest, load_contract
from .contracts.retained import (
    RetainedFinding,
    RetainedRowCheck,
    evaluate_retained_rows,
    plan_retained_instances,
)
from .contracts.sheet_effects import (
    SheetEffectSource,
    SheetRetentionEvidence,
    capture_sheet_effects,
    capture_sheet_retention,
    validate_sheet_retention,
)
from .contracts.tables import Digest, TableEvidence, TableSource, capture_table
from .manifest_guard_assessments import EffectInput, digest, execution_subject, selectors_digest
from .manifest_source import admit_manifest_source

RETAINED_PRODUCER = "automationbench.manifest_retained_rows"
RETAINED_OUTPUT = "automationbench.manifest_retained_result@1"


class CompletionWitness(FrozenModel):
    check_id: StrictStr = Field(min_length=1)
    instance_key: StrictStr = Field(min_length=1)
    native_record_id: StrictStr = Field(min_length=1)
    occurrence: StrictStr = Field(min_length=1)
    effect_id: StrictStr = Field(min_length=1)
    expected_revision: StrictInt = Field(ge=0)
    applied_revision: StrictInt = Field(ge=1)
    value: StrictFloat | StrictInt

    @model_validator(mode="after")
    def completion(self):
        if self.value != 1 or self.applied_revision != self.expected_revision + 1:
            raise ValueError("retained_completion_witness_invalid")
        return self


class CompletionConsumption(FrozenModel):
    episode_id: StrictStr = Field(min_length=1)
    contract_digest: Digest
    check_id: StrictStr = Field(min_length=1)
    native_record_id: StrictStr = Field(min_length=1)
    instance_key: StrictStr = Field(min_length=1)
    candidate_identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr | StrictInt]
    selectors_digest: Digest
    channel: StrictStr = Field(min_length=1)
    signal: vf.SignalDefinition


class CompletionCreditConfig(FrozenModel):
    consumption: CompletionConsumption
    policy: Literal["retained_completion_once@1"]
    allocation_witness: CompletionWitness
    initially_satisfied: StrictBool
    required: StrictBool
    terminal_value: StrictFloat | StrictInt
    goal_fields: tuple[StrictStr, ...]
    source_digest: Digest
    parent_assessment_id: StrictStr = Field(min_length=1)

    @model_validator(mode="after")
    def complete(self):
        if (self.initially_satisfied or not self.required or self.terminal_value != 1
                or not self.goal_fields or any(not field for field in self.goal_fields)
                or len(set(self.goal_fields)) != len(self.goal_fields)):
            raise ValueError("retained_completion_configuration_invalid")
        return self


class RetainedConfig(FrozenModel):
    contract_digest: Digest
    source_digest: Digest
    selectors_digest: Digest
    check_id: StrictStr
    instance_key: StrictStr
    candidate_identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr | StrictInt] | None
    potential_instances: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def coherent(self):
        if not self.check_id or not self.instance_key:
            raise ValueError("retained_config_identity_required")
        if (self.instance_key == "scope") != (self.candidate_identity is None):
            raise ValueError("retained_config_candidate_required")
        if self.candidate_identity is not None:
            identity = self.candidate_identity
            if not all(identity[:2]) or identity[2] != type(identity[3]).__name__:
                raise ValueError("retained_config_identity_invalid")
        return self


class RetainedOutput(FrozenModel):
    contract_digest: Digest
    source_digest: Digest
    selectors_digest: Digest
    input_digest: Digest
    check_id: StrictStr
    instance_key: StrictStr
    kind: Literal["finding", "scope"]
    candidate_identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr | StrictInt] | None
    native_record_id: StrictStr | None = None
    status: Literal["valid", "inapplicable", "abstained"]
    value: StrictFloat | StrictInt | None
    reason: StrictStr
    required: StrictBool | None = None
    evidence_paths: tuple[tuple[StrictStr | StrictInt, ...], ...] = ()

    @model_validator(mode="after")
    def coherent(self):
        if (self.status == "valid") != (self.value is not None) or self.value not in (None, 0, 1):
            raise ValueError("retained_output_status_invalid")
        if (self.kind == "scope") != (self.instance_key == "scope"):
            raise ValueError("retained_output_scope_invalid")
        if (self.kind == "scope") != (self.candidate_identity is None):
            raise ValueError("retained_output_identity_invalid")
        return self


def capture_retained_inputs(source, contract):
    checks = [check for check in contract.checks if isinstance(check, RetainedRowCheck)]
    population_names = {name for check in checks
                        for name in (check.population, *(lookup.source for lookup in check.lookups))}
    retention_names = {check.source for check in checks}
    credited = {rule.check for rule in contract.credit if rule.policy == "retained_completion_once@1"}
    effect_names = {check.source for check in checks if check.check_id in credited}
    return {
        "retained_population_evidence_json": canonical_json({
            name: capture_table(source, contract.sources[name]).model_dump(mode="json")
            for name in sorted(population_names)
        }),
        "retained_row_evidence_json": canonical_json({
            name: capture_sheet_retention(source, contract.sources[name]).model_dump(mode="json")
            for name in sorted(retention_names)
        }),
        "retained_completion_effects_json": canonical_json({
            name: asdict(capture_sheet_effects(source, contract.sources[name]))
            for name in sorted(effect_names)
        }),
    }


def restore_retained_inputs(material, contract):
    actual = capture_retained_inputs(material["source"], contract)
    if any(material[name] != value for name, value in actual.items()):
        raise ValueError("retained_input_raw_source_or_selector_mismatch")
    populations = {name: TableEvidence.model_validate(value)
                   for name, value in json.loads(actual["retained_population_evidence_json"]).items()}
    retained = {name: SheetRetentionEvidence.model_validate(value)
                for name, value in json.loads(actual["retained_row_evidence_json"]).items()}
    for name, evidence in retained.items():
        validate_sheet_retention(evidence, material["source"], contract.sources[name])
    return populations, retained


def retained_signal(check, *, scope=False):
    return vf.SignalDefinition(
        signal_id=check.signal_id + (".coverage" if scope else ""), revision="1",
        semantics="other" if scope else "outcome", units="coverage_indicator" if scope else "binary",
        minimum=0, maximum=1, direction="neutral" if scope else "higher",
        description="Retained row evidence coverage" if scope else "Declared retained row outcome",
    )


def _evaluate(material, contract, check, populations, retained):
    names = {check.population, *(lookup.source for lookup in check.lookups)}
    cases, potential = plan_retained_instances(check, populations[check.population])
    evaluation = evaluate_retained_rows(
        material["source"], check, {name: populations[name] for name in names}, retained[check.source],
        retention_source=contract.sources[check.source],
        population_sources={name: contract.sources[name] for name in names},
    )
    authority = binding_reason(material["source"], contract)
    if authority is not None:
        evaluation = replace(evaluation, findings=tuple(
            replace(finding, status="abstained", value=None, reason=authority, required=None)
            for finding in evaluation.findings
        ), scope_complete=False, reason=authority)
    return evaluation, cases, potential


def retained_requests(source, contract, view, material, trace_subject):
    populations, _ = restore_retained_inputs(material, contract)
    requests = []
    for check in contract.checks:
        if not isinstance(check, RetainedRowCheck):
            continue
        cases, potential = plan_retained_instances(check, populations[check.population])
        for case in (*cases, None):
            config = RetainedConfig(
                contract_digest=canonical_contract_digest(contract), source_digest=digest(material["source"]),
                selectors_digest=selectors_digest(contract, check), check_id=check.check_id,
                instance_key=case.instance_key if case else "scope",
                candidate_identity=case.candidate_identity if case else None, potential_instances=potential,
            )
            run = vf.AssessmentRun(
                run_id=uuid.uuid4().hex, producer_id=RETAINED_PRODUCER, producer_revision="1",
                rubric_revision=contract.revision, snapshot_id=source.snapshot_id,
                invocation_id=uuid.uuid4().hex, attempt_id=uuid.uuid4().hex,
                configuration_json=canonical_json(config.model_dump(mode="json")),
                expected=(vf.AssessmentTarget(subject=trace_subject, signal=retained_signal(check, scope=case is None)),),
            )
            requests.append(("manifest_check", vf.AssessmentRequest(source=source.identity, run=run, views=(view,))))
    return requests


def _result(config, material, contract, check, evaluation, cases, potential, input_digest):
    if (config.contract_digest != canonical_contract_digest(contract)
            or config.source_digest != digest(material["source"])
            or config.selectors_digest != selectors_digest(contract, check)
            or config.potential_instances != potential or config.check_id != check.check_id):
        raise ValueError("retained_configuration_mismatch")
    scope = config.instance_key == "scope"
    finding = None
    if not scope:
        case = next((case for case in cases if case.instance_key == config.instance_key), None)
        if case is None or case.candidate_identity != config.candidate_identity:
            raise ValueError("retained_candidate_mismatch")
        finding = next(item for item in evaluation.findings if item.instance_key == config.instance_key)
    finding = cast(RetainedFinding, finding)
    return RetainedOutput(
        contract_digest=config.contract_digest, source_digest=config.source_digest,
        selectors_digest=config.selectors_digest, input_digest=input_digest,
        check_id=check.check_id, instance_key=config.instance_key, kind="scope" if scope else "finding",
        candidate_identity=config.candidate_identity,
        native_record_id=None if scope else finding.native_record_id,
        status=("valid" if evaluation.scope_complete else "abstained") if scope else finding.status,
        value=(1 if evaluation.scope_complete else None) if scope else finding.value,
        reason=evaluation.reason if scope else finding.reason,
        required=None if scope else finding.required,
        evidence_paths=() if scope else finding.evidence_paths,
    )


def assess_retained(task, request, context):
    config = RetainedConfig.model_validate_json(request.run.configuration_json)
    if len(request.views) != 1 or len(request.run.expected) != 1 or context.views != request.views:
        raise ValueError("retained_transport_shape_invalid")
    view, target = request.views[0], request.run.expected[0]
    trace_subjects = [subject for subject in view.subjects if subject.kind == "trace"]
    if (len(trace_subjects) != 1 or target.subject != trace_subjects[0]
            or target.subject.snapshot_id != request.source.snapshot_id
            or target.subject.episode_id != request.source.episode_id
            or target.subject.trace_id not in request.source.trace_ids
            or request.run.snapshot_id != request.source.snapshot_id):
        raise ValueError("retained_trace_subject_mismatch")
    admitted = admit_manifest_source(task, request, context)
    key = (request.source.snapshot_id, view.view_id, view.input_digest, config.contract_digest, config.check_id)
    cache = task.__dict__.setdefault("_manifest_retained_cache", OrderedDict())
    if key not in cache:
        material = admitted.decode()
        contract = load_contract(canonical_json(material["contract"]))
        check = next((item for item in contract.checks if item.check_id == config.check_id), None)
        if not isinstance(check, RetainedRowCheck):
            raise ValueError("retained_check_unknown")
        populations, retained = restore_retained_inputs(material, contract)
        evaluation, cases, potential = _evaluate(material, contract, check, populations, retained)
        cache[key] = material, contract, check, evaluation, cases, potential
        while len(cache) > 8:
            cache.popitem(last=False)
    material, contract, check, evaluation, cases, potential = cache[key]
    if (request.run.producer_id != RETAINED_PRODUCER or request.run.producer_revision != "1"
            or request.run.rubric_revision != contract.revision
            or target.signal != retained_signal(check, scope=config.instance_key == "scope")):
        raise ValueError("retained_producer_or_signal_mismatch")
    output = _result(config, material, contract, check, evaluation, cases, potential, view.input_digest)
    context.record_evidence(RETAINED_OUTPUT, output.model_dump(mode="json"), invocation_id=request.run.invocation_id)
    return (vf.Assessment(
        assessment_id=uuid.uuid4().hex, run_id=request.run.run_id, subject=target.subject,
        view_id=view.view_id, signal=target.signal, status=output.status, value=output.value,
        reason=output.reason, invocation_ids=(request.run.invocation_id,),
    ),)


def validate_retained_batches(source, batches, context, contract):
    """Authenticate current outcomes and return their source-bound inputs."""
    if context.source != source.identity:
        raise ValueError("retained_current_source_mismatch")
    current = {(run.run_id, run.invocation_id, run.attempt_id) for run in context.current_assessment_runs}
    raw = json.loads(source.source_json)
    safe = {"task_evidence": raw["task_evidence"], "tool_execution_events": raw.get("tool_execution_events", []),
            "state_write_receipts": raw.get("state_write_receipts", [])}
    subject = vf.SubjectRef(kind="trace", snapshot_id=source.snapshot_id, episode_id=source.episode_id, trace_id=raw["trace_id"])
    inputs, evaluations, seen, admitted_records = {}, {}, set(), []
    for batch in batches:
        run = batch.run
        if (run.run_id, run.invocation_id, run.attempt_id) not in current or run.status != "complete":
            continue
        identity = batch.source.identity if isinstance(batch.source, vf.SourceSnapshot) else batch.source
        if (identity != source.identity or len(batch.views) != 1 or len(batch.assessments) != 1
                or run.producer_id != RETAINED_PRODUCER or run.producer_revision != "1"
                or run.rubric_revision != contract.revision or run.snapshot_id != source.snapshot_id):
            raise ValueError("retained_current_batch_mismatch")
        config = RetainedConfig.model_validate_json(run.configuration_json)
        view = batch.views[0]
        material = json.loads(view.input_json)
        if (digest(material) != view.input_digest or digest(material["source"]) != digest(safe)
                or canonical_contract_digest(load_contract(canonical_json(material["contract"]))) != canonical_contract_digest(contract)):
            raise ValueError("retained_current_input_mismatch")
        if view.input_digest not in inputs:
            inputs[view.input_digest] = restore_retained_inputs(material, contract)
        check = next((item for item in contract.checks if item.check_id == config.check_id), None)
        if not isinstance(check, RetainedRowCheck):
            raise TypeError("retained_current_check_unknown")
        key = view.input_digest, check.check_id
        if key not in evaluations:
            evaluations[key] = _evaluate(material, contract, check, *inputs[view.input_digest])
        evaluation, cases, potential = evaluations[key]
        expected_output = _result(config, material, contract, check, evaluation, cases, potential, view.input_digest)
        receipts = [item for item in run.execution_evidence if item.kind == RETAINED_OUTPUT]
        if len(receipts) != 1 or receipts[0].invocation_id != run.invocation_id:
            raise ValueError("retained_current_receipt_missing")
        admitted = RetainedOutput.model_validate_json(receipts[0].payload_json)
        if admitted != expected_output:
            raise ValueError("retained_current_receipt_mismatch")
        parent = batch.assessments[0]
        expected_signal = retained_signal(check, scope=config.instance_key == "scope")
        if (len(run.expected) != 1 or run.expected[0].subject != subject or run.expected[0].signal != expected_signal
                or parent.subject != subject or subject not in view.subjects
                or parent.signal != expected_signal or parent.view_id != view.view_id or parent.run_id != run.run_id
                or parent.invocation_ids != (run.invocation_id,)
                or (parent.status, parent.value, parent.reason) != (admitted.status, admitted.value, admitted.reason)):
            raise ValueError("retained_current_parent_mismatch")
        instance = check.check_id, config.instance_key
        if instance in seen:
            raise ValueError("retained_duplicate_current_instance")
        seen.add(instance)
        admitted_records.append((material, check, admitted, parent, *inputs[view.input_digest]))
    return tuple(admitted_records)


def plan_retained_credit(source, batches, context, contract):
    from .contracts.retained_credit import evaluate_retained_completion

    admitted = validate_retained_batches(source, batches, context, contract)
    evaluations, effects, requests, channels = {}, {}, [], set()
    for material, check, output, parent, populations, retention in admitted:
        if (output.kind != "finding" or output.status != "valid" or output.value != 1
                or output.required is not True or output.native_record_id is None):
            continue
        rules = [rule for rule in contract.credit
                 if rule.policy == "retained_completion_once@1" and rule.check == check.check_id]
        for rule in rules:
            effect_key = output.input_digest, check.source
            if effect_key not in effects:
                raw = json.loads(material["retained_completion_effects_json"])[check.source]
                effects[effect_key] = EffectInput.model_validate(raw).facts()
            key = output.input_digest, check.check_id, digest(rule.model_dump(mode="json"))
            if key not in evaluations:
                names = {check.population, *(lookup.source for lookup in check.lookups)}
                evaluations[key] = evaluate_retained_completion(
                    material["source"], check, rule, {name: populations[name] for name in names},
                    retention[check.source], effects[effect_key],
                    population_sources={name: contract.sources[name] for name in names},
                    retention_source=contract.sources[check.source],
                )
            evaluation = evaluations[key]
            finding = next((item for item in evaluation.findings if item.instance_key == output.instance_key), None)
            if finding is None or finding.status != "eligible" or finding.selection is None:
                continue
            selected = finding.selection
            if (finding.candidate_identity != output.candidate_identity
                    or selected.native_record_id != output.native_record_id
                    or selected.instance_key != output.instance_key or selected.check_id != check.check_id):
                raise ValueError("retained_completion_instance_mismatch")
            recipient = execution_subject(source, selected.occurrence)
            if recipient is None or recipient.execution is None:
                raise ValueError("retained_completion_execution_missing")
            consumption = {
                "episode_id": source.episode_id, "contract_digest": output.contract_digest,
                "check_id": check.check_id, "native_record_id": output.native_record_id,
                "instance_key": output.instance_key, "candidate_identity": output.candidate_identity,
                "selectors_digest": output.selectors_digest, "channel": rule.channel,
                "signal": parent.signal.model_dump(mode="json"),
            }
            configuration = {
                "consumption": consumption, "policy": rule.policy,
                "allocation_witness": asdict(selected), "initially_satisfied": finding.initially_satisfied,
                "required": output.required, "terminal_value": output.value,
                "goal_fields": rule.goal_fields, "source_digest": output.source_digest,
                "parent_assessment_id": parent.assessment_id,
            }
            configuration = CompletionCreditConfig.model_validate(configuration).model_dump(mode="json")
            credit_rule = vf.CreditRule(rule_id="automationbench.manifest_retained_completion_once",
                revision="1", configuration_json=canonical_json(configuration))
            consumed = False
            for previous in context.prior_assignments:
                old_rule = previous.request.rule
                if (previous.request.source.episode_id != source.episode_id
                        or (old_rule.rule_id, old_rule.revision) != (credit_rule.rule_id, credit_rule.revision)):
                    continue
                old = json.loads(old_rule.configuration_json)
                old_consumption = old.get("consumption", {})
                if canonical_json({k: v for k, v in old_consumption.items() if k != "signal"}) != canonical_json(
                        {k: v for k, v in consumption.items() if k != "signal"}):
                    continue
                for contribution in previous.contributions:
                    if contribution.status != "valid":
                        continue
                    if (old_consumption.get("signal") != consumption["signal"]
                            or contribution.value != 1 or contribution.signal != parent.signal
                            or contribution.channel != rule.channel):
                        raise ValueError("retained_completion_prior_credit_conflict")
                    consumed = True
            if consumed:
                continue
            channel_key = recipient.execution.occurrence_id, rule.channel
            if channel_key in channels:
                raise ValueError("retained_completion_aggregation_required")
            channels.add(channel_key)
            requests.append(("manifest_retained_identity", vf.CreditRequest(
                source=source, invocation_id=uuid.uuid4().hex, attempt_id=uuid.uuid4().hex,
                rule=credit_rule, accepted=(parent,),
                targets=(vf.CreditTarget(recipient=recipient, channel=rule.channel),),
                allocation="turn_boundary", overlap_policy="reject",
            )))
    return requests


async def manifest_retained_identity(task, request):
    if len(request.accepted) != 1 or len(request.targets) != 1:
        raise ValueError("retained_completion_one_parent_target_required")
    parent, target = request.accepted[0], request.targets[0]
    config = CompletionCreditConfig.model_validate_json(request.rule.configuration_json).model_dump(mode="json")
    consumption, witness = config.get("consumption", {}), config.get("allocation_witness", {})
    if (request.rule.rule_id != "automationbench.manifest_retained_completion_once"
            or request.rule.revision != "1" or config.get("policy") != "retained_completion_once@1"
            or parent.status != "valid" or parent.value != 1 or parent.subject.kind != "trace"
            or parent.assessment_id != config.get("parent_assessment_id")
            or parent.signal != vf.SignalDefinition.model_validate(consumption["signal"])
            or config.get("initially_satisfied") is not False or config.get("required") is not True
            or config.get("terminal_value") != 1 or not config.get("goal_fields")
            or consumption.get("episode_id") != request.source.episode_id
            or consumption.get("channel") != target.channel
            or witness.get("native_record_id") != consumption.get("native_record_id")
            or witness.get("check_id") != consumption.get("check_id")
            or witness.get("instance_key") != consumption.get("instance_key")
            or not witness.get("effect_id") or witness.get("value") != 1
            or target.recipient.kind != "execution" or target.recipient.execution is None
            or target.recipient.execution.origin != "tool_server"
            or target.recipient.execution.invocation_id != witness.get("occurrence")
            or parent.signal.direction != "higher" or parent.signal.minimum != 0 or parent.signal.maximum != 1):
        raise ValueError("retained_completion_credit_request_invalid")
    # The native executor authenticates a full request snapshot against its
    # supplied source. Configuration is not itself an allocation proof.
    if task is None or not isinstance(request.source, vf.SourceSnapshot):
        raise ValueError("retained_completion_source_proof_unavailable")
    from .contracts.retained_credit import evaluate_retained_completion
    from .manifest_assessments import load_task_contract

    sealed = vf.SourceSnapshot.model_validate(request.source.model_dump(mode="python"))
    contract = load_task_contract(task.data.task_name)
    check = next((item for item in contract.checks if item.check_id == consumption["check_id"]), None)
    rule = next((item for item in contract.credit
                 if item.check == consumption["check_id"] and item.channel == consumption["channel"]
                 and item.policy == "retained_completion_once@1"), None)
    if (not isinstance(check, RetainedRowCheck) or rule is None
            or canonical_contract_digest(contract) != consumption["contract_digest"]
            or tuple(config["goal_fields"]) != rule.goal_fields
            or parent.signal != retained_signal(check)
            or parent.subject.snapshot_id != sealed.snapshot_id
            or parent.subject.episode_id != sealed.episode_id):
        raise ValueError("retained_completion_contract_or_parent_mismatch")
    raw = json.loads(sealed.source_json)
    safe = {"task_evidence": raw["task_evidence"], "tool_execution_events": raw.get("tool_execution_events", []),
            "state_write_receipts": raw.get("state_write_receipts", [])}
    if (binding_reason(safe, contract) is not None or digest(safe) != config["source_digest"]
            or selectors_digest(contract, check) != consumption["selectors_digest"]):
        raise ValueError("retained_completion_source_or_selector_mismatch")
    names = {check.population, *(lookup.source for lookup in check.lookups)}
    population_sources = {}
    for name in names:
        spec = contract.sources[name]
        if not isinstance(spec, TableSource):
            raise TypeError("retained_completion_population_type_mismatch")
        population_sources[name] = spec
    retention_source = contract.sources[check.source]
    if not isinstance(retention_source, SheetEffectSource):
        raise TypeError("retained_completion_retention_type_mismatch")
    evaluation = evaluate_retained_completion(safe, check, rule,
        {name: capture_table(safe, spec) for name, spec in population_sources.items()},
        capture_sheet_retention(safe, retention_source), capture_sheet_effects(safe, retention_source),
        population_sources=population_sources, retention_source=retention_source)
    finding = next((item for item in evaluation.findings if item.instance_key == consumption["instance_key"]), None)
    if (finding is None or finding.status != "eligible" or finding.selection is None
            or canonical_json(asdict(finding.selection)) != canonical_json(witness)
            or canonical_json(finding.candidate_identity) != canonical_json(consumption["candidate_identity"])
            or finding.native_record_id != consumption["native_record_id"]
            or execution_subject(sealed, finding.selection.occurrence) != target.recipient):
        raise ValueError("retained_completion_allocation_proof_mismatch")
    return (vf.CreditContribution(contribution_id=uuid.uuid4().hex,
        parent_assessment_ids=(parent.assessment_id,), recipient=target.recipient,
        channel=target.channel, signal=parent.signal, transformation="retained_completion_identity@1",
        status="valid", value=1, allocation=request.allocation, attribution="coarse", reason=parent.reason),)
