"""Closed filtered COUNT/SUM evidence over one declared initial population.

This module neither checks report completion nor assigns action credit. Units are
manifest declarations, not inferred currencies or conversion instructions. SUM
uses existing exact scalar semantics: an unrounded nonterminating member value
is unavailable even if several such fractions could cancel after aggregation.
Sheets identities are declared scoped typed row IDs at this initial snapshot;
they are not array positions or proof of identity continuity after mutations.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict
from fractions import Fraction
from typing import Any, Literal, cast

from pydantic import (
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_validator,
    model_validator,
)

from ..capture import canonical_json
from .base import FrozenModel, Identifier
from .populations import InitialCollectionSource, _model, capture_population
from .predicates import Predicate, evaluate_predicate, parse_predicate
from .predicates import context_paths as _fields
from .tables import Digest, TableEvidence, TableSource, capture_table
from .values import (
    ValueExpression,
    _bounded,
    _canonical_decimal,
    _Unavailable,
    evaluate_value,
    parse_value,
)

type AggregatePopulationSource = TableSource | InitialCollectionSource
type Path = tuple[StrictStr | StrictInt, ...]
type MemberIdentity = tuple[StrictStr, StrictStr, StrictStr, StrictStr | StrictInt]


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class AggregateSpec(FrozenModel):
    operator: Literal["population.aggregate@1"] = "population.aggregate@1"
    population: Identifier
    reduction: Literal["count", "sum"]
    where: Predicate
    value: ValueExpression | None = None
    unit: Identifier
    max_members: StrictInt = Field(default=4096, ge=1, le=65536)

    @field_validator("where", mode="before")
    @classmethod
    def predicate(cls, value):
        return parse_predicate(value)

    @field_validator("value", mode="before")
    @classmethod
    def expression(cls, value):
        return None if value is None else parse_value(value)

    @model_validator(mode="after")
    def bounded_context(self):
        if (self.reduction == "sum") != (self.value is not None):
            raise ValueError("aggregate_sum_requires_value_count_forbids_value")
        if self.reduction == "count" and self.unit != "members":
            raise ValueError("aggregate_count_unit_must_be_members")
        for path in _fields(self.model_dump(mode="python")):
            if len(path) < 2 or path[0] not in {"request", "candidate"}:
                raise ValueError("aggregate_context_path_unsupported")
            if path[0] == "candidate" and path != ("candidate", "native_record_id"):
                raise ValueError("aggregate_candidate_metadata_unsupported")
        return self


class AggregateMember(FrozenModel):
    identity: MemberIdentity
    native_record_id: Identifier | None
    source_path: Path
    cells_json: StrictStr
    selected: StrictBool | None
    reason: StrictStr
    eligibility_paths: tuple[Path, ...]
    value_evidence_json: StrictStr | None = None


class AggregateEvidence(FrozenModel):
    source_digest: Digest
    selector_digest: Digest
    spec_digest: Digest
    population: Identifier
    reduction: Literal["count", "sum"]
    unit: Identifier
    status: Literal["qualified", "unavailable"]
    reason: StrictStr
    membership_closed: StrictBool
    enumerated: StrictBool
    selected_count: StrictInt | None
    canonical_value: StrictStr | None
    members: tuple[AggregateMember, ...]

    @model_validator(mode="after")
    def result_shape(self):
        if self.status == "qualified":
            if (
                not self.membership_closed
                or not self.enumerated
                or self.selected_count is None
                or self.selected_count < 0
                or self.canonical_value is None
                or any(member.selected is None for member in self.members)
                or self.selected_count != sum(member.selected is True for member in self.members)
            ):
                raise ValueError("aggregate_qualified_result_inconsistent")
        elif self.selected_count is not None or self.canonical_value is not None:
            raise ValueError("aggregate_unavailable_has_no_total")
        return self


def _admit(spec: AggregateSpec, selector: AggregatePopulationSource):
    if type(spec) is not AggregateSpec:
        raise TypeError("aggregate_spec_required")
    spec = AggregateSpec.model_validate(spec.model_dump(mode="python", warnings=False))
    if type(selector) not in {TableSource, InitialCollectionSource}:
        raise TypeError("aggregate_installed_population_source_required")
    selector = type(selector).model_validate(selector.model_dump(mode="python", warnings=False))
    if selector.path[:2] != ("task_evidence", "initial"):
        raise ValueError("aggregate_initial_population_required")
    if isinstance(selector, InitialCollectionSource):
        paths = _fields(spec.model_dump(mode="python"))
        if any(path[0] == "request" and path[1] not in selector.fields for path in paths):
            raise ValueError("aggregate_field_not_projected")
    return spec, selector


def _context(row, selector: AggregatePopulationSource):
    # Imported here: obligations declares aggregate aliases, and retained
    # records depend on obligations.
    from .retained_records import _finite, _leaf, _literal_types

    cells = json.loads(row.cells_json)
    if isinstance(selector, InitialCollectionSource):
        model = _model(cast(str, selector.path[2]), cast(str, selector.path[3]))
        # Initial collection receipts preserve raw leaves. Validate their
        # installed types privately; never normalize or hydrate their values.
        for alias, path in selector.fields.items():
            if alias not in cells:
                continue
            annotation = _leaf(model, path)
            try:
                if not _literal_types(cells[alias], annotation):
                    raise ValueError("aggregate_native_leaf_type_unavailable")
                value = TypeAdapter(annotation).validate_json(
                    canonical_json(cells[alias]), strict=True
                )
                if not _finite(value):
                    raise ValueError("aggregate_native_leaf_nonfinite")
            except ValueError:
                del cells[alias]
        native_id = row.identity[-1]
    else:
        native_id = row.native_record_id
    return {"request": cells, "candidate": {"native_record_id": native_id}}, native_id


def evaluate_aggregate(
    source: Mapping,
    spec: AggregateSpec,
    *,
    population_source: AggregatePopulationSource,
) -> AggregateEvidence:
    """Recapture raw authority; there is no caller-supplied closure/result flag."""
    spec, selector = _admit(spec, population_source)
    population = (
        capture_table(source, selector)
        if isinstance(selector, TableSource)
        else capture_population(source, selector)
    )
    reasons: list[str] = []
    if not population.closed or not population.enumerated:
        reasons.append(population.reason)
    if len(population.rows) > spec.max_members:
        reasons.append("aggregate_member_budget_exceeded")
    identities = [canonical_json(row.identity) for row in population.rows]
    native_ids = (
        [row.native_record_id for row in population.rows if row.native_record_id is not None]
        if isinstance(population, TableEvidence)
        else []
    )
    if len(set(identities)) != len(identities) or len(set(native_ids)) != len(native_ids):
        reasons.append("aggregate_duplicate_member_identity")
    members: list[AggregateMember] = []
    total = Fraction(0)
    selected = 0
    # A bounded refusal never emits a computed partial total.
    rows = population.rows if len(population.rows) <= spec.max_members else ()
    for row in rows:
        context, native_id = _context(row, selector)
        eligibility = evaluate_predicate(spec.where, context)
        value_json = None
        reason = eligibility.reason
        if eligibility.value is None:
            reasons.append("aggregate_eligibility_unavailable")
        elif eligibility.value:
            selected += 1
            if spec.value is not None:
                value = evaluate_value(spec.value, context)
                value_json = canonical_json(asdict(value))
                reason = value.reason
                if (
                    value.status != "qualified"
                    or value.kind != "decimal"
                    or type(value.canonical_value) is not str
                ):
                    reasons.append("aggregate_selected_value_unavailable")
                else:
                    try:
                        total = _bounded(total + Fraction(value.canonical_value))
                    except _Unavailable:
                        reasons.append("aggregate_numeric_budget_exceeded")
        members.append(
            AggregateMember(
                identity=row.identity,
                native_record_id=native_id,
                source_path=row.source_path,
                cells_json=row.cells_json,
                selected=eligibility.value,
                reason=reason,
                eligibility_paths=eligibility.evidence_paths,
                value_evidence_json=value_json,
            )
        )
    canonical = None
    if not reasons:
        try:
            canonical = str(selected) if spec.reduction == "count" else _canonical_decimal(total)
        except _Unavailable as error:
            reasons.append(str(error))
    return AggregateEvidence(
        source_digest=_digest(source),
        selector_digest=population.selector_digest,
        spec_digest=_digest(spec.model_dump(mode="json")),
        population=spec.population,
        reduction=spec.reduction,
        unit=spec.unit,
        status="unavailable" if reasons else "qualified",
        reason=reasons[0] if reasons else "aggregate_closed_exact_reduction",
        membership_closed=population.closed,
        enumerated=population.enumerated,
        selected_count=None if reasons else selected,
        canonical_value=canonical,
        members=tuple(members),
    )


def validate_aggregate_evidence(
    evidence: AggregateEvidence,
    source: Mapping,
    spec: AggregateSpec,
    *,
    population_source: AggregatePopulationSource,
) -> None:
    """A typed receipt or digest alone is never an authentication certificate."""
    admitted = AggregateEvidence.model_validate(evidence.model_dump(mode="python", warnings=False))
    actual = evaluate_aggregate(source, spec, population_source=population_source)
    if canonical_json(admitted.model_dump(mode="json")) != canonical_json(
        actual.model_dump(mode="json")
    ):
        raise ValueError("aggregate_source_selector_spec_or_result_mismatch")
