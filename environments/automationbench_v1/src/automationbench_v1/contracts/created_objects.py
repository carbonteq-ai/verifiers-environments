"""Fresh persisted objects satisfy authored requests; action credit is separate."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, StrictInt, field_validator, model_validator

from ..capture import canonical_json
from .base import FrozenModel, Identifier
from .created_records import (
    CreatedRecordEvidence,
    CreatedRecordSource,
    capture_created_records,
    validate_created_records,
)
from .hubspot_objects import (
    HubSpotEvidence,
    HubSpotObjectSource,
    capture_hubspot_evidence,
    validate_hubspot_evidence,
)
from .jira_effects import (
    JiraEvidence,
    JiraIssueSource,
    capture_jira_evidence,
    validate_jira_evidence,
)
from .obligations import _fields
from .predicates import Predicate, evaluate_predicate, parse_predicate
from .requests import RequestPopulationEvidence, RequestSource, validate_request_population


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


CreatedObjectSource = JiraIssueSource | HubSpotObjectSource | CreatedRecordSource
CreatedObjectEvidence = JiraEvidence | HubSpotEvidence | CreatedRecordEvidence


def capture_created_evidence(source, spec: CreatedObjectSource) -> CreatedObjectEvidence:
    if isinstance(spec, JiraIssueSource):
        return capture_jira_evidence(source, spec)
    if isinstance(spec, HubSpotObjectSource):
        return capture_hubspot_evidence(source, spec)
    if isinstance(spec, CreatedRecordSource):
        return capture_created_records(source, spec)
    raise TypeError("created_object_source_unsupported")


def restore_created_evidence(value, spec: CreatedObjectSource) -> CreatedObjectEvidence:
    if isinstance(spec, JiraIssueSource):
        return JiraEvidence.model_validate(value)
    if isinstance(spec, HubSpotObjectSource):
        return HubSpotEvidence.model_validate(value)
    if isinstance(spec, CreatedRecordSource):
        return CreatedRecordEvidence.model_validate(value)
    raise TypeError("created_object_source_unsupported")


def created_object_count(evidence: CreatedObjectEvidence) -> int:
    if isinstance(evidence, JiraEvidence):
        return len(evidence.final.all_issue_ids)
    return len(evidence.final.all_object_ids)


@dataclass(frozen=True)
class _CompletionTransition:
    object_id: str | None
    invocation_id: str
    receipt_id: str | None
    kind: str
    status: str
    before_json: str | None
    after_json: str | None
    expected_revision: int | None
    applied_revision: int | None
    requested_fields: tuple[str, ...]
    changed_fields: tuple[str, ...]


def _predicate_object(value: str | None, evidence: CreatedObjectEvidence) -> str | None:
    """One private predicate view; adapter facts keep their native wire shape."""
    if value is None or isinstance(evidence, JiraEvidence):
        return value
    native = json.loads(value)
    return canonical_json({"id": native["id"], "fields": native})


def _objects(evidence: CreatedObjectEvidence):
    if isinstance(evidence, JiraEvidence):
        return tuple((item.issue_id, item.issue_json) for item in evidence.final.issues)
    if isinstance(evidence, CreatedRecordEvidence):
        return tuple((item.object_id, item.object_json) for item in evidence.final.objects)
    return tuple(
        (
            item.object_id,
            canonical_json({"id": item.object_id, "fields": json.loads(item.object_json)}),
        )
        for item in evidence.final.objects
    )


def _transitions(evidence: CreatedObjectEvidence) -> tuple[_CompletionTransition, ...]:
    if isinstance(evidence, CreatedRecordEvidence):
        # Outcome-only adapter: no qualified creation transitions or receipts.
        raise TypeError("created_completion_source_unsupported")
    if isinstance(evidence, JiraEvidence):
        return tuple(
            _CompletionTransition(
                item.issue_id,
                item.invocation_id,
                item.audit_id,
                item.kind,
                item.status,
                item.before_issue_json,
                item.after_issue_json,
                item.expected_revision,
                item.applied_revision,
                item.requested_fields,
                item.changed_fields,
            )
            for item in evidence.transitions
        )
    return tuple(
        _CompletionTransition(
            item.object_id,
            item.invocation_id,
            item.receipt_id,
            item.kind,
            item.status,
            _predicate_object(item.before_object_json, evidence),
            _predicate_object(item.after_object_json, evidence),
            item.expected_revision,
            item.applied_revision,
            item.requested_fields,
            item.changed_fields,
        )
        for item in evidence.transitions
    )


class CreatedRetainedCheck(FrozenModel):
    check_id: Identifier
    signal_id: Identifier
    role: Literal["goal"]
    operator: Literal["objects.created_and_retained@1"] = "objects.created_and_retained@1"
    population: Identifier
    source: Identifier
    required_when: Predicate
    retained_when: Predicate
    max_instances: StrictInt = Field(default=4096, ge=1, le=65536)

    @field_validator("required_when", "retained_when", mode="before")
    @classmethod
    def predicates(cls, value):
        return parse_predicate(value)

    @model_validator(mode="after")
    def contexts(self):
        for name in ("required_when", "retained_when"):
            roots = {"request", "candidate"} | ({"retained"} if name == "retained_when" else set())
            if any(
                len(path) < 2 or path[0] not in roots
                for path in _fields(getattr(self, name).model_dump(mode="python"))
            ):
                raise ValueError("created_predicate_context_unknown")
        return self


@dataclass(frozen=True)
class CreatedFinding:
    check_id: str
    instance_key: str
    signal_id: str
    candidate_identity: tuple
    status: Literal["valid", "inapplicable", "abstained"]
    value: float | None
    reason: str
    required: bool | None
    native_record_ids: tuple[str, ...] = ()
    evidence_paths: tuple = ()


@dataclass(frozen=True)
class CreatedEvaluation:
    source_digest: str
    check_digest: str
    findings: tuple[CreatedFinding, ...]
    scope_complete: bool
    reason: str


@dataclass(frozen=True)
class CreatedSelection:
    check_id: str
    instance_key: str
    native_record_id: str
    occurrence: str
    effect_id: str
    expected_revision: int
    applied_revision: int
    value: float = 1.0


@dataclass(frozen=True)
class CreatedCompletionFinding:
    instance_key: str
    candidate_identity: tuple
    status: Literal["eligible", "unavailable", "ineligible"]
    reason: str
    selection: CreatedSelection | None = None


@dataclass(frozen=True)
class CreatedCompletionEvaluation:
    source_digest: str
    check_digest: str
    selection_digest: str
    outcome: CreatedEvaluation
    findings: tuple[CreatedCompletionFinding, ...]
    action_scope_complete: bool
    reason: str


def _context(row):
    return {"request": json.loads(row.cells_json), "candidate": {"identity": list(row.identity)}}


def _fresh(object_id, evidence: CreatedObjectEvidence):
    ids = (
        evidence.initial.all_issue_ids
        if isinstance(evidence, JiraEvidence)
        else evidence.initial.all_object_ids
    )
    if object_id in ids:
        return False
    if evidence.initial.identities_complete:
        return True
    return None


def _admit(source, check, population, evidence, population_source, object_source, bindings):
    check = CreatedRetainedCheck.model_validate(check.model_dump(mode="python", warnings=False))
    population_source = RequestSource.model_validate(
        population_source.model_dump(mode="python", warnings=False)
    )
    if isinstance(object_source, JiraIssueSource):
        object_source = JiraIssueSource.model_validate(
            object_source.model_dump(mode="python", warnings=False)
        )
        validate_jira_evidence(evidence, source, object_source)
    elif isinstance(object_source, HubSpotObjectSource):
        object_source = HubSpotObjectSource.model_validate(
            object_source.model_dump(mode="python", warnings=False)
        )
        validate_hubspot_evidence(evidence, source, object_source)
    elif isinstance(object_source, CreatedRecordSource) and isinstance(
        evidence, CreatedRecordEvidence
    ):
        object_source = CreatedRecordSource.model_validate(
            object_source.model_dump(mode="python", warnings=False)
        )
        validate_created_records(evidence, source, object_source)
    else:
        raise TypeError("created_object_source_unsupported")
    validate_request_population(population, source, bindings)
    if canonical_json(population.source.model_dump(mode="json")) != canonical_json(
        population_source.model_dump(mode="json")
    ):
        raise ValueError("created_population_selector_mismatch")
    return check


def evaluate_created_retained(
    source: Mapping,
    check: CreatedRetainedCheck,
    population: RequestPopulationEvidence,
    evidence: CreatedObjectEvidence,
    *,
    population_source: RequestSource,
    object_source: CreatedObjectSource,
    bindings: Sequence,
) -> CreatedEvaluation:
    """Existence of one fresh, matching, retained object is sufficient.

    Missing capture can block absence while leaving an independent positive
    proof intact. Neither action history nor an old matching object is a goal.
    """
    check = _admit(source, check, population, evidence, population_source, object_source, bindings)
    source_id, check_id = _digest(source), _digest(check.model_dump(mode="json"))
    row = population.rows[0]
    instance = _digest([check.check_id, population.selector_digest, row.identity])
    status: Literal["valid", "inapplicable", "abstained"] = "abstained"
    value, reason, required, matches, paths = (
        None,
        "created_request_authority_unavailable",
        None,
        [],
        [],
    )
    count = created_object_count(evidence)
    if population.status == "qualified":
        context = _context(row)
        requirement = evaluate_predicate(check.required_when, context)
        paths.extend(requirement.evidence_paths)
        required = requirement.value
        if required is False:
            status, reason = "inapplicable", "created_not_required"
        elif required is None:
            reason = "created_requirement_unavailable"
        elif source.get("task_evidence", {}).get("complete") is not True:
            reason = "created_terminal_finalization_unavailable"
        elif count > check.max_instances:
            reason = "created_instance_budget_exceeded"
        else:
            unknown = not evidence.final.closed
            for object_id, object_json in _objects(evidence):
                result = evaluate_predicate(
                    check.retained_when, context | {"retained": json.loads(object_json)}
                )
                paths.extend(result.evidence_paths)
                fresh = _fresh(object_id, evidence)
                if result.value is True and fresh is True:
                    matches.append(object_id)
                elif result.value is not False and fresh is not False:
                    unknown = True
            if matches:
                status, value, reason = "valid", 1.0, "created_matching_fresh_object_retained"
            elif unknown:
                reason = "created_retained_membership_or_fields_unavailable"
            else:
                status, value, reason = "valid", 0.0, "created_matching_fresh_object_absent"
    finding = CreatedFinding(
        check.check_id,
        instance,
        check.signal_id,
        row.identity,
        status,
        value,
        reason,
        required,
        tuple(sorted(matches)),
        tuple(dict.fromkeys(paths)),
    )
    complete = (
        population.closed
        and evidence.final.closed
        and status != "abstained"
        and source.get("task_evidence", {}).get("complete") is True
    )
    return CreatedEvaluation(
        source_id,
        check_id,
        (finding,),
        complete,
        "created_scope_closed" if complete else "created_scope_unavailable",
    )


def _eligible(transition: _CompletionTransition, check, context, goal_fields):
    if (
        transition.status != "qualified"
        or transition.after_json is None
        or transition.object_id is None
        or transition.receipt_id is None
        or transition.expected_revision is None
        or transition.applied_revision is None
    ):
        return False
    after = evaluate_predicate(
        check.retained_when, context | {"retained": json.loads(transition.after_json)}
    ).value
    if after is not True:
        return False
    if transition.kind == "create":
        return transition.before_json is None
    if (
        transition.kind not in {"status_update", "association_update"}
        or transition.before_json is None
    ):
        return False
    before = evaluate_predicate(
        check.retained_when, context | {"retained": json.loads(transition.before_json)}
    ).value
    return before is False and bool(
        set(goal_fields) & set(transition.requested_fields) & set(transition.changed_fields)
    )


def evaluate_created_completion(
    source: Mapping,
    check: CreatedRetainedCheck,
    population: RequestPopulationEvidence,
    evidence: CreatedObjectEvidence,
    *,
    population_source: RequestSource,
    object_source: CreatedObjectSource,
    bindings: Sequence,
    goal_fields: tuple[str, ...],
    selection: Literal["earliest"] = "earliest",
) -> CreatedCompletionEvaluation:
    """One earliest observed completion, consumed by the native caller per request.

    Final outcome must still be true. A missing/unknown before predicate never
    becomes false; status noops and unrelated fields cannot claim completion.
    """
    check = CreatedRetainedCheck.model_validate(check.model_dump(mode="python", warnings=False))
    if (
        selection != "earliest"
        or type(selection) is not str
        or not goal_fields
        or any(type(field) is not str or not field for field in goal_fields)
        or len(set(goal_fields)) != len(goal_fields)
    ):
        raise ValueError("created_completion_selection_invalid")
    read = {
        path[2]
        for path in _fields(check.retained_when.model_dump(mode="python"))
        if len(path) >= 3 and path[:2] == ("retained", "fields")
    }
    if not set(goal_fields) <= read:
        raise ValueError("created_completion_goal_field_not_read")
    outcome = evaluate_created_retained(
        source,
        check,
        population,
        evidence,
        population_source=population_source,
        object_source=object_source,
        bindings=bindings,
    )
    goal = outcome.findings[0]
    status: Literal["eligible", "unavailable", "ineligible"] = "ineligible"
    reason, chosen = "created_completion_terminal_goal_not_met", None
    if goal.status == "abstained":
        status, reason = "unavailable", "created_completion_terminal_goal_unavailable"
    elif goal.status == "inapplicable":
        reason = "created_completion_not_required"
    elif goal.value == 1:
        context = _context(population.rows[0])
        candidates = [
            item
            for item in _transitions(evidence)
            if item.object_id in goal.native_record_ids
            and _eligible(item, check, context, goal_fields)
        ]
        if not candidates:
            status, reason = "unavailable", "created_completion_qualified_witness_unavailable"
        else:
            earliest = min(item.applied_revision for item in candidates)
            best = [item for item in candidates if item.applied_revision == earliest]
            if len(best) != 1:
                status, reason = "unavailable", "created_completion_revision_order_ambiguous"
            else:
                witness = best[0]
                chosen = CreatedSelection(
                    check.check_id,
                    goal.instance_key,
                    witness.object_id,
                    witness.invocation_id,
                    witness.receipt_id,
                    witness.expected_revision,
                    witness.applied_revision,
                )
                status, reason = "eligible", "created_completion_earliest_qualified_transition"
    finding = CreatedCompletionFinding(
        goal.instance_key, goal.candidate_identity, status, reason, chosen
    )
    return CreatedCompletionEvaluation(
        outcome.source_digest,
        outcome.check_digest,
        _digest({"goal_fields": goal_fields, "selection": selection}),
        outcome,
        (finding,),
        evidence.complete,
        "created_completion_action_scope_closed"
        if evidence.complete
        else "created_completion_action_scope_unavailable",
    )
