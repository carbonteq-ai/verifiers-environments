"""Native occurrence-obligation outcomes and separately witnessed action credit."""

import json
import uuid
from collections import OrderedDict
from dataclasses import asdict, replace
from typing import Literal, cast

import verifiers.v1 as vf
from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from .capture import canonical_json
from .contracts.base import FrozenModel
from .contracts.effects import EffectSource
from .contracts.engine import binding_reason
from .contracts.gmail_observations import GmailObservationSource
from .contracts.loader import canonical_contract_digest, load_contract
from .contracts.notification_effects import NotificationEffectSource
from .contracts.obligations import (
    ObligationCheck,
    ObligationEvaluation,
    ObligationFinding,
    evaluate_obligations,
    obligation_effect_names,
    obligation_population_names,
    plan_obligation_instances,
    select_obligation_credit,
)
from .contracts.populations import InitialCollectionSource, PopulationEvidence, capture_population
from .contracts.record_writes import RecordWriteSource
from .contracts.requests import RequestPopulationEvidence, RequestSource, capture_request_population
from .contracts.sheet_effects import SheetEffectSource
from .contracts.sheet_reads import SheetReadSource
from .contracts.slack_effects import SlackEffectSource
from .contracts.slack_reads import SlackReadSource
from .contracts.tables import Digest, TableEvidence, TableSource, capture_table
from .manifest_guard_assessments import (
    EffectInput,
    authenticated_view,
    capture_effect_input,
    digest,
    execution_subject,
    selectors_digest,
)

OBLIGATION_PRODUCER = "automationbench.manifest_obligations"
OBLIGATION_OUTPUT = "automationbench.manifest_obligation_result@1"


class ObligationConfig(FrozenModel):
    contract_digest: Digest
    source_digest: Digest
    selectors_digest: Digest
    check_id: StrictStr
    instance_key: StrictStr
    candidate_identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr | StrictInt] | None
    potential_instances: StrictInt

    @model_validator(mode="after")
    def coherent(self):
        if not self.check_id or self.potential_instances < 0:
            raise ValueError("obligation_config_invalid")
        if (self.instance_key == "scope") != (self.candidate_identity is None):
            raise ValueError("obligation_config_candidate_required")
        if self.candidate_identity is not None:
            identity = self.candidate_identity
            authored = identity[0] == "public.request@1" and identity[2] == "authored" and type(identity[3]) is str
            if not all(identity[:2]) or not authored and identity[2] != type(identity[3]).__name__:
                raise ValueError("obligation_config_identity_invalid")
        return self


class WitnessOutput(FrozenModel):
    occurrence: StrictStr
    effect_id: StrictStr
    expected_revision: StrictInt
    applied_revision: StrictInt
    evidence_paths: tuple[tuple[StrictStr | StrictInt, ...], ...]

    @model_validator(mode="after")
    def coherent(self):
        if (not self.occurrence or not self.effect_id or self.expected_revision < 0
                or self.applied_revision != self.expected_revision + 1):
            raise ValueError("obligation_witness_invalid")
        return self


class ObligationOutput(FrozenModel):
    contract_digest: Digest
    source_digest: Digest
    selectors_digest: Digest
    input_digest: Digest
    check_id: StrictStr
    instance_key: StrictStr
    kind: Literal["finding", "scope"]
    semantics: Literal["occurrence", "new_occurrence"]
    candidate_identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr | StrictInt] | None
    status: Literal["valid", "inapplicable", "abstained"]
    value: StrictFloat | StrictInt | None
    reason: StrictStr
    required: StrictBool | None = None
    initially_satisfied: StrictBool | None = None
    baseline_reason: StrictStr = "scope"
    witnesses: tuple[WitnessOutput, ...] = ()
    # Present only for checks declaring aggregates, so legacy receipts keep
    # their bytes. Full member evidence is retained once, on the scope receipt.
    aggregate_digest: Digest | None = Field(default=None, exclude_if=lambda value: value is None)
    aggregate_evidence_json: StrictStr | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def coherent(self):
        if (self.status == "valid") != (self.value is not None) or self.value not in (None, 0, 1):
            raise ValueError("obligation_output_status_invalid")
        if self.aggregate_evidence_json is not None and (
            self.kind != "scope"
            or self.aggregate_digest != digest(json.loads(self.aggregate_evidence_json))
        ):
            raise ValueError("obligation_output_aggregate_evidence_invalid")
        if self.kind == "scope" and (self.aggregate_digest is None) != (
            self.aggregate_evidence_json is None
        ):
            raise ValueError("obligation_output_aggregate_evidence_missing")
        if (self.kind == "scope") != (self.instance_key == "scope"):
            raise ValueError("obligation_output_scope_invalid")
        if (self.kind == "scope") != (self.candidate_identity is None):
            raise ValueError("obligation_output_identity_invalid")
        return self


def aggregate_receipt(check, evaluation, *, scope):
    """Bind receipts to recomputed totals; empty for checks without aggregates."""
    if not check.aggregates:
        return {}
    evidence = [[alias, item.model_dump(mode="json")] for alias, item in evaluation.aggregates]
    receipt = {"aggregate_digest": digest(evidence)}
    if scope:
        receipt["aggregate_evidence_json"] = canonical_json(evidence)
    return receipt


def capture_obligation_inputs(source, contract):
    checks = [check for check in contract.checks if isinstance(check, ObligationCheck)]
    population_names = {name for check in checks for name in obligation_population_names(check)}
    effect_names = {name for check in checks for name in obligation_effect_names(check)}
    populations = {
        name: (capture_request_population(source, spec, tuple(binding for binding in contract.bindings
                         if binding.path[:2] in {("task_evidence", "prompt"), ("task_evidence", "initial")}))
               if isinstance(spec, RequestSource) else
               capture_population(source, spec) if isinstance(spec, InitialCollectionSource)
               else capture_table(source, spec)).model_dump(mode="json")
        for name, spec in contract.sources.items()
        if name in population_names and isinstance(spec, (InitialCollectionSource, TableSource, RequestSource))
    }
    effects = {
        name: asdict(capture_effect_input(source, spec))
        for name, spec in contract.sources.items()
        if name in effect_names and isinstance(spec, (EffectSource, NotificationEffectSource, SheetEffectSource, SlackEffectSource, GmailObservationSource, SlackReadSource, SheetReadSource, RecordWriteSource))
    }
    return {"obligation_population_evidence_json": canonical_json(populations),
            "obligation_effect_evidence_json": canonical_json(effects)}


def restore_obligation_inputs(material, contract):
    # Authenticate adapter receipts against raw current source once per view,
    # rather than trusting syntactically coherent labels and claimed digests.
    expected = capture_obligation_inputs(material["source"], contract)
    for name, value in expected.items():
        if material[name] != value:
            raise ValueError("obligation_input_source_or_selector_mismatch")
    populations = {
        name: (RequestPopulationEvidence.model_validate(value)
               if isinstance(contract.sources[name], RequestSource) else PopulationEvidence.model_validate(value)
               if isinstance(contract.sources[name], InitialCollectionSource)
               else TableEvidence.model_validate(value))
        for name, value in json.loads(expected["obligation_population_evidence_json"]).items()
    }
    effects = {name: EffectInput.model_validate(value).facts()
               for name, value in json.loads(expected["obligation_effect_evidence_json"]).items()}
    return populations, effects


def obligation_signal(check, *, scope=False):
    return vf.SignalDefinition(signal_id=check.signal_id + (".coverage" if scope else ""),
        revision="1", semantics="other" if scope else "outcome",
        units="coverage_indicator" if scope else "binary", minimum=0, maximum=1,
        direction="neutral" if scope else "higher",
        description="Required effect evidence coverage" if scope else "Declared occurrence obligation")


def obligation_requests(source, contract, view, material, trace_subject):
    populations, effects = restore_obligation_inputs(material, contract)
    requests = []
    for check in contract.checks:
        if not isinstance(check, ObligationCheck):
            continue
        cases, potential = plan_obligation_instances(check, populations[check.population], effects[check.source])
        for case in (*cases, None):
            config = ObligationConfig(contract_digest=canonical_contract_digest(contract),
                source_digest=digest(material["source"]), selectors_digest=selectors_digest(contract, check),
                check_id=check.check_id, instance_key=case.instance_key if case else "scope",
                candidate_identity=case.candidate_identity if case else None, potential_instances=potential)
            run = vf.AssessmentRun(run_id=uuid.uuid4().hex, producer_id=OBLIGATION_PRODUCER,
                producer_revision="1", rubric_revision=contract.revision, snapshot_id=source.snapshot_id,
                invocation_id=uuid.uuid4().hex, attempt_id=uuid.uuid4().hex,
                configuration_json=canonical_json(config.model_dump(mode="json")),
                expected=(vf.AssessmentTarget(subject=trace_subject, signal=obligation_signal(check, scope=case is None)),))
            requests.append(("manifest_check", vf.AssessmentRequest(source=source.identity, run=run, views=(view,))))
    return requests


def _evaluate(material, contract, check, populations, effects):
    names = obligation_population_names(check)
    selected = {name: populations[name] for name in names}
    cases, potential = plan_obligation_instances(check, populations[check.population], effects[check.source])
    authority = binding_reason(material["source"], contract)
    if authority is not None:
        result = ObligationEvaluation(digest(material["source"]), digest(check.model_dump(mode="json")),
            tuple(ObligationFinding(check.check_id, case.instance_key, check.signal_id,
                case.candidate_identity, "abstained", None, authority, None, None, authority, (), ())
                for case in cases), False, authority, check.semantics)
    else:
        result = evaluate_obligations(material["source"], check, selected, effects[check.source],
            effect_source=contract.sources[check.source],
            population_sources={name: contract.sources[name] for name in names},
            join_effects={item.alias: effects[item.source] for item in check.effect_joins},
            join_sources={item.alias: contract.sources[item.source] for item in check.effect_joins},
            alternative_effects={item.alias: effects[item.source] for item in check.alternatives},
            alternative_sources={item.alias: contract.sources[item.source] for item in check.alternatives})
    return result, cases, potential


def assess_obligation(task, request, context):
    from .manifest_source import admit_manifest_source

    admitted = admit_manifest_source(task, request, context)
    config = ObligationConfig.model_validate_json(request.run.configuration_json)
    if len(request.views) != 1 or len(request.run.expected) != 1 or context.views != request.views:
        raise ValueError("obligation_transport_shape_invalid")
    view, target = request.views[0], request.run.expected[0]
    trace_subjects = [subject for subject in view.subjects if subject.kind == "trace"]
    if (len(trace_subjects) != 1 or target.subject != trace_subjects[0]
            or target.subject.snapshot_id != request.source.snapshot_id
            or target.subject.episode_id != request.source.episode_id
            or target.subject.trace_id not in request.source.trace_ids
            or request.run.snapshot_id != request.source.snapshot_id):
        raise ValueError("obligation_trace_subject_mismatch")
    key = (request.run.snapshot_id, view.input_digest, config.contract_digest, config.check_id)
    cache = task.__dict__.setdefault("_manifest_obligation_cache", OrderedDict())
    if key not in cache:
        material = admitted.decode()
        contract = load_contract(canonical_json(material["contract"]))
        check = next((item for item in contract.checks if item.check_id == config.check_id), None)
        if not isinstance(check, ObligationCheck) or canonical_contract_digest(contract) != config.contract_digest:
            raise ValueError("obligation_contract_or_check_mismatch")
        populations, effects = restore_obligation_inputs(material, contract)
        evaluation, cases, potential = _evaluate(material, contract, check, populations, effects)
        cache[key] = material, contract, check, evaluation, cases, potential
        while len(cache) > 8:
            cache.popitem(last=False)
    material, contract, check, evaluation, cases, potential = cache[key]
    scope = config.instance_key == "scope"
    if (request.run.producer_id != OBLIGATION_PRODUCER or request.run.producer_revision != "1"
            or request.run.rubric_revision != contract.revision
            or config.source_digest != digest(material["source"])
            or config.selectors_digest != selectors_digest(contract, check)
            or config.potential_instances != potential
            or target.signal != obligation_signal(check, scope=scope)):
        raise ValueError("obligation_configuration_mismatch")
    finding = None
    if not scope:
        case = next((case for case in cases if case.instance_key == config.instance_key), None)
        if case is None or case.candidate_identity != config.candidate_identity:
            raise ValueError("obligation_candidate_mismatch")
        finding = next(item for item in evaluation.findings if item.instance_key == config.instance_key)
    finding = cast(ObligationFinding, finding)
    output = ObligationOutput(contract_digest=config.contract_digest, source_digest=config.source_digest,
        selectors_digest=config.selectors_digest, input_digest=view.input_digest,
        check_id=check.check_id, instance_key=config.instance_key, kind="scope" if scope else "finding",
        semantics=check.semantics,
        candidate_identity=config.candidate_identity,
        status="valid" if scope and evaluation.scope_complete else "abstained" if scope else finding.status,
        value=1 if scope and evaluation.scope_complete else None if scope else finding.value,
        reason=evaluation.reason if scope else finding.reason,
        required=None if scope else finding.required,
        initially_satisfied=None if scope else finding.initially_satisfied,
        baseline_reason="scope" if scope else finding.baseline_reason,
        witnesses=() if scope else tuple(WitnessOutput(**asdict(w)) for w in finding.witnesses),
        **aggregate_receipt(check, evaluation, scope=scope))
    context.record_evidence(OBLIGATION_OUTPUT, output.model_dump(mode="json"), invocation_id=request.run.invocation_id)
    return (vf.Assessment(assessment_id=uuid.uuid4().hex, run_id=request.run.run_id,
        subject=target.subject, view_id=view.view_id, signal=target.signal,
        status=output.status,
        value=output.value, reason=output.reason, invocation_ids=(request.run.invocation_id,)),)


def plan_obligation_credit(source, batches, context, contract):
    if context.source != source.identity:
        raise ValueError("obligation_credit_source_mismatch")
    current = {(run.run_id, run.invocation_id, run.attempt_id) for run in context.current_assessment_runs}
    raw = json.loads(source.source_json)
    safe = {"task_evidence": raw["task_evidence"],
            "tool_execution_events": raw.get("tool_execution_events", []),
            "state_write_receipts": raw.get("state_write_receipts", [])}
    rules = {rule.check: rule for rule in contract.credit if rule.policy == "required_effect_once@1"}
    checks = {check.check_id: check for check in contract.checks if isinstance(check, ObligationCheck)}
    result, seen, channels, inputs, evaluations = [], set(), set(), {}, {}
    views, safe_digest = {}, digest(safe)
    for batch in batches:
        run = batch.run
        if (run.run_id, run.invocation_id, run.attempt_id) not in current:
            continue
        if (run.producer_id != OBLIGATION_PRODUCER or run.producer_revision != "1"
                or run.rubric_revision != contract.revision):
            raise ValueError("obligation_credit_producer_mismatch")
        if run.status != "complete":
            continue
        config = ObligationConfig.model_validate_json(run.configuration_json)
        identity = batch.source.identity if isinstance(batch.source, vf.SourceSnapshot) else batch.source
        if identity != source.identity or len(batch.views) != 1 or len(batch.assessments) != 1:
            raise ValueError("obligation_credit_batch_mismatch")
        view = batch.views[0]
        material = authenticated_view(views, view, safe_digest, canonical_contract_digest(contract),
                                      "obligation_credit_view_mismatch")
        if view.input_digest not in inputs:
            inputs[view.input_digest] = restore_obligation_inputs(material, contract)
        check = checks.get(config.check_id)
        if check is None:
            raise ValueError("obligation_credit_check_unknown")
        evaluation_key = (view.input_digest, check.check_id)
        if evaluation_key not in evaluations:
            evaluations[evaluation_key] = _evaluate(material, contract, check, *inputs[view.input_digest])
        evaluation, _cases, potential = evaluations[evaluation_key]
        receipts = [receipt for receipt in run.execution_evidence if receipt.kind == OBLIGATION_OUTPUT]
        if len(receipts) != 1 or receipts[0].invocation_id != run.invocation_id:
            raise ValueError("obligation_credit_receipt_missing")
        output = ObligationOutput.model_validate_json(receipts[0].payload_json)
        if (output.contract_digest != canonical_contract_digest(contract)
                or output.source_digest != safe_digest or output.input_digest != view.input_digest
                or output.selectors_digest != selectors_digest(contract, check)
                or config.contract_digest != output.contract_digest
                or config.source_digest != output.source_digest
                or config.selectors_digest != output.selectors_digest
                or config.potential_instances != potential or config.instance_key != output.instance_key
                or output.check_id != check.check_id or output.semantics != check.semantics):
            raise ValueError("obligation_credit_receipt_binding_mismatch")
        parent = batch.assessments[0]
        scope = output.kind == "scope"
        expected_aggregates = aggregate_receipt(check, evaluation, scope=scope)
        if (output.aggregate_digest, output.aggregate_evidence_json) != (
            expected_aggregates.get("aggregate_digest"),
            expected_aggregates.get("aggregate_evidence_json"),
        ):
            raise ValueError("obligation_credit_aggregate_mismatch")
        expected_status = output.status
        if (len(run.expected) != 1 or run.expected[0].subject != parent.subject
                or run.expected[0].signal != parent.signal or parent.signal != obligation_signal(check, scope=scope)
                or parent.run_id != run.run_id or parent.view_id != view.view_id
                or parent.invocation_ids != (run.invocation_id,)
                or (parent.status, parent.value, parent.reason) != (expected_status, output.value, output.reason)
                or parent.subject.kind != "trace" or parent.subject.snapshot_id != source.snapshot_id
                or parent.subject.episode_id != source.episode_id
                or parent.subject.trace_id not in source.trace_ids or parent.subject not in view.subjects):
            raise ValueError("obligation_credit_parent_mismatch")
        member = (check.check_id, output.instance_key)
        if member in seen:
            raise ValueError("obligation_credit_duplicate_current_instance")
        seen.add(member)
        if scope:
            if (output.status != ("valid" if evaluation.scope_complete else "abstained")
                    or output.value != (1 if evaluation.scope_complete else None)
                    or output.reason != evaluation.reason or output.required is not None
                    or output.initially_satisfied is not None or output.baseline_reason != "scope"
                    or output.witnesses or config.candidate_identity is not None):
                raise ValueError("obligation_credit_scope_mismatch")
            continue
        finding = next((item for item in evaluation.findings if item.instance_key == output.instance_key), None)
        if (finding is None or finding.candidate_identity != config.candidate_identity
                or output.candidate_identity != finding.candidate_identity
                or (output.status, output.value, output.reason, output.required, output.initially_satisfied,
                    output.baseline_reason, tuple(w.model_dump(mode="json") for w in output.witnesses))
                != (finding.status, finding.value, finding.reason, finding.required, finding.initially_satisfied,
                    finding.baseline_reason, tuple(WitnessOutput(**asdict(w)).model_dump(mode="json") for w in finding.witnesses))):
            raise ValueError("obligation_credit_finding_mismatch")
        rule = rules.get(check.check_id)
        selected = next((item for item in select_obligation_credit(evaluation)
                         if item.instance_key == output.instance_key), None)
        if rule is None or selected is None:
            continue
        effect_source = contract.sources[check.source]
        if isinstance(effect_source, SheetEffectSource) and effect_source.kind == "update":
            # A successful acknowledged noop remains an occurrence outcome.
            # Choose the first qualifying state change so an earlier noop does
            # not hide a later independently verified useful write.
            eligible = {(fact.invocation_id, fact.effect_id)
                        for fact in inputs[view.input_digest][1][check.source].effects
                        if fact.status == "qualified" and fact.params_json is not None
                        and json.loads(fact.params_json)["changed_fields"]}
            witness = next((witness for witness in finding.witnesses
                            if (witness.occurrence, witness.effect_id) in eligible), None)
            if witness is None:
                continue
            selected = replace(selected, occurrence=witness.occurrence, effect_id=witness.effect_id)
        recipient = execution_subject(source, selected.occurrence)
        if recipient is None or recipient.execution is None:
            raise ValueError("obligation_credit_execution_missing")
        consumption = {"episode_id": source.episode_id, "contract_digest": output.contract_digest,
                "check_id": check.check_id, "candidate_identity": output.candidate_identity,
                "instance_key": output.instance_key, "selectors_digest": output.selectors_digest,
                "channel": rule.channel}
        credit_rule = vf.CreditRule(rule_id="automationbench.manifest_required_effect_once", revision="1",
            configuration_json=canonical_json({"consumption": consumption,
                "allocation_witness": {"occurrence": selected.occurrence, "effect_id": selected.effect_id},
                "policy": rule.policy, "signal": parent.signal.model_dump(mode="json")}))
        consumed = False
        for assignment in context.prior_assignments:
            if (assignment.request.source.episode_id != source.episode_id
                    or assignment.request.rule.rule_id != credit_rule.rule_id
                    or assignment.request.rule.revision != credit_rule.revision):
                continue
            previous_config = json.loads(assignment.request.rule.configuration_json)
            previous_consumption = previous_config.get("consumption")
            obligation_fields = ("episode_id", "check_id", "candidate_identity", "channel")
            if not isinstance(previous_consumption, dict) or any(
                canonical_json(previous_consumption.get(field)) != canonical_json(consumption[field])
                for field in obligation_fields
            ):
                continue
            for contribution in assignment.contributions:
                if contribution.status == "valid" and contribution.channel == rule.channel:
                    if canonical_json(previous_consumption) != canonical_json(consumption):
                        raise ValueError("obligation_prior_credit_revision_conflict")
                    if contribution.value != 1 or contribution.signal != parent.signal:
                        raise ValueError("obligation_prior_credit_conflict")
                    consumed = True
        if consumed:
            continue
        channel_key = (recipient.execution.occurrence_id, rule.channel)
        if channel_key in channels:
            raise ValueError("obligation_credit_aggregation_required")
        channels.add(channel_key)
        result.append(("manifest_obligation_identity", vf.CreditRequest(source=source,
            invocation_id=uuid.uuid4().hex, attempt_id=uuid.uuid4().hex, rule=credit_rule,
            accepted=(parent,), targets=(vf.CreditTarget(recipient=recipient, channel=rule.channel),),
            allocation="turn_boundary", overlap_policy="reject")))
    return result


async def manifest_obligation_identity(task, request, context=None):
    if len(request.accepted) != 1 or len(request.targets) != 1:
        raise ValueError("obligation_credit_requires_one_parent_target")
    parent, target = request.accepted[0], request.targets[0]
    config = json.loads(request.rule.configuration_json)
    if (request.rule.rule_id != "automationbench.manifest_required_effect_once"
            or request.rule.revision != "1" or config.get("policy") != "required_effect_once@1"
            or parent.status != "valid" or parent.value != 1 or parent.subject.kind != "trace"
            or target.recipient.kind != "execution" or target.recipient.execution is None
            or target.recipient.execution.origin != "tool_server"
            or target.recipient.execution.invocation_id != config.get("allocation_witness", {}).get("occurrence")
            or not config.get("allocation_witness", {}).get("effect_id")
            or config.get("consumption", {}).get("episode_id") != request.source.episode_id
            or config.get("consumption", {}).get("channel") != target.channel
            or parent.signal != vf.SignalDefinition.model_validate(config["signal"])
            or parent.signal.direction != "higher" or parent.signal.minimum != 0 or parent.signal.maximum != 1
            or context is not None and (request.source.identity if isinstance(request.source, vf.SourceSnapshot)
                                       else request.source) != context.source):
        raise ValueError("obligation_credit_request_invalid")
    if task is None or not isinstance(request.source, vf.SourceSnapshot):
        raise ValueError("obligation_credit_source_proof_unavailable")
    from .manifest_assessments import load_task_contract

    sealed = vf.SourceSnapshot.model_validate(request.source.model_dump(mode="python"))
    contract = load_task_contract(task.data.task_name)
    consumption = config["consumption"]
    check = next((item for item in contract.checks if item.check_id == consumption["check_id"]), None)
    rule = next((item for item in contract.credit if item.check == consumption["check_id"]
                 and item.channel == target.channel and item.policy == "required_effect_once@1"), None)
    if (not isinstance(check, ObligationCheck) or rule is None
            or canonical_contract_digest(contract) != consumption["contract_digest"]
            or selectors_digest(contract, check) != consumption["selectors_digest"]
            or parent.signal != obligation_signal(check)
            or parent.subject.snapshot_id != sealed.snapshot_id or parent.subject.episode_id != sealed.episode_id):
        raise ValueError("obligation_credit_contract_or_parent_mismatch")
    raw = json.loads(sealed.source_json)
    safe = {"task_evidence": raw["task_evidence"], "tool_execution_events": raw.get("tool_execution_events", []),
            "state_write_receipts": raw.get("state_write_receipts", [])}
    material = {"source": safe, **capture_obligation_inputs(safe, contract)}
    populations, effects = restore_obligation_inputs(material, contract)
    evaluation, _, _ = _evaluate(material, contract, check, populations, effects)
    finding = next((item for item in evaluation.findings if item.instance_key == consumption["instance_key"]), None)
    selected = next((item for item in select_obligation_credit(evaluation)
                     if item.instance_key == consumption["instance_key"]), None)
    effect_source = contract.sources[check.source]
    if selected is not None and finding is not None and isinstance(effect_source, SheetEffectSource) and effect_source.kind == "update":
        eligible = {(fact.invocation_id, fact.effect_id) for fact in effects[check.source].effects
                    if fact.status == "qualified" and fact.params_json is not None
                    and json.loads(fact.params_json)["changed_fields"]}
        witness = next((item for item in finding.witnesses if (item.occurrence, item.effect_id) in eligible), None)
        selected = replace(selected, occurrence=witness.occurrence, effect_id=witness.effect_id) if witness else None
    if (finding is None or selected is None or finding.status != "valid" or finding.value != 1
            or finding.reason != parent.reason
            or canonical_json(finding.candidate_identity) != canonical_json(consumption["candidate_identity"])
            or config["allocation_witness"] != {"occurrence": selected.occurrence, "effect_id": selected.effect_id}
            or execution_subject(sealed, selected.occurrence) != target.recipient):
        raise ValueError("obligation_credit_allocation_proof_mismatch")
    return (vf.CreditContribution(contribution_id=uuid.uuid4().hex,
        parent_assessment_ids=(parent.assessment_id,), recipient=target.recipient,
        channel=target.channel, signal=parent.signal, transformation="required_effect_identity@1",
        status="valid", value=1, allocation=request.allocation, attribution="coarse", reason=parent.reason),)
