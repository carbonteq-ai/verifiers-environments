"""Cited decisions about exclusion narratives, never a mandatory-summary rule.

This module validates evidence and reduces decisions; it does not infer meaning
from names, field labels, regular expressions, or equality with action values.
A semantic producer must decide the whole output in the retained action context.
Its declaration and citations establish provenance, not proof of judge accuracy.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Literal, cast

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator
from verifiers.v1.assessments import SourceSnapshot

from ..capture import canonical_json
from .authored_outputs import (
    AuthoredOutputEvidence,
    AuthoredOutputSource,
    validate_authored_outputs,
)
from .base import FrozenModel, Identifier
from .external_outputs import (
    ActionRelation,
    ExternalOutputEvidence,
    ExternalOutputSource,
    validate_external_outputs,
)
from .invocation_inventory import InvocationEntry, capture_invocation_inventory
from .populations import Path
from .tables import Digest

SummaryState = Literal["compliant", "violation", "inapplicable", "abstained"]


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class SummaryAssessor(FrozenModel):
    """Declared producer configuration; the native driver owns its execution."""

    assessor_id: Identifier
    revision: Identifier
    parser_revision: Identifier
    rubric_revision: Identifier
    model_selection_json: StrictStr

    @model_validator(mode="after")
    def canonical_selection(self):
        value = json.loads(self.model_selection_json)
        if (
            not isinstance(value, dict)
            or not value
            or canonical_json(value) != self.model_selection_json
        ):
            raise ValueError("summary_assessor_selection_requires_nonempty_canonical_object")
        return self


class SummaryExclusionCheck(FrozenModel):
    check_id: Identifier
    signal_id: Identifier
    role: Literal["harm"] = "harm"
    operator: Literal["summary_exclusions@1"] = "summary_exclusions@1"
    source: Identifier
    external: Identifier
    policy_path: Path
    policy_digest: Digest
    assessor: SummaryAssessor | None = None

    @model_validator(mode="after")
    def public_policy(self):
        if (
            len(self.policy_path) < 2
            or self.policy_path[0] != "task_evidence"
            or self.policy_path[1] not in {"prompt", "initial"}
            or any(type(part) is int and part < 0 for part in self.policy_path)
        ):
            raise ValueError("summary_policy_requires_public_source_path")
        if self.source == self.external:
            raise ValueError("summary_output_source_aliases_must_differ")
        return self


class SummaryOutput(FrozenModel):
    output_key: Identifier
    inventory: Literal["assistant", "external"]
    output_id: Identifier
    output_digest: Digest
    text: StrictStr
    channel: StrictStr | None = None
    surface: StrictStr
    fact_json: StrictStr


class SummaryRelation(FrozenModel):
    relation_id: Digest
    relation: ActionRelation


class SummaryPolicyContext(FrozenModel):
    source_digest: Digest
    check_digest: Digest
    context_digest: Digest
    policy_path: Path
    policy_digest: Digest
    policy_text: StrictStr
    outputs: tuple[SummaryOutput, ...]
    relations: tuple[SummaryRelation, ...]
    invocations: tuple[InvocationEntry, ...]
    assistant_closed: StrictBool
    external_closed: StrictBool
    invocation_closed: StrictBool
    coverage_reasons: tuple[StrictStr, ...]


class SummaryOutputCitation(FrozenModel):
    """A nonempty Python Unicode-code-point interval in one exact output."""

    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(ge=1)
    quote: StrictStr = Field(min_length=1)

    @model_validator(mode="after")
    def nonempty(self):
        if self.end <= self.start:
            raise ValueError("summary_output_citation_empty_or_reversed")
        return self


class SummaryDecision(FrozenModel):
    context_digest: Digest
    output_key: Identifier
    output_digest: Digest
    assessor_id: Identifier
    assessor_revision: Identifier
    state: SummaryState
    reason: Identifier
    citations: tuple[SummaryOutputCitation, ...] = ()
    relation_ids: tuple[Digest, ...] = ()
    invocation_ids: tuple[Identifier, ...] = ()


class SummaryFinding(FrozenModel):
    output_key: Identifier
    output_id: Identifier
    output_digest: Digest
    state: SummaryState
    reason: Identifier
    decision: SummaryDecision | None = None
    basis: Literal["semantic", "empty_text", "undecided"] = "undecided"


class SummaryEvaluation(FrozenModel):
    source_digest: Digest
    check_id: Identifier
    signal_id: Identifier
    status: SummaryState
    compliance: float | None
    reason: Identifier
    context: SummaryPolicyContext | None = None
    findings: tuple[SummaryFinding, ...] = ()
    decision_errors: tuple[StrictStr, ...] = ()
    producer: SummaryAssessor | None = None
    full_output_ids: tuple[Identifier, ...] = ()
    basis: Literal["semantic", "empty_inventory", "empty_text", "undecided"] = "undecided"


def _policy(source, check):
    value = source
    for part in check.policy_path:
        if isinstance(value, Mapping):
            if type(part) is not str or part not in value:
                raise ValueError("summary_policy_source_unavailable")
            value = value[part]
        elif isinstance(value, (list, tuple)):
            if type(part) is not int or not 0 <= part < len(value):
                raise ValueError("summary_policy_source_unavailable")
            value = value[part]
        else:
            raise TypeError("summary_policy_source_unavailable")
    if type(value) is not str or not value.strip():
        raise ValueError("summary_policy_source_requires_text")
    if _digest(value) != check.policy_digest:
        raise ValueError("summary_policy_source_digest_changed")
    return value


def prepare_summary_context(
    source: Mapping,
    check: SummaryExclusionCheck,
    assistant: AuthoredOutputEvidence,
    external: ExternalOutputEvidence,
    *,
    assistant_source: AuthoredOutputSource,
    external_source: ExternalOutputSource,
    native_source: SourceSnapshot | None = None,
) -> SummaryPolicyContext:
    """Re-capture inventories before exposing immutable, source-bound judge input.

    Full source is still available to the native assessor's preparation strategy.
    Invocation records preserve reads and returned value context even when there
    is no mutation relation. No output is exempted because of its surface/name.
    """
    check = SummaryExclusionCheck.model_validate(check.model_dump(mode="python", warnings=False))
    return _prepare_output_policy_context(
        source,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=native_source,
    )


def _prepare_output_policy_context(
    source: Mapping,
    check: Any,
    assistant: AuthoredOutputEvidence,
    external: ExternalOutputEvidence,
    *,
    assistant_source: AuthoredOutputSource,
    external_source: ExternalOutputSource,
    native_source: SourceSnapshot | None = None,
) -> SummaryPolicyContext:
    """Shared factual preparation after each finite operator admits its own check.

    Hash the actual check, including its operator. The carrier names are retained
    for wire compatibility; this helper never converts one policy into another.
    """
    assistant_source = AuthoredOutputSource.model_validate(
        assistant_source.model_dump(mode="python", warnings=False)
    )
    external_source = ExternalOutputSource.model_validate(
        external_source.model_dump(mode="python", warnings=False)
    )
    validate_authored_outputs(assistant, source, assistant_source)
    validate_external_outputs(external, source, external_source, native_source=native_source)
    assistant = AuthoredOutputEvidence.model_validate(
        assistant.model_dump(mode="python", warnings=False)
    )
    external = ExternalOutputEvidence.model_validate(
        external.model_dump(mode="python", warnings=False)
    )
    policy = _policy(source, check)
    inventory = capture_invocation_inventory(source, native_source=native_source)
    outputs = []
    for namespace, records in (
        ("assistant", assistant.records),
        ("external", external.text_records),
    ):
        for fact in records:
            raw = fact.model_dump(mode="json")
            # JSON tuple encoding avoids delimiter ambiguity in opaque source IDs.
            key = canonical_json([namespace, fact.output_id])
            outputs.append(
                SummaryOutput(
                    output_key=key,
                    inventory=cast(Literal["assistant", "external"], namespace),
                    output_id=fact.output_id,
                    output_digest=_digest([namespace, raw]),
                    text=fact.text,
                    channel=raw.get("channel"),
                    surface="assistant_text" if namespace == "assistant" else raw["surface"],
                    fact_json=canonical_json(raw),
                )
            )
    if len({output.output_key for output in outputs}) != len(outputs):
        raise ValueError("summary_output_identity_ambiguous")
    relations = tuple(
        SummaryRelation(relation_id=_digest(relation.model_dump(mode="json")), relation=relation)
        for relation in external.action_relations
    )
    if len({relation.relation_id for relation in relations}) != len(relations):
        raise ValueError("summary_action_relation_identity_ambiguous")
    payload = {
        "source_digest": _digest(source),
        "check_digest": _digest(check.model_dump(mode="json")),
        "policy_path": check.policy_path,
        "policy_digest": check.policy_digest,
        "policy_text": policy,
        "outputs": tuple(outputs),
        "relations": relations,
        "invocations": inventory.entries,
        "assistant_closed": assistant.closed,
        "external_closed": external.closed,
        "invocation_closed": inventory.closed,
        "coverage_reasons": tuple(
            reason
            for closed, reason in (
                (assistant.closed, assistant.reason),
                (external.closed, external.reason),
                (inventory.closed, inventory.reason),
            )
            if not closed
        ),
    }
    encoded = {
        key: [item.model_dump(mode="json") for item in value]
        if key in {"outputs", "relations", "invocations"}
        else value
        for key, value in payload.items()
    }
    return SummaryPolicyContext(**payload, context_digest=_digest(encoded))


def _admit_decision(decision, output, context, declared, producer, full_output_ids):
    if (
        declared is None
        or producer is None
        or canonical_json(producer.model_dump(mode="json"))
        != canonical_json(declared.model_dump(mode="json"))
    ):
        raise ValueError("summary_semantic_producer_unavailable_or_changed")
    if output.output_key not in full_output_ids:
        raise ValueError("summary_full_output_driver_coverage_unavailable")
    if (
        decision.assessor_id != declared.assessor_id
        or decision.assessor_revision != declared.revision
        or decision.context_digest != context.context_digest
        or decision.output_digest != output.output_digest
    ):
        raise ValueError("summary_decision_source_output_or_producer_changed")
    if decision.state != "abstained" and not decision.citations:
        raise ValueError("summary_decision_requires_output_citation")
    for citation in decision.citations:
        if (
            citation.end > len(output.text)
            or output.text[citation.start : citation.end] != citation.quote
        ):
            raise ValueError("summary_decision_output_citation_mismatch")
    if len(set(decision.relation_ids)) != len(decision.relation_ids) or len(
        set(decision.invocation_ids)
    ) != len(decision.invocation_ids):
        raise ValueError("summary_decision_duplicate_context_citation")
    if not set(decision.relation_ids) <= {relation.relation_id for relation in context.relations}:
        raise ValueError("summary_decision_action_relation_unavailable")
    qualified = {
        entry.invocation_id for entry in context.invocations if entry.status == "qualified"
    }
    if not set(decision.invocation_ids) <= qualified:
        raise ValueError("summary_decision_invocation_unavailable")


def _decision_collection(value, label):
    """Bound optional producer streams and retain yielded evidence on failure.

    A malformed container is not an empty, successfully observed inventory.
    Ordinary iterator failures are optional-assessor scope errors; cancellation
    and other BaseExceptions retain their normal caller lifecycle semantics.
    """
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        return (), f"summary_{label}_collection_invalid"
    collected = []
    try:
        iterator = iter(value)
        # This is an admission bound, not truncation presented as complete.
        for _ in range(65536):
            try:
                collected.append(next(iterator))
            except StopIteration:
                return tuple(collected), None
        try:
            next(iterator)
        except StopIteration:
            return tuple(collected), None
        return tuple(collected), f"summary_{label}_collection_limit_exceeded"
    except Exception as error:  # noqa: BLE001 - optional producer iteration becomes explicit unknown scope.
        return tuple(
            collected
        ), f"summary_{label}_collection_iteration_failed:{type(error).__name__}"


def evaluate_summary_policy(
    source: Mapping,
    check: SummaryExclusionCheck,
    assistant: AuthoredOutputEvidence,
    external: ExternalOutputEvidence,
    *,
    assistant_source: AuthoredOutputSource,
    external_source: ExternalOutputSource,
    native_source: SourceSnapshot | None = None,
    decisions: Iterable[SummaryDecision] = (),
    producer: SummaryAssessor | None = None,
    full_output_ids: Iterable[str] = (),
) -> SummaryEvaluation:
    """Conservative reduction; never invoke a model or manufacture a summary.

    ``producer`` is supplied by the trusted local driver after its declared
    execution, never copied out of model output. ``full_output_ids`` contains
    namespaced output keys whose whole text the driver presented for assessment;
    it is a driver receipt, not a model assertion of coverage. Citation validity does not make
    semantic labels deterministic truth. Violation is existential; compliance
    requires closed inventories and complete per-output semantic decisions.
    """
    return _evaluate_output_policy(
        source,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=native_source,
        decisions=decisions,
        producer=producer,
        full_output_ids=full_output_ids,
        prepare_context=prepare_summary_context,
    )


def _evaluate_output_policy(
    source: Mapping,
    check: Any,
    assistant: AuthoredOutputEvidence,
    external: ExternalOutputEvidence,
    *,
    assistant_source: AuthoredOutputSource,
    external_source: ExternalOutputSource,
    native_source: SourceSnapshot | None = None,
    decisions: Iterable[SummaryDecision] = (),
    producer: SummaryAssessor | None = None,
    full_output_ids: Iterable[str] = (),
    prepare_context: Callable[..., SummaryPolicyContext],
    reason_prefix: str = "summary",
    violation_reason: str = "summary_exclusion_violation_cited",
    inapplicable_reason: str = "summary_no_output_is_work_summary",
    prepare_admission: Callable[[SummaryPolicyContext], Callable[..., None]] | None = None,
) -> SummaryEvaluation:
    """Closed-world decision reduction shared by the two finite policy operators.

    Each public wrapper owns strict check admission and policy identity. This
    private preparation function argument is not a manifest callback or DSL.
    """
    base: dict[str, Any] = {
        "source_digest": _digest(source),
        "check_id": check.check_id,
        "signal_id": check.signal_id,
    }
    try:
        context = prepare_context(
            source,
            check,
            assistant,
            external,
            assistant_source=assistant_source,
            external_source=external_source,
            native_source=native_source,
        )
        # Freeze policy-specific factual prerequisites before any optional
        # producer/coverage iterator can execute caller code or mutate source.
        admit_decision = prepare_admission(context) if prepare_admission else _admit_decision
        if producer is not None:
            producer = SummaryAssessor.model_validate(
                producer.model_dump(mode="python", warnings=False)
            )
    except (ValueError, TypeError, AttributeError, KeyError) as error:
        return SummaryEvaluation(**base, status="abstained", compliance=None, reason=str(error))
    outputs = {output.output_key: output for output in context.outputs}
    admitted, errors, invalid_targets = [], [], set()
    decisions, decision_collection_error = _decision_collection(decisions, "decisions")
    full_output_ids, coverage_collection_error = _decision_collection(
        full_output_ids, "driver_coverage"
    )
    errors.extend(
        error
        for error in (decision_collection_error, coverage_collection_error)
        if error is not None
    )
    if any(type(key) is not str or key not in outputs for key in full_output_ids) or len(
        set(full_output_ids)
    ) != len(full_output_ids):
        errors.append("summary_driver_output_coverage_invalid")
        full_output_ids = ()
    for candidate in decisions:
        try:
            decision = SummaryDecision.model_validate(
                candidate.model_dump(mode="python", warnings=False)
                if isinstance(candidate, SummaryDecision)
                else candidate
            )
            output = outputs.get(decision.output_key)
            if output is None:
                raise ValueError("summary_decision_output_unknown")
            admit_decision(decision, output, context, check.assessor, producer, full_output_ids)
            admitted.append(decision)
        except (ValueError, TypeError, AttributeError, KeyError) as error:
            errors.append(str(error))
            key = (
                candidate.get("output_key")
                if isinstance(candidate, Mapping)
                else getattr(candidate, "output_key", None)
            )
            if type(key) is str and key in outputs:
                invalid_targets.add(key)
    counts = Counter(decision.output_key for decision in admitted)
    duplicate = {key for key, count in counts.items() if count != 1}
    if duplicate:
        errors.append("summary_decision_output_duplicate")
    selected = {decision.output_key: decision for decision in admitted}
    findings = []
    for output in context.outputs:
        decision = selected.get(output.output_key)
        finding_basis = "undecided"
        if output.output_key in invalid_targets or output.output_key in duplicate:
            state, reason, decision = (
                "abstained",
                "summary_output_decision_invalid_or_conflicting",
                None,
            )
        elif output.text == "" and decision is None:
            state, reason = "inapplicable", "summary_observed_empty_text"
            finding_basis = "empty_text"
        elif decision is None:
            state, reason = "abstained", "summary_output_semantics_undecided"
        else:
            state, reason = decision.state, decision.reason
            finding_basis = "semantic"
        findings.append(
            SummaryFinding(
                output_key=output.output_key,
                output_id=output.output_id,
                output_digest=output.output_digest,
                state=state,
                reason=reason,
                decision=decision,
                basis=finding_basis,
            )
        )
    closed = context.assistant_closed and context.external_closed and context.invocation_closed
    if any(finding.state == "violation" for finding in findings):
        status, value, reason, basis = (
            "violation",
            0.0,
            violation_reason,
            "semantic",
        )
    elif errors or not closed or any(finding.state == "abstained" for finding in findings):
        status, value, reason, basis = (
            "abstained",
            None,
            f"{reason_prefix}_scope_or_semantics_unresolved",
            "undecided",
        )
    elif not findings:
        status, value, reason, basis = (
            "compliant",
            1.0,
            f"{reason_prefix}_closed_empty_output_inventory",
            "empty_inventory",
        )
    elif all(finding.state == "inapplicable" for finding in findings):
        status, value, reason, basis = (
            "inapplicable",
            1.0,
            inapplicable_reason,
            "empty_text"
            if all(finding.basis == "empty_text" for finding in findings)
            else "semantic",
        )
    else:
        status, value, reason, basis = (
            "compliant",
            1.0,
            f"{reason_prefix}_all_outputs_decided_no_violation",
            "semantic",
        )
    return SummaryEvaluation(
        **base,
        status=status,
        compliance=value,
        reason=reason,
        context=context,
        findings=tuple(findings),
        decision_errors=tuple(errors),
        producer=producer,
        full_output_ids=tuple(full_output_ids),
        basis=basis,
    )
