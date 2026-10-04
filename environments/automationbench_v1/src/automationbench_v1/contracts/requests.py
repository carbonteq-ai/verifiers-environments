"""One authored obligation, qualified by bound public material.

Parameters are reviewed declarations, not observed baseline state. Consumers
must admit this population only for new-occurrence obligations.
"""

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, Literal, cast

from pydantic import (
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_serializer,
    model_validator,
)

from ..capture import canonical_json
from .base import FrozenModel, Identifier
from .populations import Path
from .tables import Digest


def _digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _public(path: Path) -> bool:
    return (len(path) >= 2 and path[0] == "task_evidence"
            and path[1] in {"prompt", "initial"})


def _path(path: Path) -> None:
    if (not path or any(type(part) is str and not part or
                        type(part) is int and part < 0 for part in path)
            or not _public(path)):
        raise ValueError("request_public_path_required")


def _scalar(value) -> bool:
    return type(value) in {str, bool, int, float} and (
        type(value) is not float or math.isfinite(value))


def _resolve(material: Mapping, path: Path):
    value = material
    for part in path:
        if (type(part) is str and isinstance(value, Mapping) and part in value
                or type(part) is int and isinstance(value, list) and 0 <= part < len(value)):
            value = cast(Any, value)[part]
        else:
            return False, None
    return True, value


class RequestField(FrozenModel):
    value: StrictStr | StrictBool | StrictInt | StrictFloat | None = None
    copy_from: Path | None = None
    authority_paths: tuple[Path, ...]

    @model_validator(mode="after")
    def qualified_declaration(self):
        literal = self.value is not None
        if literal == (self.copy_from is not None) or literal and not _scalar(self.value):
            raise ValueError("request_exactly_one_strict_scalar_or_projection")
        if not self.authority_paths or len(set(self.authority_paths)) != len(self.authority_paths):
            raise ValueError("request_unique_authority_paths_required")
        for path in self.authority_paths:
            _path(path)
        if self.copy_from is not None:
            _path(self.copy_from)
            if not any(self.copy_from[:len(path)] == path for path in self.authority_paths):
                raise ValueError("request_projection_authority_required")
        return self


class RequestSource(FrozenModel):
    adapter: Literal["public.request@1"] = "public.request@1"
    member_key: Identifier
    fields: dict[Identifier, RequestField]
    # This authored key is not a generated record ID or a Sheets row position.
    key_fields: tuple[Literal["request_key"], ...] = ("request_key",)

    @model_validator(mode="after")
    def one_member(self):
        if not self.fields or "request_key" in self.fields or self.key_fields != ("request_key",):
            raise ValueError("request_fields_or_authored_key_invalid")
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        return self

    @field_serializer("fields")
    def serialize_fields(self, fields):
        return dict(fields)


class RequestBinding(FrozenModel):
    """Structural copy of the public binding value, avoiding a models cycle."""

    path: Path
    canonical_sha256: Digest

    @model_validator(mode="after")
    def public_binding(self):
        _path(self.path)
        return self


def _bindings(bindings: Sequence) -> tuple[RequestBinding, ...]:
    admitted = tuple(RequestBinding.model_validate(
        binding.model_dump(mode="python", warnings=False) if hasattr(binding, "model_dump")
        else binding) for binding in bindings)
    if len({binding.path for binding in admitted}) != len(admitted):
        raise ValueError("request_duplicate_binding")
    return admitted


class RequestMemberEvidence(FrozenModel):
    identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr]
    cells_json: StrictStr
    key_json: StrictStr
    missing_fields: tuple[StrictStr, ...] = ()
    authority_paths_json: StrictStr


class RequestPopulationEvidence(FrozenModel):
    source: RequestSource
    source_digest: Digest
    selector_digest: Digest
    binding_digest: Digest
    authority_bindings_json: StrictStr
    status: Literal["qualified", "unavailable"]
    closed: StrictBool
    enumerated: StrictBool
    reason: StrictStr
    rows: tuple[RequestMemberEvidence, ...] = ()

    @model_validator(mode="after")
    def coherent_member(self):
        if self.selector_digest != _digest(self.source.model_dump(mode="json", exclude_none=True)):
            raise ValueError("request_selector_mismatch")
        qualified = self.status == "qualified"
        if self.closed is not qualified or self.enumerated is not True or len(self.rows) != 1:
            raise ValueError("request_population_closure_inconsistent")
        bindings = json.loads(self.authority_bindings_json)
        if (not isinstance(bindings, list) or canonical_json(bindings) != self.authority_bindings_json
                or _digest(bindings) != self.binding_digest):
            raise ValueError("request_binding_provenance_inconsistent")
        _bindings(bindings)
        row = self.rows[0]
        authorities = {name: [list(path) for path in field.authority_paths]
                       for name, field in self.source.fields.items()}
        if (row.identity != (self.source.adapter, self.selector_digest, "authored", self.source.member_key)
                or row.key_json != canonical_json([["str", self.source.member_key]])
                or row.authority_paths_json != canonical_json(authorities)):
            raise ValueError("request_member_identity_or_authority_inconsistent")
        if qualified:
            cells = json.loads(row.cells_json)
            if (not isinstance(cells, dict) or canonical_json(cells) != row.cells_json
                    or set(cells) != {*self.source.fields, "request_key"}
                    or any(not _scalar(value) for value in cells.values())
                    or cells["request_key"] != self.source.member_key
                    or row.identity != (self.source.adapter, self.selector_digest,
                                        "authored", self.source.member_key)
                    or row.key_json != canonical_json([["str", self.source.member_key]])
                    or row.missing_fields or row.authority_paths_json != canonical_json(authorities)):
                raise ValueError("request_member_projection_inconsistent")
            for name, field in self.source.fields.items():
                if field.copy_from is None and canonical_json(cells[name]) != canonical_json(field.value):
                    raise ValueError("request_literal_mismatch")
        elif (row.cells_json != canonical_json({"request_key": self.source.member_key})
              or row.missing_fields != tuple(sorted(self.source.fields))):
            raise ValueError("request_unavailable_fields_must_be_untrusted")
        return self


def capture_request_population(source: Mapping, spec: RequestSource,
                               bindings: Sequence) -> RequestPopulationEvidence:
    """Re-admit declarations and require every public authority to be bound."""
    spec = RequestSource.model_validate(spec.model_dump(mode="python", warnings=False))
    admitted = _bindings(bindings)
    binding_json = canonical_json([binding.model_dump(mode="json") for binding in admitted])
    base = {"source": spec, "source_digest": _digest(source),
            "selector_digest": _digest(spec.model_dump(mode="json", exclude_none=True)),
            "binding_digest": _digest(json.loads(binding_json)), "authority_bindings_json": binding_json}

    def unavailable(reason):
        row = RequestMemberEvidence(
            identity=(spec.adapter, base["selector_digest"], "authored", spec.member_key),
            cells_json=canonical_json({"request_key": spec.member_key}),
            key_json=canonical_json([["str", spec.member_key]]), missing_fields=tuple(sorted(spec.fields)),
            authority_paths_json=canonical_json({name: [list(path) for path in field.authority_paths]
                                                for name, field in spec.fields.items()}))
        return RequestPopulationEvidence(**base, status="unavailable", closed=False,
                                         enumerated=True, reason=reason, rows=(row,))

    if not any(binding.path[:2] == ("task_evidence", "prompt") for binding in admitted):
        return unavailable("request_public_prompt_binding_missing")
    for binding in admitted:
        exists, material = _resolve(source, binding.path)
        if not exists:
            return unavailable("request_bound_material_missing")
        if _digest(material) != binding.canonical_sha256:
            return unavailable("request_public_binding_mismatch")
    cells: dict[str, Any] = {"request_key": spec.member_key}
    for name, field in spec.fields.items():
        for path in field.authority_paths:
            if not any(path[:len(binding.path)] == binding.path for binding in admitted):
                return unavailable("request_field_authority_unbound")
            exists, _ = _resolve(source, path)
            if not exists:
                return unavailable("request_field_authority_missing")
        value = field.value
        if field.copy_from is not None:
            exists, value = _resolve(source, field.copy_from)
            if not exists or not _scalar(value):
                return unavailable("request_projected_scalar_unavailable")
        cells[name] = value
    row = RequestMemberEvidence(
        identity=(spec.adapter, base["selector_digest"], "authored", spec.member_key),
        cells_json=canonical_json(cells), key_json=canonical_json([["str", spec.member_key]]),
        authority_paths_json=canonical_json({name: [list(path) for path in field.authority_paths]
                                            for name, field in spec.fields.items()}))
    return RequestPopulationEvidence(**base, status="qualified", closed=True,
        enumerated=True, reason="request_one_public_bound_authored_obligation", rows=(row,))


def validate_request_population(evidence: RequestPopulationEvidence, source: Mapping,
                                bindings: Sequence) -> None:
    admitted = RequestPopulationEvidence.model_validate(evidence.model_dump(mode="python", warnings=False))
    actual = capture_request_population(source, admitted.source, bindings)
    if canonical_json(admitted.model_dump(mode="json")) != canonical_json(actual.model_dump(mode="json")):
        raise ValueError("request_raw_source_or_projection_mismatch")
