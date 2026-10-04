"""Declared initial record populations, without schema hydration or task policy."""

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from types import MappingProxyType, UnionType
from typing import Literal, Protocol, Union, cast, get_args, get_origin

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_serializer,
    model_validator,
)

from automationbench.schema.world import WorldState

from ..capture import canonical_json
from .base import FrozenModel, Identifier
from .tables import Digest

type Path = tuple[StrictStr | StrictInt, ...]


@cache
def _model(service: str, collection: str) -> type[BaseModel]:
    # The installed typed schema is the capability registry. Never instantiate
    # it to manufacture missing collections, aliases or native identities.
    if service not in WorldState.model_fields:
        raise ValueError("population_service_schema_unavailable")
    service_type = WorldState.model_fields[service].annotation
    if not isinstance(service_type, type) or not issubclass(service_type, BaseModel):
        raise ValueError("population_service_schema_unavailable")  # noqa: TRY004 - schema admission must become a validation failure.
    if collection not in service_type.model_fields:
        raise ValueError("population_collection_schema_unavailable")
    annotation = service_type.model_fields[collection].annotation
    args = get_args(annotation)
    if get_origin(annotation) is not list or len(args) != 1:
        raise ValueError("population_collection_schema_unavailable")
    record_type = args[0]
    if not isinstance(record_type, type) or not issubclass(record_type, BaseModel):
        raise ValueError("population_record_schema_unavailable")  # noqa: TRY004 - schema admission must become a validation failure.
    return record_type


def _string_keyed_mapping(annotation) -> bool:
    candidates = [item for item in (get_args(annotation) if get_origin(annotation) in (Union, UnionType) else ())
                  if item is not type(None)] or [annotation]
    return len(candidates) == 1 and get_origin(candidates[0]) is dict and get_args(candidates[0])[:1] == (str,)


def _names(info) -> tuple[str, ...]:
    """Plain-string schema aliases of a field (``alias``/``validation_alias``)."""
    names = []
    for alias in (info.alias, info.validation_alias):
        choices = alias.choices if isinstance(alias, AliasChoices) else (alias,)
        names.extend(choice for choice in choices if type(choice) is str)
    return tuple(dict.fromkeys(names))


def _canonical(model: type[BaseModel], part) -> str | None:
    """The canonical field a path step names: the field itself or one of its
    plain-string schema aliases (HubSpot ``lifecycle_stage`` -> ``lifecyclestage``)."""
    if type(part) is not str:
        return None
    if part in model.model_fields:
        return part
    owners = [name for name, info in model.model_fields.items() if part in _names(info)]
    return owners[0] if len(owners) == 1 else None


def _field(model: type[BaseModel], path: Path) -> None:
    # Canonical model field names or their plain-string schema aliases; no
    # array offsets or wildcard population expansion. A string-keyed mapping
    # field (HubSpot ``properties``) may be read one key deep as the last step.
    for index, part in enumerate(path):
        name = _canonical(model, part)
        if name is None:
            raise ValueError("population_field_path_unsupported")
        if index == len(path) - 2 and _string_keyed_mapping(model.model_fields[name].annotation):
            if type(path[-1]) is not str or not path[-1]:
                raise ValueError("population_field_path_unsupported")
            return
        if index != len(path) - 1:
            annotation = model.model_fields[name].annotation
            candidates = get_args(annotation) or (annotation,)
            nested = [item for item in candidates if isinstance(item, type)
                      and issubclass(item, BaseModel)]
            if len(nested) != 1:
                raise ValueError("population_field_path_unsupported")
            model = nested[0]


@cache
def _step_keys(model: type[BaseModel], path: Path) -> tuple[tuple[str, ...] | None, ...]:
    """Raw keys that may carry each schema path step (None: a mapping key).

    Public initial state is raw JSON written with schema aliases
    (``lifecycle_stage``); terminal snapshots are dumped with canonical names
    (``lifecyclestage``). Either key reads the same field.
    """
    keys: list[tuple[str, ...] | None] = []
    current: type[BaseModel] | None = model
    for part in path:
        name = _canonical(current, part) if current is not None else None
        if current is None or name is None:
            keys.append(None)
            current = None
            continue
        info = current.model_fields[name]
        keys.append(tuple(dict.fromkeys((name, *_names(info)))))
        candidates = get_args(info.annotation) or (info.annotation,)
        nested = [item for item in candidates if isinstance(item, type) and issubclass(item, BaseModel)]
        current = nested[0] if len(nested) == 1 else None
    return tuple(keys)


def _resolve_field(record: Mapping, model: type[BaseModel], path: Path):
    """Read a declared field path; a key and its alias that disagree are unread."""
    value = record
    for part, keys in zip(path, _step_keys(model, path), strict=True):
        if not isinstance(value, Mapping):
            return False, None
        present = [value[key] for key in (keys or (part,)) if key in value]
        if not present or any(canonical_json(item) != canonical_json(present[0]) for item in present[1:]):
            return False, None
        value = present[0]
    return True, value


def _digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class InitialCollectionSource(FrozenModel):
    adapter: Literal["initial.records@1"] = "initial.records@1"
    path: Path
    identity_path: Path = ("id",)
    # Composite native identity for records without a string ``id`` (Slack
    # messages: channel_id + ts). The identity value is the canonical JSON list
    # of these string fields, matching Slack effect identities. Omitted when empty.
    identity_paths: tuple[Path, ...] = Field(default=(), exclude_if=lambda value: not value)
    fields: dict[Identifier, Path]
    key_fields: tuple[Identifier, ...]
    required_fields: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def reviewed_schema(self):
        if (len(self.path) != 4 or self.path[:2] != ("task_evidence", "initial")
                or any(type(part) is not str or not part for part in self.path)):
            raise ValueError("population_initial_collection_path_required")
        model = _model(cast(str, self.path[2]), cast(str, self.path[3]))
        if self.identity_paths:
            if (self.identity_path != ("id",) or len(self.identity_paths) > 4
                    or len(set(self.identity_paths)) != len(self.identity_paths)
                    or any(len(path) != 1 or type(path[0]) is not str or path[0] not in model.model_fields
                           or model.model_fields[path[0]].annotation is not str for path in self.identity_paths)):
                raise ValueError("population_native_identity_required")
        elif (self.identity_path != ("id",) or "id" not in model.model_fields
                or model.model_fields["id"].annotation is not str):
            raise ValueError("population_native_identity_required")
        if not self.fields or any(not path for path in self.fields.values()):
            raise ValueError("population_projection_required")
        for path in self.fields.values():
            _field(model, path)
        if (not self.key_fields or len(set(self.key_fields)) != len(self.key_fields)
                or len(set(self.required_fields)) != len(self.required_fields)
                or any(field not in self.fields for field in
                       (*self.key_fields, *self.required_fields))):
            raise ValueError("population_projection_keys_invalid")
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        return self

    @field_serializer("fields")
    def serialize_fields(self, value):
        return dict(value)


def _resolve(record: Mapping, path: Path):
    value = record
    for part in path:
        if not isinstance(value, Mapping) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _native_identity(record, source) -> str | None:
    """The record's native identity: ``id`` or the declared composite fields."""
    if source.identity_paths:
        parts = [_resolve(record, path) for path in source.identity_paths]
        if any(not exists or type(part) is not str or not part for exists, part in parts):
            return None
        return canonical_json([part for _, part in parts])
    exists, native_id = _resolve(record, source.identity_path)
    return native_id if exists and type(native_id) is str and native_id else None


def _project(record, source):
    result = {}
    model = _model(cast(str, source.path[2]), cast(str, source.path[3]))
    for alias, path in source.fields.items():
        exists, value = _resolve_field(record, model, path)
        if exists:
            result[alias] = value
    return result


def _key(values, fields):
    if any(field not in values or type(values[field]) not in {str, int, float}
           or type(values[field]) is float and not math.isfinite(values[field])
           for field in fields):
        return None
    return canonical_json([[type(values[field]).__name__, values[field]] for field in fields])


class MemberEvidence(FrozenModel):
    identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr]
    raw_json: StrictStr
    cells_json: StrictStr
    key_json: StrictStr | None
    missing_fields: tuple[StrictStr, ...]
    source_path: Path

    @model_validator(mode="after")
    def canonical_records(self):
        for text in (self.raw_json, self.cells_json):
            value = json.loads(text)
            if not isinstance(value, dict) or canonical_json(value) != text:
                raise ValueError("population_canonical_object_required")
        return self


class PopulationEvidence(FrozenModel):
    source: InitialCollectionSource
    source_digest: Digest
    selector_digest: Digest
    schema_digest: Digest
    status: Literal["qualified", "partial", "unavailable"]
    closed: StrictBool
    enumerated: StrictBool = False
    reason: StrictStr
    rows: tuple[MemberEvidence, ...] = ()

    @model_validator(mode="after")
    def coherent_projection(self):
        source = self.source
        model = _model(cast(str, source.path[2]), cast(str, source.path[3]))
        if (self.selector_digest != _digest(source.model_dump(mode="json"))
                or self.schema_digest != _digest(model.model_json_schema())):
            raise ValueError("population_selector_or_schema_mismatch")
        if self.closed != (self.status == "qualified") or self.closed and not self.enumerated:
            raise ValueError("population_status_closure_inconsistent")
        identities, paths = [], []
        for row in self.rows:
            raw = json.loads(row.raw_json)
            native_id = _native_identity(raw, source)
            if native_id is None:
                raise ValueError("population_record_identity_invalid")
            if row.identity != (source.adapter, canonical_json(source.path), "str", native_id):
                raise ValueError("population_record_scope_mismatch")
            if (row.source_path[:-1] != source.path or len(row.source_path) != len(source.path) + 1
                    or type(row.source_path[-1]) is not int or row.source_path[-1] < 0):
                raise ValueError("population_record_path_mismatch")
            cells = _project(raw, source)
            missing = tuple(field for field in dict.fromkeys(
                (*source.key_fields, *source.required_fields)) if field not in cells)
            if (row.cells_json != canonical_json(cells) or row.missing_fields != missing
                    or row.key_json != _key(cells, source.key_fields)):
                raise ValueError("population_record_projection_mismatch")
            identities.append(row.identity)
            paths.append(row.source_path)
        if len(paths) != len(set(paths)):
            raise ValueError("population_duplicate_record_path")
        if len(identities) != len(set(identities)) and self.status != "unavailable":
            raise ValueError("population_duplicate_identity_requires_unavailable")
        return self


class Member(Protocol):
    @property
    def identity(self) -> tuple: ...
    @property
    def cells_json(self) -> str: ...
    @property
    def key_json(self) -> str | None: ...
    @property
    def missing_fields(self) -> tuple[str, ...]: ...


class PopulationSelector(Protocol):
    @property
    def key_fields(self) -> tuple[str, ...]: ...


class Population(Protocol):
    @property
    def source(self) -> PopulationSelector: ...
    @property
    def enumerated(self) -> bool: ...
    @property
    def source_digest(self) -> str: ...
    @property
    def selector_digest(self) -> str: ...
    @property
    def rows(self) -> tuple[Member, ...]: ...
    @property
    def closed(self) -> bool: ...
    @property
    def status(self) -> str: ...
    @property
    def reason(self) -> str: ...


@dataclass(frozen=True)
class LookupResult:
    status: Literal["matched", "not_found", "ambiguous", "unavailable"]
    reason: str
    matches: tuple[Member, ...]
    unresolved_rows: tuple[Member, ...] = ()


def capture_population(material: Mapping, source: InitialCollectionSource) -> PopulationEvidence:
    model = _model(cast(str, source.path[2]), cast(str, source.path[3]))
    base = {"source": source, "source_digest": _digest(material),
            "selector_digest": _digest(source.model_dump(mode="json")),
            "schema_digest": _digest(model.model_json_schema())}
    value = material
    for part in source.path:
        if not isinstance(value, Mapping) or part not in value:
            return PopulationEvidence(**base, status="unavailable", closed=False,
                                      reason="population_collection_missing")
        value = value[part]
    if not isinstance(value, list):
        return PopulationEvidence(**base, status="unavailable", closed=False,
                                  reason="population_collection_not_list")
    rows, ids, closed, duplicate = [], set(), True, False
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping) or any(type(key) is not str for key in raw):
            closed = False
            continue
        native_id = _native_identity(raw, source)
        if native_id is None:
            closed = False
            continue
        duplicate |= native_id in ids
        ids.add(native_id)
        cells = _project(raw, source)
        rows.append(MemberEvidence(
            identity=(source.adapter, canonical_json(source.path), "str", native_id),
            raw_json=canonical_json(dict(raw)), cells_json=canonical_json(cells),
            key_json=_key(cells, source.key_fields),
            missing_fields=tuple(field for field in dict.fromkeys(
                (*source.key_fields, *source.required_fields)) if field not in cells),
            source_path=(*source.path, index)))
    return PopulationEvidence(**base, status="unavailable" if duplicate else
                              "qualified" if closed else "partial",
                              closed=closed and not duplicate, enumerated=closed,
                              reason="population_duplicate_identity" if duplicate else
                              "population_declared_initial_collection" if closed else
                              "population_incomplete", rows=tuple(rows))


def validate_population_evidence(evidence: PopulationEvidence, material: Mapping) -> None:
    """Trust-boundary validation includes raw records, not only a claimed digest."""
    # model_copy intentionally bypasses Pydantic validators. Re-admit values
    # before comparing, and use canonical JSON so bool/int equality cannot
    # authenticate a changed index or closure label.
    admitted = PopulationEvidence.model_validate(evidence.model_dump(mode="python", warnings=False))
    actual = capture_population(material, evidence.source)
    if canonical_json(admitted.model_dump(mode="json")) != canonical_json(actual.model_dump(mode="json")):
        raise ValueError("population_source_or_projection_mismatch")


def lookup_population(population: Population, key: Mapping) -> LookupResult:
    # Source is structural too: TableSource and InitialCollectionSource expose
    # the same exact key inventory. Runtime validation stays in their adapters.
    fields = population.source.key_fields
    wanted = _key(key, fields)
    if set(key) != set(fields) or wanted is None:
        return LookupResult("unavailable", "lookup_key_unavailable", ())
    matches = tuple(row for row in population.rows if row.key_json == wanted)
    unknown = tuple(row for row in population.rows if row.key_json is None)
    if population.status == "unavailable":
        status, reason = "unavailable", population.reason
    elif len(matches) > 1:
        status, reason = "ambiguous", "lookup_multiple_exact_matches"
    elif not population.closed or unknown:
        status, reason = "unavailable", "lookup_population_not_closed"
    elif matches and any(row.missing_fields for row in matches):
        status, reason = "unavailable", "lookup_matched_row_fields_unavailable"
    elif matches:
        status, reason = "matched", "lookup_unique_exact_match"
    else:
        status, reason = "not_found", "lookup_closed_population_no_match"
    return LookupResult(status, reason, matches, unknown)


def native_record_id(row):
    """Sheets rows carry it; typed initial records use their native ``id`` identity."""
    value = getattr(row, "native_record_id", None)
    if value is None and row.identity and row.identity[0] == "initial.records@1":
        return row.identity[-1]
    return value
