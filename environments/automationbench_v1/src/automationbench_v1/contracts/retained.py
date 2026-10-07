"""Terminal Sheets outcomes, independent of occurrence evidence and action credit."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, StrictInt, field_validator, model_validator

from ..capture import canonical_json
from .base import FrozenModel, Identifier
from .guards import LookupSpec
from .obligations import _context, _fields
from .predicates import Predicate, evaluate_predicate, parse_predicate
from .sheet_effects import SheetEffectSource, SheetRetentionEvidence, validate_sheet_retention
from .tables import TableEvidence, TableSource, capture_table


class RetainedRowCheck(FrozenModel):
    check_id: Identifier
    signal_id: Identifier
    role: Literal["goal"]
    operator: Literal["sheets.retained_when@1"]
    population: Identifier
    source: Identifier
    lookups: tuple[LookupSpec, ...] = ()
    required_when: Predicate
    supported_when: Predicate | None = Field(default=None, exclude_if=lambda value: value is None)
    retained_when: Predicate
    max_instances: StrictInt = Field(default=4096, ge=1, le=65536)

    @field_validator("required_when", "supported_when", "retained_when", mode="before")
    @classmethod
    def predicates(cls, value):
        return parse_predicate(value) if value is not None else None

    @model_validator(mode="after")
    def contexts(self):
        aliases = [lookup.alias for lookup in self.lookups]
        reserved = {"request", "candidate", "retained", "effect"}
        if len(set(aliases)) != len(aliases) or set(aliases) & reserved:
            raise ValueError("retained_lookup_alias_conflict")
        available = {"request", "candidate"}
        for lookup in self.lookups:
            if any(len(value.path) < 2 or value.path[0] not in available
                   for value in lookup.keys.values()):
                raise ValueError("retained_lookup_context_unavailable")
            available.add(lookup.alias)
        for name in ("required_when", "supported_when", "retained_when"):
            predicate = getattr(self, name)
            if predicate is None:
                continue
            roots = available | ({"retained"} if name == "retained_when" else set())
            if any(len(path) < 2 or path[0] not in roots
                   for path in _fields(predicate.model_dump(mode="python"))):
                raise ValueError("retained_predicate_context_unknown")
        return self


@dataclass(frozen=True)
class RetainedCase:
    instance_key: str
    candidate_identity: tuple


@dataclass(frozen=True)
class RetainedFinding:
    check_id: str
    instance_key: str
    signal_id: str
    candidate_identity: tuple
    native_record_id: str | None
    status: Literal["valid", "inapplicable", "abstained"]
    value: float | None
    reason: str
    required: bool | None
    evidence_paths: tuple


@dataclass(frozen=True)
class RetainedEvaluation:
    source_digest: str
    check_digest: str
    findings: tuple[RetainedFinding, ...]
    scope_complete: bool
    reason: str


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def plan_retained_instances(check: RetainedRowCheck, population: TableEvidence):
    count = len(population.rows)
    if count > check.max_instances:
        return (), count
    return tuple(RetainedCase(_digest([check.check_id, population.selector_digest, identity]), identity)
                 for identity in dict.fromkeys(row.identity for row in population.rows)), count


def evaluate_retained_rows(
    source: Mapping, check: RetainedRowCheck, populations: Mapping[str, TableEvidence],
    retention: SheetRetentionEvidence, *, retention_source: SheetEffectSource,
    population_sources: Mapping[str, TableSource],
) -> RetainedEvaluation:
    """Authenticate projections, then test original objects in the finalized state.

    Closed absence is failure. Unknown identity or unfinished capture abstains.
    Row position is never substituted for object identity. No action is inferred.
    """
    check = RetainedRowCheck.model_validate(check.model_dump(mode="python"))
    required = {check.population, *(lookup.source for lookup in check.lookups)}
    if set(populations) != required or set(population_sources) != required:
        raise ValueError("retained_population_inventory_mismatch")
    for name, population in populations.items():
        spec = population_sources[name]
        if spec.path[:2] != ("task_evidence", "initial"):
            raise ValueError("retained_requires_initial_population")
        actual = capture_table(source, spec)
        if canonical_json(population.model_dump(mode="python")) != canonical_json(actual.model_dump(mode="python")):
            raise ValueError("retained_population_source_or_projection_mismatch")
    population = populations[check.population]
    if (population.source.spreadsheet_id, population.source.worksheet_id) != (
            retention_source.spreadsheet_id, retention_source.worksheet_id):
        raise ValueError("retained_population_scope_mismatch")
    for lookup in check.lookups:
        if set(lookup.keys) != set(population_sources[lookup.source].key_fields):
            raise ValueError("retained_lookup_key_inventory_mismatch")
    validate_sheet_retention(retention, source, retention_source)
    cases, count = plan_retained_instances(check, population)
    source_id, check_id = _digest(source), _digest(check.model_dump(mode="json"))
    if count > check.max_instances:
        return RetainedEvaluation(source_id, check_id, (), False, "retained_instance_budget_exceeded")
    findings = []
    for case in cases:
        rows = [row for row in population.rows if row.identity == case.candidate_identity]
        row = rows[0]
        status, value, reason, needed = "abstained", None, "retained_initial_population_unavailable", None
        paths = (row.source_path,)
        if population.status != "unavailable" and len(rows) == 1:
            context = _context(check, row, populations)
            applicability = evaluate_predicate(check.required_when, context)
            needed = applicability.value
            paths += applicability.evidence_paths
            support = (evaluate_predicate(check.supported_when, context)
                       if needed is True and check.supported_when is not None else None)
            if support is not None:
                paths += support.evidence_paths
            if needed is False:
                status, reason = "inapplicable", "retained_not_required"
            elif needed is None:
                reason = "retained_requirement_unavailable"
            elif support is not None and support.value is False:
                reason = "retained_calculation_domain_unsupported"
            elif support is not None and support.value is None:
                reason = "retained_calculation_domain_unavailable"
            elif not retention.closed:
                reason = "retained_terminal_unavailable"
            elif row.native_record_id is None:
                reason = "retained_original_identity_unavailable"
            else:
                matches = [final for final in retention.rows if final.native_record_id == row.native_record_id]
                if not matches:
                    status, value, reason = "valid", 0.0, "retained_original_record_absent"
                elif len(matches) != 1:
                    reason = "retained_original_identity_ambiguous"
                else:
                    context["retained"] = json.loads(matches[0].cells_json)
                    result = evaluate_predicate(check.retained_when, context)
                    paths += result.evidence_paths
                    if result.value is None:
                        reason = "retained_predicate_unavailable"
                    else:
                        status, value, reason = "valid", float(result.value), "retained_predicate_verified"
        findings.append(RetainedFinding(check.check_id, case.instance_key, check.signal_id,
            case.candidate_identity, row.native_record_id, status, value, reason, needed, paths))
    closed = (population.closed and retention.closed and
              all(finding.status != "abstained" for finding in findings))
    return RetainedEvaluation(source_id, check_id, tuple(findings), closed,
        "retained_scope_complete" if closed else "retained_scope_unavailable")
