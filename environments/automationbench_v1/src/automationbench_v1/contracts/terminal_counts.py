"""Candidate-relative counts over a separate authenticated final collection.

This outcome primitive does not identify a causal action or require a retained
object with the candidate's identity. Initial roster rows may have zero members.
"""

import json
from collections.abc import Mapping
from typing import Literal

from pydantic import Field, StrictInt, field_validator, model_validator

from .base import FrozenModel, Identifier
from .obligations import _context, _fields
from .populations import InitialCollectionSource, capture_population
from .predicates import Predicate, evaluate_predicate, parse_predicate
from .retained import RetainedEvaluation, RetainedFinding
from .retained_records import (
    RetainedCount,
    RetainedRecordSource,
    _digest,
    _typed_context_populations,
    plan_retained_record_instances,
    validate_record_retention,
)
from .sheet_effects import SheetEffectSource, capture_sheet_retention, validate_sheet_retention
from .tables import TableSource, capture_table


class TerminalCountCheck(FrozenModel):
    check_id: Identifier
    signal_id: Identifier
    role: Literal["goal"] = "goal"
    operator: Literal["collections.counts_when@1"] = "collections.counts_when@1"
    population: Identifier
    source: Identifier
    member_fields: tuple[Identifier, ...] = Field(default=(), max_length=64, exclude_if=lambda value: not value)
    counts: tuple[RetainedCount, ...] = Field(min_length=1, max_length=8)
    required_when: Predicate
    counts_when: Predicate
    max_instances: StrictInt = Field(default=4096, ge=1, le=65536)

    @field_validator("required_when", "counts_when", mode="before")
    @classmethod
    def predicates(cls, value):
        return parse_predicate(value)

    @model_validator(mode="after")
    def contexts(self):
        if self.role != "goal" or self.operator != "collections.counts_when@1":
            raise ValueError("terminal_count_outcome_operator_required")
        aliases = [count.alias for count in self.counts]
        if len(set(self.member_fields)) != len(self.member_fields):
            raise ValueError("terminal_count_member_fields_conflict")
        if len(set(aliases)) != len(aliases):
            raise ValueError("terminal_count_alias_conflict")
        for predicate, roots in ((self.required_when, {"request", "candidate"}),
                                 (self.counts_when, {"request", "candidate", "count"}),
                                 *((count.where, {"request", "candidate", "member"}) for count in self.counts)):
            for path in _fields(predicate.model_dump(mode="python")):
                if len(path) < 2 or path[0] not in roots:
                    raise ValueError("terminal_count_context_unknown")
                if path[0] == "count" and (len(path) != 2 or path[1] not in aliases):
                    raise ValueError("terminal_count_alias_unknown")
                if path[0] == "candidate" and (len(path) != 2 or path[1] != "identity"):
                    raise ValueError("terminal_count_candidate_metadata_unknown")
        return self

    @property
    def lookups(self):
        return ()


def admit_terminal_count_projections(check, initial, final):
    from .populations import _field, _model

    if not isinstance(initial, (TableSource, InitialCollectionSource)) or not isinstance(final, (RetainedRecordSource, SheetEffectSource)):
        raise TypeError("terminal_count_typed_sources_required")
    if isinstance(final, SheetEffectSource) and not check.member_fields:
        raise ValueError("terminal_count_sheet_member_fields_required")
    if isinstance(final, RetainedRecordSource) and check.member_fields:
        raise ValueError("terminal_count_record_member_fields_declared_on_source")
    if initial.path[:2] != ("task_evidence", "initial"):
        raise ValueError("terminal_count_initial_population_required")
    if isinstance(initial, TableSource) and initial.path != ("task_evidence", "initial", "google_sheets"):
        raise ValueError("terminal_count_initial_table_path_required")
    for path in _fields(check.model_dump(mode="python")):
        if path[0] in {"count", "candidate"}:
            continue
        selector = initial if path[0] == "request" else final
        if isinstance(selector, SheetEffectSource):
            if len(path) != 2 or path[1] not in check.member_fields:
                raise ValueError("terminal_count_sheet_projection_undeclared")
        elif isinstance(selector, TableSource):
            if len(path) != 2 or path[1] not in (*selector.key_fields, *selector.required_fields):
                raise ValueError("terminal_count_table_projection_undeclared")
        else:
            if path[1] not in selector.fields:
                raise ValueError("terminal_count_projection_undeclared")
            _field(_model(selector.path[2], selector.path[3]), (*selector.fields[path[1]], *path[2:]))


def capture_terminal_count_population(source, selector):
    return capture_table(source, selector) if isinstance(selector, TableSource) else capture_population(source, selector)


def capture_terminal_count_retention(source, selector):
    from .retained_records import capture_record_retention

    return capture_sheet_retention(source, selector) if isinstance(selector, SheetEffectSource) else capture_record_retention(source, selector)


def evaluate_terminal_counts(source: Mapping, check, population, retention, *, population_source, retention_source):
    check = TerminalCountCheck.model_validate(check.model_dump(mode="python"))
    admit_terminal_count_projections(check, population_source, retention_source)
    actual = capture_terminal_count_population(source, population_source)
    if actual.model_dump(mode="json") != population.model_dump(mode="json"):
        raise ValueError("terminal_count_initial_source_or_projection_mismatch")
    sheet = isinstance(retention_source, SheetEffectSource)
    if sheet:
        validate_sheet_retention(retention, source, retention_source)
    else:
        validate_record_retention(retention, source, retention_source)
    finalized = retention.closed if sheet else retention.finalized
    working = population
    if isinstance(population_source, InitialCollectionSource):
        working = _typed_context_populations(check, {check.population: population},
                                            {check.population: population_source})[check.population]
    cases, potential = plan_retained_record_instances(check, population)
    source_digest, check_digest = _digest(source), _digest(check.model_dump(mode="json"))
    if potential > check.max_instances:
        return RetainedEvaluation(source_digest, check_digest, (), False, "terminal_count_instance_budget_exceeded")
    budget_ok = len(cases) * len(retention.rows) * len(check.counts) <= 65536
    sheet_paths = {row.get("id"): ("task_evidence", "final", "google_sheets", "rows", index)
                   for index, row in enumerate(source.get("task_evidence", {}).get("final", {}).get("google_sheets", {}).get("rows", []))
                   if isinstance(row, Mapping)} if sheet and retention.closed else {}
    members = tuple((row, json.loads(row.cells_json)) for row in retention.rows) if (
        budget_ok and retention.closed and finalized) else ()
    findings = []
    for case in cases:
        rows = [row for row in working.rows if row.identity == case.candidate_identity]
        needed, value, status, reason, paths = None, None, "abstained", "terminal_count_candidate_unavailable", ()
        if len(rows) == 1 and population.status != "unavailable":
            row = rows[0]
            context = _context(check, row, {check.population: working})
            paths = (row.source_path,)
            required = evaluate_predicate(check.required_when, context)
            needed = required.value
            paths += required.evidence_paths
            if needed is False:
                status, reason = "inapplicable", "terminal_count_not_required"
            elif needed is None:
                reason = "terminal_count_requirement_unavailable"
            elif not finalized or not retention.closed:
                reason = "terminal_count_terminal_scope_unavailable"
            elif not budget_ok:
                reason = "terminal_count_comparison_budget_exceeded"
            else:
                totals = {}
                for count in check.counts:
                    total, decided = 0, True
                    for member, fields in members:
                        result = evaluate_predicate(count.where, {**context, "member": fields})
                        member_path = sheet_paths[member.native_record_id] if sheet else member.source_path
                        paths += (member_path, *result.evidence_paths)
                        if result.value is None:
                            decided = False
                        elif result.value:
                            total += 1
                    if decided:
                        totals[count.alias] = total
                result = evaluate_predicate(check.counts_when, {**context, "count": totals})
                paths += result.evidence_paths
                if result.value is None:
                    reason = "terminal_count_predicate_unavailable"
                else:
                    status, value, reason = "valid", float(result.value), "terminal_count_predicate_verified"
        findings.append(RetainedFinding(check.check_id, case.instance_key, check.signal_id,
            case.candidate_identity, None, status, value, reason, needed, paths))
    closed = population.closed and retention.closed and finalized and all(
        finding.status != "abstained" for finding in findings)
    return RetainedEvaluation(source_digest, check_digest, tuple(findings), closed,
        "terminal_count_scope_complete" if closed else "terminal_count_scope_unavailable")
