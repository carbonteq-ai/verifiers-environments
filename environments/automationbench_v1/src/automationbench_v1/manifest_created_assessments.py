"""Native fresh-object outcomes and separately replayable completion credit."""

import json
import uuid
from collections import OrderedDict
from dataclasses import asdict, replace
from typing import Literal, cast

import verifiers.v1 as vf
from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from .capture import canonical_json
from .contracts.base import FrozenModel
from .contracts.created_objects import (
    CreatedFinding,
    CreatedRetainedCheck,
    capture_created_evidence,
    created_object_count,
    evaluate_created_completion,
    evaluate_created_retained,
    restore_created_evidence,
)
from .contracts.engine import binding_reason
from .contracts.hubspot_objects import HubSpotObjectSource
from .contracts.jira_effects import JiraIssueSource
from .contracts.loader import canonical_contract_digest, load_contract
from .contracts.requests import RequestPopulationEvidence, RequestSource, capture_request_population
from .contracts.tables import Digest
from .manifest_guard_assessments import digest, execution_subject
from .manifest_source import admit_manifest_source

CREATED_PRODUCER = "automationbench.manifest_created_objects"
CREATED_OUTPUT = "automationbench.manifest_created_result@1"


class CreatedConfig(FrozenModel):
    contract_digest: Digest
    source_digest: Digest
    selectors_digest: Digest
    check_id: StrictStr = Field(min_length=1)
    instance_key: StrictStr = Field(min_length=1)
    candidate_identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr] | None
    potential_instances: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def coherent(self):
        if (self.instance_key == "scope") != (self.candidate_identity is None):
            raise ValueError("created_config_candidate_required")
        if self.candidate_identity is not None and (
            self.candidate_identity[0] != "public.request@1"
            or self.candidate_identity[2] != "authored"
            or not all(self.candidate_identity)
        ):
            raise ValueError("created_config_authored_identity_invalid")
        return self


class CreatedOutput(FrozenModel):
    contract_digest: Digest
    source_digest: Digest
    selectors_digest: Digest
    input_digest: Digest
    check_id: StrictStr
    instance_key: StrictStr
    kind: Literal["finding", "scope"]
    candidate_identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr] | None
    native_record_ids: tuple[StrictStr, ...] = ()
    status: Literal["valid", "inapplicable", "abstained"]
    value: StrictFloat | StrictInt | None
    reason: StrictStr
    required: StrictBool | None = None
    evidence_paths: tuple[tuple[StrictStr | StrictInt, ...], ...] = ()

    @model_validator(mode="after")
    def coherent(self):
        if (
            (self.status == "valid") != (self.value is not None)
            or self.value not in (None, 0, 1)
            or (self.kind == "scope") != (self.instance_key == "scope")
            or (self.kind == "scope") != (self.candidate_identity is None)
            or len(set(self.native_record_ids)) != len(self.native_record_ids)
        ):
            raise ValueError("created_output_status_or_identity_invalid")
        return self


class CreatedWitness(FrozenModel):
    check_id: StrictStr = Field(min_length=1)
    instance_key: StrictStr = Field(min_length=1)
    native_record_id: StrictStr = Field(min_length=1)
    occurrence: StrictStr = Field(min_length=1)
    effect_id: StrictStr = Field(min_length=1)
    expected_revision: StrictInt = Field(ge=0)
    applied_revision: StrictInt = Field(ge=1)
    value: StrictFloat | StrictInt

    @model_validator(mode="after")
    def coherent(self):
        if self.value != 1 or self.applied_revision != self.expected_revision + 1:
            raise ValueError("created_credit_witness_invalid")
        return self


class CreatedConsumption(FrozenModel):
    episode_id: StrictStr = Field(min_length=1)
    contract_digest: Digest
    check_id: StrictStr = Field(min_length=1)
    instance_key: StrictStr = Field(min_length=1)
    candidate_identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr]
    selectors_digest: Digest
    channel: StrictStr = Field(min_length=1)
    signal: vf.SignalDefinition


class CreatedCreditConfig(FrozenModel):
    consumption: CreatedConsumption
    policy: Literal["created_retained_completion_once@1"]
    completion_selection: Literal["earliest"]
    allocation_witness: CreatedWitness
    goal_fields: tuple[StrictStr, ...]
    source_digest: Digest
    parent_assessment_id: StrictStr = Field(min_length=1)

    @model_validator(mode="after")
    def coherent(self):
        if (
            not self.goal_fields
            or len(set(self.goal_fields)) != len(self.goal_fields)
            or any(not field for field in self.goal_fields)
        ):
            raise ValueError("created_credit_goal_fields_invalid")
        return self


def public_bindings(contract):
    return tuple(
        binding
        for binding in contract.bindings
        if binding.path[:2] in {("task_evidence", "prompt"), ("task_evidence", "initial")}
    )


def created_selectors_digest(contract, check):
    return digest(
        {
            name: contract.sources[name].model_dump(mode="json")
            for name in (check.population, check.source)
        }
    )


def capture_created_inputs(source, contract):
    checks = [check for check in contract.checks if isinstance(check, CreatedRetainedCheck)]
    if not checks:
        return {}
    return {
        "created_population_evidence_json": canonical_json(
            {
                name: capture_request_population(
                    source, contract.sources[name], public_bindings(contract)
                ).model_dump(mode="json")
                for name in sorted({check.population for check in checks})
            }
        ),
        "created_object_evidence_json": canonical_json(
            {
                name: capture_created_evidence(source, contract.sources[name]).model_dump(
                    mode="json"
                )
                for name in sorted({check.source for check in checks})
            }
        ),
    }


def restore_created_inputs(material, contract):
    actual = capture_created_inputs(material["source"], contract)
    if not actual:
        return {}, {}
    if any(material[name] != value for name, value in actual.items()):
        raise ValueError("created_input_raw_source_or_selector_mismatch")
    return (
        {
            name: RequestPopulationEvidence.model_validate(value)
            for name, value in json.loads(actual["created_population_evidence_json"]).items()
        },
        {
            name: restore_created_evidence(value, contract.sources[name])
            for name, value in json.loads(actual["created_object_evidence_json"]).items()
        },
    )


def created_signal(check, *, scope=False):
    return vf.SignalDefinition(
        signal_id=check.signal_id + (".coverage" if scope else ""),
        revision="1",
        semantics="other" if scope else "outcome",
        units="coverage_indicator" if scope else "binary",
        minimum=0,
        maximum=1,
        direction="neutral" if scope else "higher",
        description="Fresh-object evidence coverage"
        if scope
        else "Fresh created object retained outcome",
    )


def _evaluate(material, contract, check, populations, objects):
    evaluation = evaluate_created_retained(
        material["source"],
        check,
        populations[check.population],
        objects[check.source],
        population_source=contract.sources[check.population],
        object_source=contract.sources[check.source],
        bindings=public_bindings(contract),
    )
    authority = binding_reason(material["source"], contract)
    if authority is not None:
        evaluation = replace(
            evaluation,
            findings=tuple(
                replace(
                    finding,
                    status="abstained",
                    value=None,
                    reason=authority,
                    required=None,
                    native_record_ids=(),
                )
                for finding in evaluation.findings
            ),
            scope_complete=False,
            reason=authority,
        )
    return evaluation


def created_requests(source, contract, view, material, trace_subject):
    populations, objects = restore_created_inputs(material, contract)
    requests = []
    for check in contract.checks:
        if not isinstance(check, CreatedRetainedCheck):
            continue
        evaluation = _evaluate(material, contract, check, populations, objects)
        for finding in (*evaluation.findings, None):
            config = CreatedConfig(
                contract_digest=canonical_contract_digest(contract),
                source_digest=digest(material["source"]),
                selectors_digest=created_selectors_digest(contract, check),
                check_id=check.check_id,
                instance_key=finding.instance_key if finding else "scope",
                candidate_identity=finding.candidate_identity if finding else None,
                potential_instances=created_object_count(objects[check.source]),
            )
            run = vf.AssessmentRun(
                run_id=uuid.uuid4().hex,
                producer_id=CREATED_PRODUCER,
                producer_revision="1",
                rubric_revision=contract.revision,
                snapshot_id=source.snapshot_id,
                invocation_id=uuid.uuid4().hex,
                attempt_id=uuid.uuid4().hex,
                configuration_json=canonical_json(config.model_dump(mode="json")),
                expected=(
                    vf.AssessmentTarget(
                        subject=trace_subject, signal=created_signal(check, scope=finding is None)
                    ),
                ),
            )
            requests.append(
                (
                    "manifest_check",
                    vf.AssessmentRequest(source=source.identity, run=run, views=(view,)),
                )
            )
    return requests


def _output(config, material, contract, check, evaluation, objects, input_digest):
    if (
        config.contract_digest != canonical_contract_digest(contract)
        or config.source_digest != digest(material["source"])
        or config.selectors_digest != created_selectors_digest(contract, check)
        or config.check_id != check.check_id
        or config.potential_instances != created_object_count(objects[check.source])
    ):
        raise ValueError("created_configuration_mismatch")
    scope = config.instance_key == "scope"
    finding = next(
        (item for item in evaluation.findings if item.instance_key == config.instance_key), None
    )
    if not scope and (finding is None or config.candidate_identity != finding.candidate_identity):
        raise ValueError("created_candidate_mismatch")
    finding = cast(CreatedFinding, finding)
    return CreatedOutput(
        contract_digest=config.contract_digest,
        source_digest=config.source_digest,
        selectors_digest=config.selectors_digest,
        input_digest=input_digest,
        check_id=check.check_id,
        instance_key=config.instance_key,
        kind="scope" if scope else "finding",
        candidate_identity=config.candidate_identity,
        native_record_ids=() if scope else finding.native_record_ids,
        status=("valid" if evaluation.scope_complete else "abstained") if scope else finding.status,
        value=(1 if evaluation.scope_complete else None) if scope else finding.value,
        reason=evaluation.reason if scope else finding.reason,
        required=None if scope else finding.required,
        evidence_paths=() if scope else finding.evidence_paths,
    )


def assess_created(task, request, context):
    admitted = admit_manifest_source(task, request, context)
    config = CreatedConfig.model_validate_json(request.run.configuration_json)
    if len(request.views) != 1 or len(request.run.expected) != 1:
        raise ValueError("created_transport_shape_invalid")
    view, target = request.views[0], request.run.expected[0]
    traces = [subject for subject in view.subjects if subject.kind == "trace"]
    if (
        len(traces) != 1
        or target.subject != traces[0]
        or target.subject.snapshot_id != request.source.snapshot_id
        or target.subject.episode_id != request.source.episode_id
        or target.subject.trace_id not in request.source.trace_ids
    ):
        raise ValueError("created_trace_subject_mismatch")
    key = (
        request.source.snapshot_id,
        view.view_id,
        view.input_digest,
        config.contract_digest,
        config.check_id,
    )
    cache = task.__dict__.setdefault("_manifest_created_cache", OrderedDict())
    if key not in cache:
        material = admitted.decode()
        contract = load_contract(canonical_json(material["contract"]))
        check = next((item for item in contract.checks if item.check_id == config.check_id), None)
        if not isinstance(check, CreatedRetainedCheck):
            raise ValueError("created_check_unknown")
        populations, objects = restore_created_inputs(material, contract)
        cache[key] = (
            material,
            contract,
            check,
            _evaluate(material, contract, check, populations, objects),
            objects,
        )
        while len(cache) > 8:
            cache.popitem(last=False)
    material, contract, check, evaluation, objects = cache[key]
    if (
        request.run.producer_id != CREATED_PRODUCER
        or request.run.producer_revision != "1"
        or request.run.rubric_revision != contract.revision
        or target.signal != created_signal(check, scope=config.instance_key == "scope")
    ):
        raise ValueError("created_producer_or_signal_mismatch")
    output = _output(config, material, contract, check, evaluation, objects, view.input_digest)
    context.record_evidence(
        CREATED_OUTPUT, output.model_dump(mode="json"), invocation_id=request.run.invocation_id
    )
    return (
        vf.Assessment(
            assessment_id=uuid.uuid4().hex,
            run_id=request.run.run_id,
            subject=target.subject,
            view_id=view.view_id,
            signal=target.signal,
            status=output.status,
            value=output.value,
            reason=output.reason,
            invocation_ids=(request.run.invocation_id,),
        ),
    )


def validate_created_batches(source, batches, context, contract):
    if context.source != source.identity:
        raise ValueError("created_current_source_mismatch")
    current = {
        (run.run_id, run.invocation_id, run.attempt_id) for run in context.current_assessment_runs
    }
    raw = json.loads(source.source_json)
    safe = {
        "task_evidence": raw["task_evidence"],
        "tool_execution_events": raw.get("tool_execution_events", []),
        "state_write_receipts": raw.get("state_write_receipts", []),
    }
    subject = vf.SubjectRef(
        kind="trace",
        snapshot_id=source.snapshot_id,
        episode_id=source.episode_id,
        trace_id=raw["trace_id"],
    )
    seen, receipts, inputs, evaluations = set(), [], {}, {}
    for batch in batches:
        run = batch.run
        if (
            run.run_id,
            run.invocation_id,
            run.attempt_id,
        ) not in current or run.status != "complete":
            continue
        identity = (
            batch.source.identity if isinstance(batch.source, vf.SourceSnapshot) else batch.source
        )
        if (
            identity != source.identity
            or len(batch.views) != 1
            or len(batch.assessments) != 1
            or run.producer_id != CREATED_PRODUCER
            or run.producer_revision != "1"
            or run.rubric_revision != contract.revision
            or run.snapshot_id != source.snapshot_id
        ):
            raise ValueError("created_current_batch_mismatch")
        config, view = CreatedConfig.model_validate_json(run.configuration_json), batch.views[0]
        material = json.loads(view.input_json)
        if (
            digest(material) != view.input_digest
            or canonical_json(material["source"]) != canonical_json(safe)
            or canonical_contract_digest(load_contract(canonical_json(material["contract"])))
            != canonical_contract_digest(contract)
        ):
            raise ValueError("created_current_input_mismatch")
        if view.input_digest not in inputs:
            inputs[view.input_digest] = restore_created_inputs(material, contract)
        check = next((item for item in contract.checks if item.check_id == config.check_id), None)
        if not isinstance(check, CreatedRetainedCheck):
            raise TypeError("created_current_check_unknown")
        key = view.input_digest, check.check_id
        if key not in evaluations:
            evaluations[key] = _evaluate(material, contract, check, *inputs[view.input_digest])
        output = _output(
            config,
            material,
            contract,
            check,
            evaluations[key],
            inputs[view.input_digest][1],
            view.input_digest,
        )
        evidence = [item for item in run.execution_evidence if item.kind == CREATED_OUTPUT]
        if (
            len(evidence) != 1
            or evidence[0].invocation_id != run.invocation_id
            or CreatedOutput.model_validate_json(evidence[0].payload_json) != output
        ):
            raise ValueError("created_current_receipt_mismatch")
        parent, expected_signal = (
            batch.assessments[0],
            created_signal(check, scope=config.instance_key == "scope"),
        )
        if (
            len(run.expected) != 1
            or run.expected[0].subject != subject
            or run.expected[0].signal != expected_signal
            or parent.subject != subject
            or subject not in view.subjects
            or parent.signal != expected_signal
            or parent.view_id != view.view_id
            or parent.run_id != run.run_id
            or parent.invocation_ids != (run.invocation_id,)
            or (parent.status, parent.value, parent.reason)
            != (output.status, output.value, output.reason)
        ):
            raise ValueError("created_current_parent_mismatch")
        key = check.check_id, config.instance_key
        if key in seen:
            raise ValueError("created_duplicate_current_instance")
        seen.add(key)
        receipts.append((material, check, output, parent, *inputs[view.input_digest]))
    return tuple(receipts)


def plan_created_credit(source, batches, context, contract):
    accepted = validate_created_batches(source, batches, context, contract)
    requests, channels = [], set()
    for material, check, output, parent, populations, objects in accepted:
        if (
            output.kind != "finding"
            or output.status != "valid"
            or output.value != 1
            or output.required is not True
        ):
            continue
        for rule in contract.credit:
            if rule.policy != "created_retained_completion_once@1" or rule.check != check.check_id:
                continue
            evaluation = evaluate_created_completion(
                material["source"],
                check,
                populations[check.population],
                objects[check.source],
                population_source=contract.sources[check.population],
                object_source=contract.sources[check.source],
                bindings=public_bindings(contract),
                goal_fields=rule.goal_fields,
                selection=rule.completion_selection,
            )
            finding = evaluation.findings[0]
            if finding.selection is None or finding.status != "eligible":
                continue
            selected = finding.selection
            if (
                finding.instance_key != output.instance_key
                or finding.candidate_identity != output.candidate_identity
            ):
                raise ValueError("created_completion_instance_mismatch")
            recipient = execution_subject(source, selected.occurrence)
            if recipient is None or recipient.execution is None:
                raise ValueError("created_completion_execution_missing")
            consumption = CreatedConsumption(
                episode_id=source.episode_id,
                contract_digest=output.contract_digest,
                check_id=check.check_id,
                instance_key=output.instance_key,
                candidate_identity=output.candidate_identity,
                selectors_digest=output.selectors_digest,
                channel=rule.channel,
                signal=parent.signal,
            )
            consumed = False
            for assignment in context.prior_assignments:
                if (
                    assignment.request.rule.rule_id
                    != "automationbench.manifest_created_completion_once"
                    or assignment.request.rule.revision != "1"
                    or assignment.request.source.episode_id != source.episode_id
                ):
                    continue
                previous = CreatedCreditConfig.model_validate_json(
                    assignment.request.rule.configuration_json
                )
                old = previous.consumption.model_dump(mode="json")
                fresh = consumption.model_dump(mode="json")
                # Signal conflicts cannot evade an otherwise identical once key.
                if {key: value for key, value in old.items() if key != "signal"} != {
                    key: value for key, value in fresh.items() if key != "signal"
                }:
                    continue
                for contribution in assignment.contributions:
                    if contribution.status == "valid" and contribution.channel == rule.channel:
                        if (
                            contribution.value != 1
                            or contribution.signal != parent.signal
                            or previous.consumption.signal != parent.signal
                        ):
                            raise ValueError("created_prior_credit_conflict")
                        consumed = True
            if consumed:
                continue
            key = recipient.execution.occurrence_id, rule.channel
            if key in channels:
                raise ValueError("created_credit_aggregation_required")
            channels.add(key)
            config = CreatedCreditConfig(
                consumption=consumption,
                policy=rule.policy,
                completion_selection=rule.completion_selection,
                allocation_witness=CreatedWitness(**asdict(selected)),
                goal_fields=rule.goal_fields,
                source_digest=output.source_digest,
                parent_assessment_id=parent.assessment_id,
            )
            requests.append(
                (
                    "manifest_created_identity",
                    vf.CreditRequest(
                        source=source,
                        invocation_id=uuid.uuid4().hex,
                        attempt_id=uuid.uuid4().hex,
                        rule=vf.CreditRule(
                            rule_id="automationbench.manifest_created_completion_once",
                            revision="1",
                            configuration_json=canonical_json(config.model_dump(mode="json")),
                        ),
                        accepted=(parent,),
                        targets=(vf.CreditTarget(recipient=recipient, channel=rule.channel),),
                        allocation="turn_boundary",
                        overlap_policy="reject",
                    ),
                )
            )
    return requests


async def manifest_created_identity(task, request, context=None):
    if task is None or not isinstance(request.source, vf.SourceSnapshot):
        raise ValueError("created_completion_source_proof_unavailable")
    if len(request.accepted) != 1 or len(request.targets) != 1:
        raise ValueError("created_completion_requires_one_parent_target")
    config = CreatedCreditConfig.model_validate_json(request.rule.configuration_json)
    parent, target = request.accepted[0], request.targets[0]
    sealed = vf.SourceSnapshot.model_validate(request.source.model_dump(mode="python"))
    if (
        request.rule.rule_id != "automationbench.manifest_created_completion_once"
        or request.rule.revision != "1"
        or parent.assessment_id != config.parent_assessment_id
        or parent.status != "valid"
        or parent.value != 1
        or parent.subject.kind != "trace"
        or parent.subject.snapshot_id != sealed.snapshot_id
        or parent.subject.episode_id != sealed.episode_id
        or target.channel != config.consumption.channel
        or config.consumption.episode_id != sealed.episode_id
        or parent.signal != config.consumption.signal
        or target.recipient.kind != "execution"
        or target.recipient.execution is None
        or context is not None
        and context.source != sealed.identity
    ):
        raise ValueError("created_completion_credit_request_invalid")
    from .manifest_assessments import load_task_contract

    contract = load_task_contract(task.data.task_name)
    check = next(
        (item for item in contract.checks if item.check_id == config.consumption.check_id), None
    )
    rule = next(
        (
            item
            for item in contract.credit
            if item.policy == config.policy
            and item.check == config.consumption.check_id
            and item.channel == target.channel
        ),
        None,
    )
    if (
        not isinstance(check, CreatedRetainedCheck)
        or rule is None
        or config.consumption.contract_digest != canonical_contract_digest(contract)
        or config.consumption.selectors_digest != created_selectors_digest(contract, check)
        or config.goal_fields != rule.goal_fields
        or config.completion_selection != rule.completion_selection
        or parent.signal != created_signal(check)
    ):
        raise ValueError("created_completion_contract_or_parent_mismatch")
    raw = json.loads(sealed.source_json)
    safe = {
        "task_evidence": raw["task_evidence"],
        "tool_execution_events": raw.get("tool_execution_events", []),
        "state_write_receipts": raw.get("state_write_receipts", []),
    }
    if digest(safe) != config.source_digest or binding_reason(safe, contract) is not None:
        raise ValueError("created_completion_source_or_authority_mismatch")
    material = {"source": safe, **capture_created_inputs(safe, contract)}
    populations, objects = restore_created_inputs(material, contract)
    population_source, object_source = (
        contract.sources[check.population],
        contract.sources[check.source],
    )
    if (
        not isinstance(population_source, RequestSource)
        or not isinstance(object_source, (JiraIssueSource, HubSpotObjectSource))
        or rule.completion_selection != "earliest"
    ):
        raise ValueError("created_completion_source_or_selection_invalid")
    evaluation = evaluate_created_completion(
        safe,
        check,
        populations[check.population],
        objects[check.source],
        population_source=population_source,
        object_source=object_source,
        bindings=public_bindings(contract),
        goal_fields=rule.goal_fields,
        selection=rule.completion_selection,
    )
    finding = evaluation.findings[0]
    if (
        finding.selection is None
        or finding.status != "eligible"
        or canonical_json(asdict(finding.selection))
        != canonical_json(config.allocation_witness.model_dump(mode="json"))
        or finding.instance_key != config.consumption.instance_key
        or finding.candidate_identity != config.consumption.candidate_identity
        or evaluation.outcome.findings[0].reason != parent.reason
        or execution_subject(sealed, finding.selection.occurrence) != target.recipient
    ):
        raise ValueError("created_completion_allocation_proof_mismatch")
    return (
        vf.CreditContribution(
            contribution_id=uuid.uuid4().hex,
            parent_assessment_ids=(parent.assessment_id,),
            recipient=target.recipient,
            channel=target.channel,
            signal=parent.signal,
            transformation="created_retained_completion_identity@1",
            status="valid",
            value=1,
            allocation=request.allocation,
            attribution="coarse",
            reason=parent.reason,
        ),
    )
