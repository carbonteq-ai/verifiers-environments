"""Final raw records satisfy obligations on the original initial native IDs."""

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping
from types import MappingProxyType, SimpleNamespace, UnionType
from typing import Annotated, Literal, Union, cast, get_args, get_origin

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_serializer,
    field_validator,
    model_validator,
)

from ..capture import canonical_json
from .base import FrozenModel, Identifier
from .guards import LookupSpec
from .obligations import _context, _fields
from .populations import (
    InitialCollectionSource,
    Path,
    PopulationEvidence,
    _field,
    _key,
    _model,
    _project,
    _resolve,
    capture_population,
)
from .predicates import Predicate, evaluate_predicate, parse_predicate
from .retained import RetainedCase, RetainedEvaluation, RetainedFinding
from .tables import Digest


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class RetainedRecordSource(FrozenModel):
    adapter: Literal["final.records@1"] = "final.records@1"
    path: Path
    identity_path: Path = ("id",)
    fields: dict[Identifier, Path]

    @model_validator(mode="after")
    def schema(self):
        if (len(self.path) != 4 or self.path[:2] != ("task_evidence", "final")
                or any(type(part) is not str or not part for part in self.path)):
            raise ValueError("retained_record_final_collection_required")
        model = _model(cast(str, self.path[2]), cast(str, self.path[3]))
        if self.identity_path != ("id",) or "id" not in model.model_fields or model.model_fields["id"].annotation is not str:
            raise ValueError("retained_record_native_identity_required")
        if not self.fields:
            raise ValueError("retained_record_projection_required")
        for path in self.fields.values():
            if not path:
                raise ValueError("retained_record_field_path_required")
            _field(model, path)
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        return self

    @field_serializer("fields")
    def projected(self, value):
        return dict(value)


class RetainedRecordCheck(FrozenModel):
    check_id: Identifier
    signal_id: Identifier
    role: Literal["goal"]
    operator: Literal["records.retained_when@1"] = "records.retained_when@1"
    population: Identifier
    source: Identifier
    lookups: tuple[LookupSpec, ...] = ()
    required_when: Predicate
    supported_when: Predicate | None = Field(default=None, exclude_if=lambda value: value is None)
    retained_when: Predicate
    max_instances: StrictInt = Field(default=4096, ge=1, le=65536)

    @field_validator("required_when", "supported_when", "retained_when", mode="before")
    @classmethod
    def predicate(cls, value):
        return parse_predicate(value) if value is not None else None

    @model_validator(mode="after")
    def context(self):
        aliases = [lookup.alias for lookup in self.lookups]
        if len(set(aliases)) != len(aliases) or set(aliases) & {"request", "candidate", "retained", "effect"}:
            raise ValueError("retained_record_lookup_alias_conflict")
        available = {"request", "candidate"}
        for lookup in self.lookups:
            if any(len(value.path) < 2 or value.path[0] not in available for value in lookup.keys.values()):
                raise ValueError("retained_record_lookup_context_unknown")
            available.add(lookup.alias)
        for name in ("required_when", "supported_when", "retained_when"):
            predicate = getattr(self, name)
            roots = available | ({"retained"} if name == "retained_when" else set())
            if predicate is not None and any(len(path) < 2 or path[0] not in roots
                    for path in _fields(predicate.model_dump(mode="python"))):
                raise ValueError("retained_record_predicate_context_unknown")
        return self


class RetainedRecord(FrozenModel):
    native_record_id: StrictStr
    source_path: Path
    raw_json: StrictStr
    cells_json: StrictStr
    unavailable_fields: tuple[StrictStr, ...]


class RecordRetentionEvidence(FrozenModel):
    source: RetainedRecordSource
    source_digest: Digest
    selector_digest: Digest
    schema_digest: Digest
    finalized: StrictBool
    enumerated: StrictBool
    closed: StrictBool
    status: Literal["qualified", "partial", "unavailable"]
    reason: StrictStr
    duplicate_ids: tuple[StrictStr, ...] = ()
    rows: tuple[RetainedRecord, ...] = ()


def _leaf(model, path):
    for index, part in enumerate(path):
        info = model.model_fields[part]
        if index == len(path) - 1:
            return info.rebuild_annotation()
        types = get_args(info.annotation) or (info.annotation,)
        model = next(item for item in types if isinstance(item, type) and hasattr(item, "model_fields"))


def _literal_types(value, annotation):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        return _literal_types(value, args[0])
    if origin is Literal:
        return any(type(value) is type(allowed) and value == allowed for allowed in args)
    if origin in {Union, UnionType}:
        for branch in args:
            if not _literal_types(value, branch):
                continue
            try:
                TypeAdapter(branch).validate_json(canonical_json(value), strict=True)
                return True
            except ValueError:
                pass
        return False
    if origin is list and isinstance(value, list):
        return all(_literal_types(item, args[0]) for item in value)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel) and isinstance(value, Mapping):
        return all(_literal_types(item, annotation.model_fields[name].rebuild_annotation())
                   for name, item in value.items() if name in annotation.model_fields)
    return True


def _finite(value):
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, BaseModel):
        return all(_finite(getattr(value, name)) for name in type(value).model_fields)
    if isinstance(value, Mapping):
        return all(_finite(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return all(_finite(item) for item in value)
    return True


def _typed_context_populations(check, populations, selectors):
    """Private predicate projections; authenticated population receipts stay intact."""
    names = {"request": check.population, **{lookup.alias: lookup.source for lookup in check.lookups}}
    used = {name: set(spec.key_fields) for name, spec in selectors.items()}
    for path in _fields(check.model_dump(mode="python")):
        if path[0] in names:
            used[names[path[0]]].add(path[1])
    working = {}
    for name, population in populations.items():
        spec = selectors[name]
        model = _model(cast(str, spec.path[2]), cast(str, spec.path[3]))
        rows = []
        for row in population.rows:
            cells = json.loads(row.cells_json)
            for alias in used[name]:
                if alias not in cells:
                    continue
                annotation = _leaf(model, spec.fields[alias])
                try:
                    if not _literal_types(cells[alias], annotation):
                        raise ValueError("retained_record_initial_literal_type_unavailable")
                    value = TypeAdapter(annotation).validate_json(canonical_json(cells[alias]), strict=True)
                    if not _finite(value):
                        raise ValueError("retained_record_initial_numeric_domain_unavailable")
                except ValueError:
                    del cells[alias]
            rows.append(SimpleNamespace(identity=row.identity, source_path=row.source_path,
                cells_json=canonical_json(cells), key_json=_key(cells, spec.key_fields),
                missing_fields=tuple(sorted(set(row.missing_fields) | {
                    alias for alias in (*spec.key_fields, *spec.required_fields) if alias not in cells}))))
        working[name] = SimpleNamespace(source=spec, status=population.status, reason=population.reason,
            closed=population.closed, enumerated=population.enumerated, source_digest=population.source_digest,
            selector_digest=population.selector_digest, rows=tuple(rows))
    return working


def capture_record_retention(source: Mapping, spec: RetainedRecordSource) -> RecordRetentionEvidence:
    spec = RetainedRecordSource.model_validate(spec.model_dump(mode="python", warnings=False))
    model = _model(cast(str, spec.path[2]), cast(str, spec.path[3]))
    task = source.get("task_evidence")
    base = {"source": spec, "source_digest": _digest(source), "selector_digest": _digest(spec.model_dump(mode="json")),
            "schema_digest": _digest(model.model_json_schema()),
            "finalized": isinstance(task, Mapping) and task.get("complete") is True}
    exists, values = _resolve(source, spec.path)
    if not exists or not isinstance(values, list):
        return RecordRetentionEvidence(**base, enumerated=False, closed=False, status="unavailable",
            reason="retained_record_terminal_collection_unavailable")
    rows, ids, identities_complete = [], [], True
    annotations = {alias: _leaf(model, path) for alias, path in spec.fields.items()}
    adapters = {alias: TypeAdapter(annotation) for alias, annotation in annotations.items()}
    for index, raw in enumerate(values):
        if not isinstance(raw, Mapping) or any(type(key) is not str for key in raw):
            identities_complete = False
            continue
        exists, identity = _resolve(raw, spec.identity_path)
        if not exists or type(identity) is not str or not identity:
            identities_complete = False
            continue
        ids.append(identity)
        cells = _project(raw, spec)
        unavailable = []
        for alias in spec.fields:
            if alias not in cells:
                unavailable.append(alias)
                continue
            try:
                # Validate only supplied leaves. Never use hydrated/normalized
                # values, defaults or aliases as terminal facts.
                if not _literal_types(cells[alias], annotations[alias]):
                    raise ValueError("retained_record_literal_type_unavailable")
                validated = adapters[alias].validate_json(canonical_json(cells[alias]), strict=True)
                if not _finite(validated):
                    raise ValueError("retained_record_numeric_domain_unavailable")
            except ValueError:
                del cells[alias]
                unavailable.append(alias)
        rows.append(RetainedRecord(native_record_id=identity, source_path=(*spec.path, index),
            raw_json=canonical_json(dict(raw)), cells_json=canonical_json(cells), unavailable_fields=tuple(sorted(unavailable))))
    duplicates = tuple(sorted(identity for identity, count in Counter(ids).items() if count > 1))
    closed = identities_complete and not duplicates
    return RecordRetentionEvidence(**base, enumerated=identities_complete, closed=closed,
        status="qualified" if closed else "partial", reason="retained_record_identities_closed" if closed else "retained_record_identity_scope_partial",
        duplicate_ids=duplicates, rows=tuple(rows))


def validate_record_retention(evidence: RecordRetentionEvidence, source: Mapping, spec: RetainedRecordSource) -> None:
    admitted = RecordRetentionEvidence.model_validate(evidence.model_dump(mode="python", warnings=False))
    actual = capture_record_retention(source, spec)
    if canonical_json(admitted.model_dump(mode="json")) != canonical_json(actual.model_dump(mode="json")):
        raise ValueError("retained_record_source_or_projection_mismatch")


def plan_retained_record_instances(check: RetainedRecordCheck, population: PopulationEvidence):
    count = len(population.rows)
    if count > check.max_instances:
        return (), count
    return tuple(RetainedCase(_digest([check.check_id, population.selector_digest, identity]), identity)
                 for identity in dict.fromkeys(row.identity for row in population.rows)), count


def evaluate_retained_records(source: Mapping, check: RetainedRecordCheck, populations: Mapping[str, PopulationEvidence],
        retention: RecordRetentionEvidence, *, population_sources: Mapping[str, InitialCollectionSource],
        retention_source: RetainedRecordSource) -> RetainedEvaluation:
    check = RetainedRecordCheck.model_validate(check.model_dump(mode="python", warnings=False))
    required_sources = {check.population, *(lookup.source for lookup in check.lookups)}
    if set(populations) != required_sources or set(population_sources) != required_sources:
        raise ValueError("retained_record_population_inventory_mismatch")
    for name in required_sources:
        spec = InitialCollectionSource.model_validate(population_sources[name].model_dump(mode="python", warnings=False))
        actual = capture_population(source, spec)
        admitted = PopulationEvidence.model_validate(populations[name].model_dump(mode="python", warnings=False))
        if canonical_json(admitted.model_dump(mode="json")) != canonical_json(actual.model_dump(mode="json")):
            raise ValueError("retained_record_initial_projection_mismatch")
    initial = population_sources[check.population]
    if initial.path[2:] != retention_source.path[2:] or initial.identity_path != retention_source.identity_path:
        raise ValueError("retained_record_collection_scope_mismatch")
    for lookup in check.lookups:
        if set(lookup.keys) != set(population_sources[lookup.source].key_fields):
            raise ValueError("retained_record_lookup_key_inventory_mismatch")
    contexts = {"request": initial, "retained": retention_source,
                **{lookup.alias: population_sources[lookup.source] for lookup in check.lookups}}
    for path in _fields(check.model_dump(mode="python")):
        if path[0] == "candidate":
            if path[1] not in {"identity", "native_record_id"} or len(path) != 2:
                raise ValueError("retained_record_candidate_projection_undeclared")
            continue
        selector = contexts[path[0]]
        if path[1] not in selector.fields:
            raise ValueError("retained_record_predicate_projection_undeclared")
        model = _model(cast(str, selector.path[2]), cast(str, selector.path[3]))
        _field(model, (*selector.fields[path[1]], *path[2:]))
    validate_record_retention(retention, source, retention_source)
    population = populations[check.population]
    working_populations = _typed_context_populations(check, populations, population_sources)
    cases, count = plan_retained_record_instances(check, population)
    source_id, check_id = _digest(source), _digest(check.model_dump(mode="json"))
    if count > check.max_instances:
        return RetainedEvaluation(source_id, check_id, (), False, "retained_record_instance_budget_exceeded")
    findings = []
    for case in cases:
        rows = [row for row in population.rows if row.identity == case.candidate_identity]
        row, native_id = rows[0], case.candidate_identity[3]
        status, value, needed, reason = "abstained", None, None, "retained_record_initial_identity_ambiguous"
        paths = (row.source_path,)
        if len(rows) == 1:
            working_row = next(item for item in working_populations[check.population].rows if item.identity == row.identity)
            context = _context(check, working_row, working_populations)
            context["candidate"]["native_record_id"] = native_id
            applicability = evaluate_predicate(check.required_when, context)
            needed = applicability.value
            paths += applicability.evidence_paths
            support = evaluate_predicate(check.supported_when, context) if needed is True and check.supported_when is not None else None
            if support is not None:
                paths += support.evidence_paths
            if needed is False:
                status, reason = "inapplicable", "retained_record_not_required"
            elif needed is None:
                reason = "retained_record_requirement_unavailable"
            elif support is not None and support.value is not True:
                reason = "retained_record_domain_unsupported" if support.value is False else "retained_record_domain_unavailable"
            elif not retention.finalized:
                reason = "retained_record_finalization_unavailable"
            else:
                matches = [record for record in retention.rows if record.native_record_id == native_id]
                if len(matches) > 1:
                    reason = "retained_record_terminal_identity_ambiguous"
                elif not matches:
                    if retention.closed:
                        status, value, reason = "valid", 0.0, "retained_record_original_absent"
                    else:
                        reason = "retained_record_terminal_membership_unavailable"
                else:
                    context["retained"] = json.loads(matches[0].cells_json)
                    paths += (matches[0].source_path,)
                    result = evaluate_predicate(check.retained_when, context)
                    paths += result.evidence_paths
                    if result.value is None:
                        reason = "retained_record_predicate_unavailable"
                    else:
                        status, value, reason = "valid", float(result.value), "retained_record_predicate_verified"
        findings.append(RetainedFinding(check.check_id, case.instance_key, check.signal_id, case.candidate_identity,
            native_id, status, value, reason, needed, paths))
    closed = population.closed and retention.closed and retention.finalized and all(finding.status != "abstained" for finding in findings)
    return RetainedEvaluation(source_id, check_id, tuple(findings), closed,
        "retained_record_scope_complete" if closed else "retained_record_scope_unavailable")
