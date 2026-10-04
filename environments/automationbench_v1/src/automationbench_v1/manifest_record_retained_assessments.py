"""Native retained-record outcomes and separately verified completion credit."""

import json
import uuid
from dataclasses import asdict, replace
from typing import Literal, cast

import verifiers.v1 as vf
from pydantic import StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from .capture import canonical_json
from .contracts.base import FrozenModel
from .contracts.engine import binding_reason
from .contracts.loader import canonical_contract_digest, load_contract
from .contracts.populations import InitialCollectionSource, PopulationEvidence, capture_population
from .contracts.retained_records import (
    RetainedRecordCheck,
    RetainedRecordSource,
    capture_record_retention,
    evaluate_retained_records,
    plan_retained_record_instances,
)
from .contracts.tables import Digest
from .manifest_guard_assessments import digest, execution_subject, selectors_digest
from .manifest_retained_assessments import (
    CompletionConsumption,
    CompletionWitness,
    RetainedConfig,
    RetainedOutput,
)
from .manifest_source import admit_manifest_source

RECORD_RETAINED_PRODUCER = "automationbench.manifest_retained_records"
RECORD_RETAINED_OUTPUT = "automationbench.manifest_retained_record_result@1"
RECORD_COMPLETION_RULE = "automationbench.manifest_record_retained_completion_once"


class RecordCompletionCreditConfig(FrozenModel):
    consumption: CompletionConsumption
    policy: Literal["records_retained_completion_once@1"]
    completion_selection: Literal["earliest"]
    effects: StrictStr
    effects_selector_digest: Digest
    allocation_witness: CompletionWitness
    initially_satisfied: StrictBool
    required: StrictBool
    terminal_value: StrictFloat | StrictInt
    goal_fields: tuple[StrictStr, ...]
    source_digest: Digest
    parent_assessment_id: StrictStr

    @model_validator(mode="after")
    def complete(self):
        if (self.initially_satisfied or not self.required or self.terminal_value != 1
                or not self.effects or not self.parent_assessment_id or not self.goal_fields
                or any(not field for field in self.goal_fields)
                or len(set(self.goal_fields)) != len(self.goal_fields)):
            raise ValueError("record_completion_configuration_invalid")
        return self


def capture_record_retained_inputs(source, contract):
    checks = [check for check in contract.checks if isinstance(check, RetainedRecordCheck)]
    names = {name for check in checks
             for name in (check.population, *(lookup.source for lookup in check.lookups))}
    final_names = {check.source for check in checks}
    result = {
        "retained_record_populations_json": canonical_json({
            name: capture_population(source, contract.sources[name]).model_dump(mode="json")
            for name in sorted(names)
        }),
        "retained_record_terminal_json": canonical_json({
            name: capture_record_retention(source, contract.sources[name]).model_dump(mode="json")
            for name in sorted(final_names)
        }),
    }
    effect_names = {rule.effects for rule in contract.credit
                    if rule.policy == "records_retained_completion_once@1"}
    if effect_names:
        from .contracts.zendesk_effects import capture_zendesk_ticket_effects

        result["retained_record_completion_effects_json"] = canonical_json({
            name: asdict(capture_zendesk_ticket_effects(source, contract.sources[name]))
            for name in sorted(effect_names)
        })
    return result


def _restore(material, contract):
    actual = capture_record_retained_inputs(material["source"], contract)
    if any(material.get(name) != value for name, value in actual.items()):
        raise ValueError("retained_record_input_raw_source_or_selector_mismatch")
    populations = {name: PopulationEvidence.model_validate(value)
                   for name, value in json.loads(actual["retained_record_populations_json"]).items()}
    # Derive terminal evidence again rather than admitting caller projections.
    retained = {check.source: capture_record_retention(material["source"], contract.sources[check.source])
                for check in contract.checks if isinstance(check, RetainedRecordCheck)}
    return populations, retained


def _signal(check, *, scope=False):
    return vf.SignalDefinition(
        signal_id=check.signal_id + (".coverage" if scope else ""), revision="1",
        semantics="other" if scope else "outcome", units="coverage_indicator" if scope else "binary",
        minimum=0, maximum=1, direction="neutral" if scope else "higher",
        description="Retained record evidence coverage" if scope else "Declared retained record outcome",
    )


def record_retained_requests(source, contract, view, material, trace_subject):
    populations, _ = _restore(material, contract)
    requests = []
    for check in contract.checks:
        if not isinstance(check, RetainedRecordCheck):
            continue
        cases, potential = plan_retained_record_instances(check, populations[check.population])
        for case in (*cases, None):
            config = RetainedConfig(
                contract_digest=canonical_contract_digest(contract), source_digest=digest(material["source"]),
                selectors_digest=selectors_digest(contract, check), check_id=check.check_id,
                instance_key=case.instance_key if case else "scope",
                candidate_identity=case.candidate_identity if case else None, potential_instances=potential,
            )
            run = vf.AssessmentRun(
                run_id=uuid.uuid4().hex, producer_id=RECORD_RETAINED_PRODUCER, producer_revision="1",
                rubric_revision=contract.revision, snapshot_id=source.snapshot_id,
                invocation_id=uuid.uuid4().hex, attempt_id=uuid.uuid4().hex,
                configuration_json=canonical_json(config.model_dump(mode="json")),
                expected=(vf.AssessmentTarget(subject=trace_subject, signal=_signal(check, scope=case is None)),),
            )
            requests.append(("manifest_check", vf.AssessmentRequest(source=source.identity, run=run, views=(view,))))
    return requests


def assess_record_retained(task, request, context):
    config = RetainedConfig.model_validate_json(request.run.configuration_json)
    if len(request.views) != 1 or len(request.run.expected) != 1 or context.views != request.views:
        raise ValueError("retained_record_transport_shape_invalid")
    view, target = request.views[0], request.run.expected[0]
    trace_subjects = [subject for subject in view.subjects if subject.kind == "trace"]
    if (len(trace_subjects) != 1 or target.subject != trace_subjects[0]
            or target.subject.snapshot_id != request.source.snapshot_id
            or target.subject.episode_id != request.source.episode_id
            or target.subject.trace_id not in request.source.trace_ids
            or request.run.snapshot_id != request.source.snapshot_id):
        raise ValueError("retained_record_trace_subject_mismatch")
    material = admit_manifest_source(task, request, context).decode()
    contract = load_contract(canonical_json(material["contract"]))
    check = next((item for item in contract.checks if item.check_id == config.check_id), None)
    if not isinstance(check, RetainedRecordCheck):
        raise TypeError("retained_record_check_unknown")
    scope = config.instance_key == "scope"
    if (request.run.producer_id != RECORD_RETAINED_PRODUCER or request.run.producer_revision != "1"
            or request.run.rubric_revision != contract.revision or target.signal != _signal(check, scope=scope)):
        raise ValueError("retained_record_producer_or_signal_mismatch")
    output, _, _ = _outcome_output(material, contract, check, config, view.input_digest)
    context.record_evidence(RECORD_RETAINED_OUTPUT, output.model_dump(mode="json"),
                            invocation_id=request.run.invocation_id)
    return (vf.Assessment(
        assessment_id=uuid.uuid4().hex, run_id=request.run.run_id, subject=target.subject,
        view_id=view.view_id, signal=target.signal, status=output.status, value=output.value,
        reason=output.reason, invocation_ids=(request.run.invocation_id,),
    ),)


def _outcome_output(material, contract, check, config, input_digest):
    scope = config.instance_key == "scope"
    populations, retained = _restore(material, contract)
    cases, potential = plan_retained_record_instances(check, populations[check.population])
    if (config.contract_digest != canonical_contract_digest(contract)
            or config.source_digest != digest(material["source"])
            or config.selectors_digest != selectors_digest(contract, check)
            or config.potential_instances != potential):
        raise ValueError("retained_record_configuration_mismatch")
    names = {check.population, *(lookup.source for lookup in check.lookups)}
    evaluation = evaluate_retained_records(
        material["source"], check, {name: populations[name] for name in names}, retained[check.source],
        population_sources={name: cast(InitialCollectionSource, contract.sources[name]) for name in names},
        retention_source=cast(RetainedRecordSource, contract.sources[check.source]),
    )
    authority = binding_reason(material["source"], contract)
    if authority is not None:
        evaluation = replace(evaluation, findings=tuple(
            replace(finding, status="abstained", value=None, reason=authority, required=None)
            for finding in evaluation.findings
        ), scope_complete=False, reason=authority)
    finding = None
    if not scope:
        case = next((item for item in cases if item.instance_key == config.instance_key), None)
        if case is None or case.candidate_identity != config.candidate_identity:
            raise ValueError("retained_record_candidate_mismatch")
        finding = next(item for item in evaluation.findings if item.instance_key == config.instance_key)
    output = RetainedOutput(
        contract_digest=config.contract_digest, source_digest=config.source_digest,
        selectors_digest=config.selectors_digest, input_digest=input_digest,
        check_id=check.check_id, instance_key=config.instance_key, kind="scope" if scope else "finding",
        candidate_identity=config.candidate_identity,
        native_record_id=finding.native_record_id if finding is not None else None,
        status=finding.status if finding is not None else "valid" if evaluation.scope_complete else "abstained",
        value=finding.value if finding is not None else 1 if evaluation.scope_complete else None,
        reason=finding.reason if finding is not None else evaluation.reason,
        required=finding.required if finding is not None else None,
        evidence_paths=finding.evidence_paths if finding is not None else (),
    )
    return output, populations, retained


def validate_record_retained_batches(source, batches, context, contract):
    """Admit only current native parents whose complete source proof recomputes."""
    if context.source != source.identity:
        raise ValueError("record_completion_current_source_mismatch")
    source = vf.SourceSnapshot.model_validate(source.model_dump(mode="python"))
    current = {(run.run_id, run.invocation_id, run.attempt_id) for run in context.current_assessment_runs}
    raw = json.loads(source.source_json)
    safe = {"task_evidence": raw["task_evidence"], "tool_execution_events": raw.get("tool_execution_events", []),
            "state_write_receipts": raw.get("state_write_receipts", [])}
    subject = vf.SubjectRef(kind="trace", snapshot_id=source.snapshot_id,
        episode_id=source.episode_id, trace_id=raw["trace_id"])
    seen, admitted = set(), []
    for batch in batches:
        run = batch.run
        if (run.run_id, run.invocation_id, run.attempt_id) not in current or run.status != "complete":
            continue
        identity = batch.source.identity if isinstance(batch.source, vf.SourceSnapshot) else batch.source
        if (identity != source.identity or len(batch.views) != 1 or len(batch.assessments) != 1
                or run.producer_id != RECORD_RETAINED_PRODUCER or run.producer_revision != "1"
                or run.rubric_revision != contract.revision or run.snapshot_id != source.snapshot_id):
            raise ValueError("record_completion_current_batch_mismatch")
        config = RetainedConfig.model_validate_json(run.configuration_json)
        view = vf.ObservationView.model_validate(batch.views[0].model_dump(mode="python"))
        if view.input_json is None or view.scope != "retrospective" or view.snapshot_id != source.snapshot_id:
            raise ValueError("record_completion_current_view_mismatch")
        material = json.loads(view.input_json)
        if (digest(material) != view.input_digest or canonical_json(material["source"]) != canonical_json(safe)
                or canonical_contract_digest(load_contract(canonical_json(material["contract"]))) != canonical_contract_digest(contract)):
            raise ValueError("record_completion_current_input_mismatch")
        check = next((item for item in contract.checks if item.check_id == config.check_id), None)
        if not isinstance(check, RetainedRecordCheck):
            raise TypeError("record_completion_current_check_unknown")
        expected, populations, retained = _outcome_output(material, contract, check, config, view.input_digest)
        receipts = [item for item in run.execution_evidence if item.kind == RECORD_RETAINED_OUTPUT]
        if len(receipts) != 1 or receipts[0].invocation_id != run.invocation_id:
            raise ValueError("record_completion_current_receipt_missing")
        receipt = vf.ExecutionEvidence.model_validate(receipts[0].model_dump(mode="python"))
        output = RetainedOutput.model_validate_json(receipt.payload_json)
        if output != expected:
            raise ValueError("record_completion_current_receipt_mismatch")
        parent = vf.Assessment.model_validate(batch.assessments[0].model_dump(mode="python"))
        signal = _signal(check, scope=config.instance_key == "scope")
        if (len(run.expected) != 1 or run.expected[0].subject != subject or run.expected[0].signal != signal
                or parent.subject != subject or subject not in view.subjects
                or parent.signal != signal or parent.view_id != view.view_id or parent.run_id != run.run_id
                or parent.invocation_ids != (run.invocation_id,)
                or (parent.status, parent.value, parent.reason) != (output.status, output.value, output.reason)):
            raise ValueError("record_completion_current_parent_mismatch")
        instance = check.check_id, config.instance_key
        if instance in seen:
            raise ValueError("record_completion_duplicate_current_instance")
        seen.add(instance)
        admitted.append((material, check, output, parent, populations, retained))
    return tuple(admitted)


def plan_record_retained_credit(source, batches, context, contract):
    from .contracts.record_retained_credit import evaluate_record_retained_completion
    from .contracts.zendesk_effects import capture_zendesk_ticket_effects

    admitted = validate_record_retained_batches(source, batches, context, contract)
    requests, channels = [], set()
    for material, check, output, parent, populations, retained in admitted:
        if (output.kind != "finding" or output.status != "valid" or output.value != 1
                or output.required is not True or output.native_record_id is None):
            continue
        for rule in contract.credit:
            if rule.policy != "records_retained_completion_once@1" or rule.check != check.check_id:
                continue
            names = {check.population, *(lookup.source for lookup in check.lookups)}
            effects = capture_zendesk_ticket_effects(material["source"], contract.sources[rule.effects])
            evaluation = evaluate_record_retained_completion(material["source"], check, rule,
                {name: populations[name] for name in names}, retained[check.source], effects,
                population_sources={name: contract.sources[name] for name in names},
                retention_source=contract.sources[check.source], effect_source=contract.sources[rule.effects])
            finding = next((item for item in evaluation.findings if item.instance_key == output.instance_key), None)
            if finding is None or finding.status != "eligible" or finding.selection is None:
                continue
            selected = finding.selection
            if (finding.candidate_identity != output.candidate_identity or finding.initially_satisfied is not False
                    or selected.native_record_id != output.native_record_id
                    or selected.instance_key != output.instance_key or selected.check_id != check.check_id):
                raise ValueError("record_completion_instance_mismatch")
            recipient = execution_subject(source, selected.occurrence)
            if recipient is None or recipient.execution is None:
                raise ValueError("record_completion_execution_missing")
            consumption = {
                "episode_id": source.episode_id, "contract_digest": output.contract_digest,
                "check_id": check.check_id, "native_record_id": output.native_record_id,
                "instance_key": output.instance_key, "candidate_identity": output.candidate_identity,
                "selectors_digest": _credit_selectors(contract, check, rule), "channel": rule.channel,
                "signal": parent.signal.model_dump(mode="json"),
            }
            configuration = RecordCompletionCreditConfig.model_validate({
                "consumption": consumption, "policy": rule.policy, "completion_selection": rule.completion_selection,
                "effects": rule.effects, "effects_selector_digest": digest(contract.sources[rule.effects].model_dump(mode="json")),
                "allocation_witness": asdict(selected), "initially_satisfied": finding.initially_satisfied,
                "required": output.required, "terminal_value": output.value, "goal_fields": rule.goal_fields,
                "source_digest": output.source_digest, "parent_assessment_id": parent.assessment_id,
            })
            credit_rule = vf.CreditRule(rule_id=RECORD_COMPLETION_RULE, revision="1",
                configuration_json=canonical_json(configuration.model_dump(mode="json")))
            consumed = False
            for previous in context.prior_assignments:
                old_rule = previous.request.rule
                if (previous.request.source.episode_id != source.episode_id
                        or (old_rule.rule_id, old_rule.revision) != (credit_rule.rule_id, credit_rule.revision)):
                    continue
                old = RecordCompletionCreditConfig.model_validate_json(old_rule.configuration_json)
                old_consumption = old.consumption.model_dump(mode="json")
                stable = ("episode_id", "check_id", "native_record_id", "channel")
                if any(old_consumption[key] != consumption[key] for key in stable):
                    continue
                for contribution in previous.contributions:
                    if contribution.status != "valid":
                        continue
                    if (canonical_json(old_consumption) != canonical_json(consumption) or contribution.value != 1
                            or contribution.signal != parent.signal or contribution.channel != rule.channel):
                        raise ValueError("record_completion_prior_credit_conflict")
                    consumed = True
            if consumed:
                continue
            channel = recipient.execution.occurrence_id, rule.channel
            if channel in channels:
                raise ValueError("record_completion_aggregation_required")
            channels.add(channel)
            requests.append(("manifest_record_retained_identity", vf.CreditRequest(
                source=source, invocation_id=uuid.uuid4().hex, attempt_id=uuid.uuid4().hex,
                rule=credit_rule, accepted=(parent,), targets=(vf.CreditTarget(recipient=recipient, channel=rule.channel),),
                allocation="turn_boundary", overlap_policy="reject")))
    return requests


def _credit_selectors(contract, check, rule):
    return digest({"outcome": selectors_digest(contract, check),
                   "effects": {rule.effects: contract.sources[rule.effects].model_dump(mode="json")}})


async def manifest_record_retained_identity(task, request):
    if len(request.accepted) != 1 or len(request.targets) != 1:
        raise ValueError("record_completion_one_parent_target_required")
    parent, target = request.accepted[0], request.targets[0]
    config = RecordCompletionCreditConfig.model_validate_json(request.rule.configuration_json)
    consumption, witness = config.consumption, config.allocation_witness
    if (request.rule.rule_id != RECORD_COMPLETION_RULE or request.rule.revision != "1"
            or parent.status != "valid" or parent.value != 1 or parent.subject.kind != "trace"
            or parent.assessment_id != config.parent_assessment_id or parent.signal != consumption.signal
            or consumption.episode_id != request.source.episode_id or consumption.channel != target.channel
            or witness.native_record_id != consumption.native_record_id or witness.check_id != consumption.check_id
            or witness.instance_key != consumption.instance_key
            or target.recipient.kind != "execution" or target.recipient.execution is None
            or target.recipient.execution.origin != "tool_server"
            or target.recipient.execution.invocation_id != witness.occurrence
            or parent.signal.direction != "higher" or parent.signal.minimum != 0 or parent.signal.maximum != 1):
        raise ValueError("record_completion_credit_request_invalid")
    if task is None or not isinstance(request.source, vf.SourceSnapshot):
        raise ValueError("record_completion_source_proof_unavailable")
    from .contracts.record_retained_credit import evaluate_record_retained_completion
    from .contracts.zendesk_effects import ZendeskTicketEffectSource, capture_zendesk_ticket_effects
    from .manifest_assessments import load_task_contract

    sealed = vf.SourceSnapshot.model_validate(request.source.model_dump(mode="python"))
    contract = load_task_contract(task.data.task_name)
    check = next((item for item in contract.checks if item.check_id == consumption.check_id), None)
    rule = next((item for item in contract.credit if item.check == consumption.check_id
                 and item.channel == consumption.channel and item.policy == config.policy), None)
    if (not isinstance(check, RetainedRecordCheck) or rule is None or rule.effects is None
            or canonical_contract_digest(contract) != consumption.contract_digest
            or config.goal_fields != rule.goal_fields or config.effects != rule.effects
            or config.completion_selection != rule.completion_selection or parent.signal != _signal(check)
            or parent.subject.snapshot_id != sealed.snapshot_id or parent.subject.episode_id != sealed.episode_id):
        raise ValueError("record_completion_contract_or_parent_mismatch")
    raw = json.loads(sealed.source_json)
    safe = {"task_evidence": raw["task_evidence"], "tool_execution_events": raw.get("tool_execution_events", []),
            "state_write_receipts": raw.get("state_write_receipts", [])}
    if (parent.subject.trace_id != raw["trace_id"] or binding_reason(safe, contract) is not None
            or digest(safe) != config.source_digest or _credit_selectors(contract, check, rule) != consumption.selectors_digest):
        raise ValueError("record_completion_source_or_selector_mismatch")
    names = {check.population, *(lookup.source for lookup in check.lookups)}
    population_sources = {}
    for name in names:
        spec = contract.sources[name]
        if not isinstance(spec, InitialCollectionSource):
            raise TypeError("record_completion_population_type_mismatch")
        population_sources[name] = spec
    retention_source, effect_source = contract.sources[check.source], contract.sources[rule.effects]
    if (not isinstance(retention_source, RetainedRecordSource) or not isinstance(effect_source, ZendeskTicketEffectSource)
            or digest(effect_source.model_dump(mode="json")) != config.effects_selector_digest):
        raise ValueError("record_completion_source_type_or_effect_selector_mismatch")
    evaluation = evaluate_record_retained_completion(safe, check, rule,
        {name: capture_population(safe, spec) for name, spec in population_sources.items()},
        capture_record_retention(safe, retention_source), capture_zendesk_ticket_effects(safe, effect_source),
        population_sources=population_sources, retention_source=retention_source, effect_source=effect_source)
    finding = next((item for item in evaluation.findings if item.instance_key == consumption.instance_key), None)
    if (finding is None or finding.status != "eligible" or finding.initially_satisfied is not False
            or finding.selection is None or canonical_json(asdict(finding.selection)) != canonical_json(witness.model_dump(mode="json"))
            or canonical_json(finding.candidate_identity) != canonical_json(consumption.candidate_identity)
            or finding.native_record_id != consumption.native_record_id
            or execution_subject(sealed, finding.selection.occurrence) != target.recipient):
        raise ValueError("record_completion_allocation_proof_mismatch")
    return (vf.CreditContribution(contribution_id=uuid.uuid4().hex,
        parent_assessment_ids=(parent.assessment_id,), recipient=target.recipient, channel=target.channel,
        signal=parent.signal, transformation="records_retained_completion_identity@1", status="valid", value=1,
        allocation=request.allocation, attribution="coarse", reason=parent.reason),)
