"""Native transport for manifest guard instances; checking precedes credit."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import OrderedDict
from dataclasses import asdict
from typing import Literal

import verifiers.v1 as vf
from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from .capture import canonical_json
from .contracts.base import FrozenModel
from .contracts.effects import EffectEvidence, EffectFact, EffectSource, capture_effects
from .contracts.engine import binding_reason
from .contracts.existentials import exists_names
from .contracts.gmail_observations import GmailObservationSource, capture_gmail_observations
from .contracts.guards import (
    GuardCheck,
    GuardEvaluation,
    GuardFinding,
    evaluate_guard,
    plan_guard_instances,
)
from .contracts.loader import canonical_contract_digest, load_contract
from .contracts.notification_effects import NotificationEffectSource, capture_notification_effects
from .contracts.populations import InitialCollectionSource, PopulationEvidence, capture_population
from .contracts.record_writes import RecordWriteSource, capture_record_writes
from .contracts.requests import RequestPopulationEvidence, RequestSource, capture_request_population
from .contracts.sheet_effects import SheetEffectSource, capture_sheet_effects
from .contracts.slack_effects import SlackEffectSource, capture_slack_effects
from .contracts.slack_reads import SlackReadSource, capture_slack_reads
from .contracts.tables import Digest, TableEvidence, TableSource, capture_table

GUARD_PRODUCER = "automationbench.manifest_guards"
GUARD_OUTPUT = "automationbench.manifest_guard_result@1"


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class FactInput(FrozenModel):
    effect_id: StrictStr | None
    invocation_id: StrictStr = Field(min_length=1)
    origin: Literal["tool_server"]
    kind: Literal["create_task", "add_task_to_section", "send", "append", "update", "channel_message", "direct_message", "read_message", "create", "delete"]
    params_json: StrictStr | None
    status: Literal["qualified", "unavailable"]
    reason: StrictStr = Field(min_length=1)
    expected_revision: StrictInt | None = None
    applied_revision: StrictInt | None = None

    @model_validator(mode="after")
    def qualified_fact(self):
        if self.params_json is not None:
            params = json.loads(self.params_json)
            if not isinstance(params, dict) or self.params_json != canonical_json(params):
                raise ValueError("guard_params_canonical_object_required")
        if self.status == "qualified" and (
            not self.effect_id
            or self.params_json is None
            or self.expected_revision is None
            or self.expected_revision < 0
            or self.applied_revision != self.expected_revision + 1
        ):
            raise ValueError("guard_qualified_effect_metadata_invalid")
        return self


class EffectInput(FrozenModel):
    source_digest: Digest
    selector_digest: Digest
    effects: tuple[FactInput, ...]
    complete: StrictBool
    reason: StrictStr = Field(min_length=1)

    @model_validator(mode="after")
    def coherent_inventory(self):
        keys = [(item.origin, item.invocation_id, item.effect_id) for item in self.effects]
        if len(set(keys)) != len(keys):
            raise ValueError("guard_duplicate_effect_identity")
        if self.complete and any(item.status != "qualified" for item in self.effects):
            raise ValueError("guard_complete_inventory_has_unknown_effect")
        return self

    def facts(self) -> EffectEvidence:
        return EffectEvidence(
            self.source_digest,
            self.selector_digest,
            tuple(EffectFact(**item.model_dump()) for item in self.effects),
            self.complete,
            self.reason,
        )


class GuardOutput(FrozenModel):
    contract_digest: Digest
    source_digest: Digest
    input_digest: Digest
    selectors_digest: Digest
    check_id: StrictStr = Field(min_length=1)
    instance_key: StrictStr = Field(min_length=1)
    kind: Literal["finding", "compliance"]
    status: Literal["valid", "abstained"]
    value: StrictInt | StrictFloat | None
    reason: StrictStr = Field(min_length=1)
    occurrence: StrictStr | None = None
    effect_id: StrictStr | None = None
    candidate_identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr | StrictInt] | None = None

    @model_validator(mode="after")
    def result_shape(self):
        if (self.status == "valid") != (self.value is not None) or self.value not in (None, 0, 1):
            raise ValueError("guard_result_status_value_mismatch")
        if self.kind == "compliance":
            if self.instance_key != "scope" or any(
                item is not None
                for item in (self.occurrence, self.effect_id, self.candidate_identity)
            ):
                raise ValueError("guard_compliance_metadata_invalid")
        elif self.instance_key == "scope" or not self.occurrence or self.candidate_identity is None:
            raise ValueError("guard_finding_metadata_invalid")
        if self.kind == "finding" and self.value == 1 and self.effect_id is None:
            raise ValueError("guard_positive_effect_identity_required")
        return self


class GuardCaseConfig(FrozenModel):
    instance_key: Digest
    occurrence: StrictStr = Field(min_length=1)
    effect_id: StrictStr | None
    candidate_identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr | StrictInt]

    @model_validator(mode="after")
    def coherent_case(self):
        identity = self.candidate_identity
        # Authored request members use ("public.request@1", digest, "authored", key).
        authored = identity[0] == "public.request@1" and identity[2] == "authored" and type(identity[3]) is str
        if (
            not all(identity[:2])
            or not authored and identity[2] != type(identity[3]).__name__
            or (type(identity[3]) is str and not identity[3])
        ):
            raise ValueError("guard_config_candidate_identity_invalid")
        if self.effect_id is not None and not self.effect_id:
            raise ValueError("guard_config_effect_identity_empty")
        if self.instance_key != digest(
            [
                identity,
                "tool_server",
                self.occurrence,
                self.effect_id,
            ]
        ):
            raise ValueError("guard_config_instance_identity_mismatch")
        return self


class GuardRunConfig(FrozenModel):
    contract_digest: Digest
    source_digest: Digest
    selectors_digest: Digest
    check_id: StrictStr = Field(min_length=1)
    instance_key: StrictStr = Field(min_length=1)
    case: GuardCaseConfig | None
    potential_instances: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def coherent_instance(self):
        if self.instance_key == "scope":
            if self.case is not None:
                raise ValueError("guard_scope_case_invalid")
        elif self.case is None or self.case.instance_key != self.instance_key:
            raise ValueError("guard_config_case_required")
        return self


def parse_guard_config(text: str) -> GuardRunConfig:
    return GuardRunConfig.model_validate_json(text)


def capture_effect_input(source, spec):
    if isinstance(spec, RecordWriteSource):
        return capture_record_writes(source, spec)
    if isinstance(spec, GmailObservationSource):
        return capture_gmail_observations(source, spec)
    if isinstance(spec, SlackReadSource):
        return capture_slack_reads(source, spec)
    if isinstance(spec, SlackEffectSource):
        return capture_slack_effects(source, spec)
    if isinstance(spec, SheetEffectSource):
        return capture_sheet_effects(source, spec)
    if isinstance(spec, NotificationEffectSource):
        return capture_notification_effects(source, spec)
    return capture_effects(source, spec)


def _guard_names(contract):
    checks = [check for check in contract.checks if isinstance(check, GuardCheck)]
    table_names = {name for check in checks
                   for name in (check.population, *(lookup.source for lookup in check.lookups),
                                *exists_names(check))}
    effect_names = {name for check in checks
                    for name in (check.source, *(item.source for item in check.effect_joins))}
    return table_names, effect_names


def _capture_population(source, spec, contract):
    if isinstance(spec, RequestSource):
        bindings = tuple(binding for binding in contract.bindings
                         if binding.path[:2] in {("task_evidence", "prompt"), ("task_evidence", "initial")})
        return capture_request_population(source, spec, bindings)
    if isinstance(spec, InitialCollectionSource):
        return capture_population(source, spec)
    return capture_table(source, spec)


def capture_guard_inputs(source, contract) -> dict:
    # Populations of every supported kind share the legacy key, so Sheets-only
    # contracts keep their exact material bytes.
    table_names, effect_names = _guard_names(contract)
    tables = {
        key: _capture_population(source, spec, contract).model_dump(mode="json")
        for key, spec in contract.sources.items()
        if key in table_names and isinstance(spec, (TableSource, InitialCollectionSource, RequestSource))
    }
    effects = {
        key: asdict(capture_effect_input(source, spec))
        for key, spec in contract.sources.items()
        if key in effect_names and isinstance(spec, (EffectSource, NotificationEffectSource, SheetEffectSource, SlackEffectSource, RecordWriteSource, GmailObservationSource, SlackReadSource))
    }
    return {
        "table_evidence_json": canonical_json(tables),
        "effect_evidence_json": canonical_json(effects),
    }


def restore_guard_inputs(material, contract):
    actual = capture_guard_inputs(material["source"], contract)
    if any(material.get(key) != value for key, value in actual.items()):
        raise ValueError("guard_input_raw_source_membership_mismatch")
    table_names, effect_names = _guard_names(contract)
    models = {TableSource: TableEvidence, InitialCollectionSource: PopulationEvidence,
              RequestSource: RequestPopulationEvidence}
    tables = {
        key: models[type(contract.sources[key])].model_validate(value)
        for key, value in json.loads(material["table_evidence_json"]).items()
    }
    effects = {
        key: EffectInput.model_validate(value).facts()
        for key, value in json.loads(material["effect_evidence_json"]).items()
    }
    table_sources = {
        key: spec for key, spec in contract.sources.items()
        if key in table_names and isinstance(spec, (TableSource, InitialCollectionSource, RequestSource))
    }
    effect_sources = {
        key: spec
        for key, spec in contract.sources.items()
        if key in effect_names and isinstance(spec, (EffectSource, NotificationEffectSource, SheetEffectSource, SlackEffectSource, RecordWriteSource, GmailObservationSource, SlackReadSource))
    }
    if set(tables) != set(table_sources) or set(effects) != set(effect_sources):
        raise ValueError("guard_input_inventory_mismatch")
    identity = digest(material["source"])
    for key, value in list(tables.items()) + list(effects.items()):
        spec = contract.sources[key]
        if value.source_digest != identity or value.selector_digest != digest(
            spec.model_dump(mode="json", exclude_none=isinstance(spec, RequestSource))
        ):
            raise ValueError("guard_input_source_or_selector_mismatch")
    for key, value in effects.items():
        if any(fact.kind != effect_sources[key].kind for fact in value.effects):
            raise ValueError("guard_input_effect_kind_mismatch")
    return tables, effects


def required_tables(check):
    # Aggregate populations join obligation selector identity only when declared.
    return {
        check.population,
        *(lookup.source for lookup in check.lookups),
        *(item.aggregate.population for item in getattr(check, "aggregates", ())),
        *(item.population for item in getattr(check, "selections", ())),
        *exists_names(check),
    }


def selectors_digest(contract, check):
    return digest(
        {
            key: contract.sources[key].model_dump(mode="json")
            for key in required_tables(check) | {check.source}
            | {item.source for item in getattr(check, "effect_joins", ())}
            | {item.source for item in getattr(check, "alternatives", ())}
        }
    )


def guard_signal(check: GuardCheck, *, scope=False, penalty=False):
    return vf.SignalDefinition(
        signal_id=check.signal_id + (".compliance" if scope else ".penalty" if penalty else ""),
        revision="1",
        semantics="outcome",
        units="binary_penalty" if penalty else "binary",
        description="Declared prohibited effect penalty"
        if penalty
        else "Declared guard compliance"
        if scope
        else "Declared prohibited effect occurred",
        minimum=-1 if penalty else 0,
        maximum=0 if penalty else 1,
        direction="higher" if scope or penalty else "lower",
    )


def execution_subject(source, occurrence):
    matches = [
        item
        for item in source.executions
        if item.origin == "tool_server" and item.invocation_id == occurrence
    ]
    if len(matches) != 1:
        return None
    return vf.SubjectRef(
        kind="execution",
        snapshot_id=source.snapshot_id,
        episode_id=source.episode_id,
        trace_id=matches[0].trace_id,
        execution=matches[0],
    )


def guard_requests(source, contract, view, material, trace_subject):
    tables, effects = restore_guard_inputs(material, contract)
    requests = []
    for check in contract.checks:
        if not isinstance(check, GuardCheck):
            continue
        cases, potential = plan_guard_instances(
            check, tables[check.population], effects[check.source]
        )
        for case in (*cases, None):
            config = {
                "contract_digest": canonical_contract_digest(contract),
                "source_digest": digest(material["source"]),
                "selectors_digest": selectors_digest(contract, check),
                "check_id": check.check_id,
                "instance_key": case.instance_key if case is not None else "scope",
                "case": asdict(case) if case is not None else None,
                "potential_instances": potential,
            }
            subject = (
                execution_subject(source, case.occurrence) if case is not None else trace_subject
            )
            subject = subject or trace_subject
            run = vf.AssessmentRun(
                run_id=uuid.uuid4().hex,
                producer_id=GUARD_PRODUCER,
                producer_revision="1",
                rubric_revision=contract.revision,
                snapshot_id=source.snapshot_id,
                invocation_id=uuid.uuid4().hex,
                attempt_id=uuid.uuid4().hex,
                configuration_json=canonical_json(config),
                expected=(
                    vf.AssessmentTarget(
                        subject=subject, signal=guard_signal(check, scope=case is None)
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


def assess_guard(task, request, context):
    from .manifest_source import admit_manifest_source

    admitted = admit_manifest_source(task, request, context)
    config = parse_guard_config(request.run.configuration_json).model_dump(mode="json")
    if len(request.views) != 1 or len(request.run.expected) != 1 or context.views != request.views:
        raise ValueError("guard_requested_transport_shape_invalid")
    view = request.views[0]
    trace_subjects = tuple(subject for subject in view.subjects if subject.kind == "trace")
    if len(trace_subjects) != 1:
        raise ValueError("guard_requested_trace_subject_invalid")
    trace_subject = trace_subjects[0]
    if (
        trace_subject.snapshot_id != request.source.snapshot_id
        or trace_subject.episode_id != request.source.episode_id
        or trace_subject.trace_id not in request.source.trace_ids
        or request.run.snapshot_id != request.source.snapshot_id
    ):
        raise ValueError("guard_requested_trace_membership_invalid")
    key = (
        request.run.snapshot_id,
        view.view_id,
        view.input_digest,
        config["contract_digest"],
        config["check_id"],
    )
    cache = task.__dict__.setdefault("_manifest_guard_cache", OrderedDict())
    if key not in cache:
        material = admitted.decode()
        contract = load_contract(canonical_json(material["contract"]))
        if config["contract_digest"] != canonical_contract_digest(contract):
            raise ValueError("guard_requested_contract_mismatch")
        check = next(
            (item for item in contract.checks if item.check_id == config["check_id"]), None
        )
        if not isinstance(check, GuardCheck):
            raise ValueError("guard_requested_check_unknown")
        input_key = (request.run.snapshot_id, view.view_id, view.input_digest, config["contract_digest"])
        input_cache = task.__dict__.setdefault("_manifest_guard_input_cache", OrderedDict())
        if input_key not in input_cache:
            input_cache[input_key] = restore_guard_inputs(material, contract)
            while len(input_cache) > 8:
                input_cache.popitem(last=False)
        tables, effects = input_cache[input_key]
        keys = required_tables(check)
        selected_tables = {name: tables[name] for name in keys}
        selected_sources = {
            name: spec
            for name, spec in contract.sources.items()
            if name in keys and isinstance(spec, (TableSource, InitialCollectionSource, RequestSource))
        }
        effect_source = contract.sources[check.source]
        if not isinstance(effect_source, (EffectSource, NotificationEffectSource, SheetEffectSource, SlackEffectSource, RecordWriteSource)):
            raise ValueError("guard_requested_effect_source_invalid")
        cases, potential = plan_guard_instances(
            check, tables[check.population], effects[check.source]
        )
        authority = binding_reason(material["source"], contract)
        if authority is not None:
            evaluation = GuardEvaluation(
                tuple(
                    GuardFinding(
                        check.check_id,
                        case.instance_key,
                        check.signal_id,
                        None,
                        authority,
                        case.occurrence,
                        case.effect_id,
                        case.candidate_identity,
                        (),
                    )
                    for case in cases
                ),
                None,
                authority,
            )
        else:
            evaluation = evaluate_guard(
                material["source"],
                check,
                selected_tables,
                effects[check.source],
                effect_source=effect_source,
                table_sources=selected_sources,
                join_effects={item.alias: effects[item.source] for item in check.effect_joins},
                join_sources={item.alias: contract.sources[item.source] for item in check.effect_joins},
            )
        cache[key] = (material, contract, check, evaluation, cases, potential)
        while len(cache) > 8:
            cache.popitem(last=False)
    material, contract, check, evaluation, cases, potential = cache[key]
    if (
        config["source_digest"] != digest(material["source"])
        or config["selectors_digest"] != selectors_digest(contract, check)
        or config["potential_instances"] != potential
    ):
        raise ValueError("guard_requested_input_mismatch")
    scope = config["instance_key"] == "scope"
    target = request.run.expected[0]
    if target.signal != guard_signal(check, scope=scope):
        raise ValueError("guard_requested_signal_mismatch")
    if scope:
        if config["case"] is not None:
            raise ValueError("guard_scope_case_invalid")
        if target.subject != trace_subject:
            raise ValueError("guard_requested_scope_subject_invalid")
        value, reason = evaluation.compliance, evaluation.reason
        occurrence, effect_id, candidate = None, None, None
    else:
        case = next((item for item in cases if item.instance_key == config["instance_key"]), None)
        if case is None or canonical_json(asdict(case)) != canonical_json(config["case"]):
            raise ValueError("guard_requested_instance_unknown")
        finding = next(
            (item for item in evaluation.findings if item.instance_key == case.instance_key), None
        )
        if finding is None:
            raise ValueError("guard_evaluation_instance_missing")
        value, reason = finding.value, finding.reason
        recipient = execution_subject(request.source, finding.occurrence)
        if target.subject != (recipient or trace_subject):
            raise ValueError("guard_requested_execution_mismatch")
        if recipient is None:
            value, reason = None, "guard_execution_membership_unavailable"
        occurrence, effect_id, candidate = (
            finding.occurrence,
            finding.effect_id,
            finding.candidate_identity,
        )
    output = GuardOutput(
        contract_digest=canonical_contract_digest(contract),
        source_digest=digest(material["source"]),
        selectors_digest=selectors_digest(contract, check),
        input_digest=view.input_digest,
        check_id=check.check_id,
        instance_key=config["instance_key"],
        kind="compliance" if scope else "finding",
        status="valid" if value is not None else "abstained",
        value=value,
        reason=reason,
        occurrence=occurrence,
        effect_id=effect_id,
        candidate_identity=candidate,
    )
    context.record_evidence(
        GUARD_OUTPUT, output.model_dump(mode="json"), invocation_id=request.run.invocation_id
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


def plan_guard_credit(source, batches, context, contract):
    """Consume only current immutable guard receipts; preserve prefix consumption."""
    if context.source != source.identity:
        raise ValueError("guard_credit_source_mismatch")
    contract_id = canonical_contract_digest(contract)
    current = {
        (run.run_id, run.invocation_id, run.attempt_id) for run in context.current_assessment_runs
    }
    raw = json.loads(source.source_json)
    safe = {
        "task_evidence": raw["task_evidence"],
        "tool_execution_events": raw.get("tool_execution_events", []),
        "state_write_receipts": raw.get("state_write_receipts", []),
    }
    rules = {rule.check: rule for rule in contract.credit if rule.policy == "per_effect_negative@1"}
    checks = {check.check_id: check for check in contract.checks if isinstance(check, GuardCheck)}
    requests, planned = [], set()
    instances = set()
    inputs = {}
    plans = {}
    for batch in batches:
        run = batch.run
        if (run.run_id, run.invocation_id, run.attempt_id) not in current:
            continue
        if run.producer_id != GUARD_PRODUCER or run.producer_revision != "1":
            raise ValueError("guard_credit_producer_mismatch")
        if run.status not in ("complete", "partial") or len(batch.assessments) != 1:
            continue
        batch_identity = (
            batch.source.identity if isinstance(batch.source, vf.SourceSnapshot) else batch.source
        )
        if batch_identity != source.identity or len(batch.views) != 1:
            raise ValueError("guard_credit_snapshot_or_view_mismatch")
        config = parse_guard_config(run.configuration_json).model_dump(mode="json")
        check = checks.get(config["check_id"])
        if check is None or config.get("contract_digest") != contract_id:
            raise ValueError("guard_credit_configuration_mismatch")
        view = batch.views[0]
        material = json.loads(view.input_json)
        if (
            digest(material["source"]) != digest(safe)
            or canonical_contract_digest(load_contract(canonical_json(material["contract"])))
            != contract_id
            or view.input_digest != digest(material)
        ):
            raise ValueError("guard_credit_input_binding_mismatch")
        if view.input_digest not in inputs:
            inputs[view.input_digest] = restore_guard_inputs(material, contract)
        tables, effects = inputs[view.input_digest]
        plan_key = (view.input_digest, check.check_id)
        if plan_key not in plans:
            cases, potential = plan_guard_instances(
                check, tables[check.population], effects[check.source]
            )
            plans[plan_key] = ({case.instance_key: case for case in cases}, potential)
        cases, potential = plans[plan_key]
        receipts = [item for item in run.execution_evidence if item.kind == GUARD_OUTPUT]
        if len(receipts) != 1 or receipts[0].invocation_id != run.invocation_id:
            raise ValueError("guard_credit_output_receipt_unresolved")
        output = GuardOutput.model_validate_json(receipts[0].payload_json)
        if (
            output.contract_digest != contract_id
            or output.source_digest != digest(safe)
            or output.input_digest != view.input_digest
            or output.selectors_digest != selectors_digest(contract, check)
            or output.check_id != check.check_id
            or output.instance_key != config.get("instance_key")
            or config.get("source_digest") != output.source_digest
            or config.get("selectors_digest") != output.selectors_digest
            or type(config.get("potential_instances")) is not int
            or config.get("potential_instances") != potential
        ):
            raise ValueError("guard_credit_output_binding_mismatch")
        parent = batch.assessments[0]
        scope = output.kind == "compliance"
        if (
            parent.signal != guard_signal(check, scope=scope)
            or (parent.status, parent.value, parent.reason)
            != (output.status, output.value, output.reason)
            or parent.run_id != run.run_id
            or parent.view_id != view.view_id
            or parent.invocation_ids != (run.invocation_id,)
            or len(run.expected) != 1
            or run.expected[0].subject != parent.subject
            or run.expected[0].signal != parent.signal
        ):
            raise ValueError("guard_credit_published_parent_mismatch")
        identity = (check.check_id, output.instance_key)
        if identity in instances:
            raise ValueError("guard_credit_duplicate_current_instance")
        instances.add(identity)
        if scope:
            if config.get("case") is not None:
                raise ValueError("guard_credit_scope_case_invalid")
            continue
        case = cases.get(output.instance_key)
        if (
            case is None
            or canonical_json(asdict(case)) != canonical_json(config.get("case"))
            or (output.occurrence, output.effect_id, output.candidate_identity)
            != (case.occurrence, case.effect_id, case.candidate_identity)
        ):
            raise ValueError("guard_credit_instance_membership_mismatch")
        rule = rules.get(check.check_id)
        if rule is None or output.status != "valid" or output.value != 1:
            continue
        recipient = execution_subject(source, output.occurrence)
        if recipient is None or recipient.execution is None or parent.subject != recipient:
            raise ValueError("guard_credit_execution_membership_mismatch")
        signal = guard_signal(check, penalty=True)
        credit_rule = vf.CreditRule(
            rule_id="automationbench.manifest_per_effect_negative",
            revision="1",
            configuration_json=canonical_json(
                {
                    "contract_digest": contract_id,
                    "check_id": check.check_id,
                    "instance_key": output.instance_key,
                    "effect_id": output.effect_id,
                    "policy": rule.policy,
                    "penalty_signal": signal.model_dump(mode="json"),
                }
            ),
        )
        key = (recipient.execution.occurrence_id, rule.channel)
        if key in planned:
            raise ValueError("guard_credit_aggregation_required")
        planned.add(key)
        consumed = False
        for assignment in context.prior_assignments:
            if (
                assignment.request.source.episode_id != source.episode_id
                or assignment.request.rule != credit_rule
            ):
                continue
            for contribution in assignment.contributions:
                if (
                    contribution.status == "valid"
                    and contribution.recipient.execution is not None
                    and contribution.recipient.execution.occurrence_id
                    == recipient.execution.occurrence_id
                    and contribution.channel == rule.channel
                ):
                    if contribution.value != -1 or contribution.signal != signal:
                        raise ValueError("guard_prior_credit_conflict")
                    consumed = True
        if not consumed:
            requests.append(
                (
                    "manifest_penalty",
                    vf.CreditRequest(
                        source=source.identity,
                        invocation_id=uuid.uuid4().hex,
                        attempt_id=uuid.uuid4().hex,
                        rule=credit_rule,
                        accepted=(parent,),
                        targets=(vf.CreditTarget(recipient=recipient, channel=rule.channel),),
                        allocation="turn_boundary",
                        overlap_policy="reject",
                    ),
                )
            )
    return requests


async def manifest_penalty(task, request, context=None):
    """Explicit harm-to-penalty mapping with a derived bounded signal."""
    if len(request.accepted) != 1 or len(request.targets) != 1:
        raise ValueError("guard_penalty_requires_single_parent_and_target")
    parent, target = request.accepted[0], request.targets[0]
    config = json.loads(request.rule.configuration_json)
    signal = vf.SignalDefinition.model_validate(config["penalty_signal"])
    if (
        request.rule.rule_id != "automationbench.manifest_per_effect_negative"
        or request.rule.revision != "1"
        or config.get("policy") != "per_effect_negative@1"
        or parent.status != "valid"
        or parent.value != 1
        or parent.subject != target.recipient
        or target.recipient.kind != "execution"
        or signal.signal_id != parent.signal.signal_id + ".penalty"
        or signal.minimum != -1
        or signal.maximum != 0
        or signal.direction != "higher"
        or signal.revision != parent.signal.revision
        or context is not None
        and request.source != context.source
    ):
        raise ValueError("guard_penalty_request_invalid")
    return (
        vf.CreditContribution(
            contribution_id=uuid.uuid4().hex,
            parent_assessment_ids=(parent.assessment_id,),
            recipient=target.recipient,
            channel=target.channel,
            signal=signal,
            transformation="prohibited_effect_penalty@1",
            status="valid",
            value=-1,
            allocation=request.allocation,
            attribution="coarse",
            reason=parent.reason,
        ),
    )
