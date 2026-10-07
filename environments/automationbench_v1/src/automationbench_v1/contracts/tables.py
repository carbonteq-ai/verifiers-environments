"""Immutable declared finite tables and exact lookups, without policy decisions."""

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Annotated, Literal, cast

from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from ..capture import canonical_json
from ..effect_evidence import world_transitions
from .base import FrozenModel, Identifier

Digest = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]


class TableSource(FrozenModel):
    adapter: Literal["google_sheets.rows@1"] = "google_sheets.rows@1"
    path: tuple[StrictStr | StrictInt, ...]
    spreadsheet_id: Identifier
    worksheet_id: Identifier
    key_fields: tuple[Identifier, ...]
    required_fields: tuple[Identifier, ...] = ()

    @field_validator("path")
    @classmethod
    def valid_path(cls, value):
        if not value or any(
            type(item) is int and item < 0 or type(item) is str and not item for item in value
        ):
            raise ValueError("table_path_required_nonnegative")
        return value

    @field_validator("key_fields", "required_fields")
    @classmethod
    def unique_fields(cls, value, info):
        if len(set(value)) != len(value) or (info.field_name == "key_fields" and not value):
            raise ValueError("table_fields_unique_nonempty")
        return value


class RowEvidence(FrozenModel):
    identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr | StrictInt]
    native_record_id: Identifier | None = None
    cells_json: StrictStr
    missing_fields: tuple[StrictStr, ...]
    key_json: StrictStr | None
    source_path: tuple[StrictStr | StrictInt, ...]

    @model_validator(mode="after")
    def coherent_row(self):
        cells = json.loads(self.cells_json)
        if not isinstance(cells, dict) or self.cells_json != canonical_json(cells):
            raise ValueError("table_cells_canonical_object_required")
        kind, value = self.identity[2:]
        if kind != type(value).__name__ or type(value) is str and not value:
            raise ValueError("table_row_typed_identity_invalid")
        return self


class TableEvidence(FrozenModel):
    source: TableSource
    source_digest: Digest
    selector_digest: Digest
    status: Literal["qualified", "partial", "unavailable"]
    closed: StrictBool
    enumerated: StrictBool = False
    reason: StrictStr
    rows: tuple[RowEvidence, ...] = ()

    @model_validator(mode="after")
    def coherent_table(self):
        if self.closed != (self.status == "qualified"):
            raise ValueError("table_status_closure_inconsistent")
        if self.closed and not self.enumerated:
            raise ValueError("table_closed_requires_enumeration")
        if self.selector_digest != _digest(self.source.model_dump(mode="json")):
            raise ValueError("table_selector_digest_mismatch")
        identities = []
        native_ids = []
        paths = []
        for row in self.rows:
            if row.identity[:2] != (self.source.spreadsheet_id, self.source.worksheet_id):
                raise ValueError("table_row_scope_mismatch")
            if (
                len(row.source_path) != len(self.source.path) + 2
                or row.source_path[:-2] != self.source.path
                or row.source_path[-2] != "rows"
                or type(row.source_path[-1]) is not int
                or row.source_path[-1] < 0
            ):
                raise ValueError("table_row_path_mismatch")
            cells = json.loads(row.cells_json)
            missing = tuple(
                field
                for field in dict.fromkeys((*self.source.key_fields, *self.source.required_fields))
                if field not in cells
            )
            if row.missing_fields != missing or row.key_json != _key(cells, self.source.key_fields):
                raise ValueError("table_row_cell_projection_mismatch")
            identities.append(row.identity)
            if row.native_record_id is not None:
                native_ids.append(row.native_record_id)
            paths.append(row.source_path)
        if len(set(paths)) != len(paths):
            raise ValueError("table_duplicate_source_row_path")
        if len(set(identities)) != len(identities) and self.status != "unavailable":
            raise ValueError("table_duplicate_row_identity_requires_unavailable")
        if len(set(native_ids)) != len(native_ids) and self.status != "unavailable":
            raise ValueError("table_duplicate_native_identity_requires_unavailable")
        return self


class LookupEvidence(FrozenModel):
    status: Literal["matched", "not_found", "ambiguous", "unavailable"]
    reason: StrictStr
    matches: tuple[RowEvidence, ...]
    unresolved_rows: tuple[RowEvidence, ...] = ()


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _scalar(value):
    return type(value) in {str, int, float} and (type(value) is not float or math.isfinite(value))


def _key(cells, fields):
    if any(field not in cells or not _scalar(cells[field]) for field in fields):
        return None
    return canonical_json([[type(cells[field]).__name__, cells[field]] for field in fields])


def _contains_public(actual, public):
    """Compare every supplied field, without coercing or fabricating defaults."""
    if isinstance(public, Mapping):
        return isinstance(actual, Mapping) and all(
            key in actual and _contains_public(actual[key], value) for key, value in public.items()
        )
    return canonical_json(actual) == canonical_json(public)


def _initial_native_ids(material, source, service):
    """Bind omitted IDs only to acknowledged, complete revision-zero captures."""
    if source.path != ("task_evidence", "initial", "google_sheets"):
        return {}
    return _initial_sheet_binding(material, source.spreadsheet_id, source.worksheet_id, service)[0]


def initial_sheet_world(material: Mapping, spreadsheet_id: str, worksheet_id: str) -> str | None:
    """Reconcile a public initial table with its source-bound native BEFORE world.

    This returns observed evidence, never a newly hydrated WorldState. Only the
    selected table is reconciled; it makes no claim about unrelated services.
    """
    if type(spreadsheet_id) is not str or type(worksheet_id) is not str or not spreadsheet_id or not worksheet_id:
        return None
    try:
        service = material["task_evidence"]["initial"]["google_sheets"]
        if not isinstance(service, Mapping):
            return None
        return _initial_sheet_binding(material, spreadsheet_id, worksheet_id, service)[1]
    except (KeyError, TypeError):
        return None


def _initial_sheet_binding(material, spreadsheet_id, worksheet_id, service):
    public_rows = service.get("rows")
    if not isinstance(public_rows, list):
        return {}, None
    public = []
    for row in public_rows:
        if not isinstance(row, Mapping) or type(row.get("spreadsheet_id")) is not str or type(row.get("worksheet_id")) is not str:
            return {}, None
        if (row["spreadsheet_id"], row["worksheet_id"]) == (spreadsheet_id, worksheet_id):
            public.append(row)
    try:
        transitions = world_transitions(dict(material))
        zero_invocations = set()
        for event in material.get("tool_execution_events", []):
            receipt = json.loads(event["receipt_json"])
            if type(receipt.get("state_read_revision")) is int and receipt["state_read_revision"] == 0:
                zero_invocations.add((event["source"], receipt["invocation_id"]))
        candidates = [item for item in transitions if item.expected_revision == 0
                      or (item.origin, item.invocation_id) in zero_invocations]
        if not candidates:
            return {}, None
        agreed = None
        agreed_scope = None
        before_json = None
        for item in candidates:
            if (item.evidence_status != "acknowledged" or type(item.expected_revision) is not int
                    or type(item.applied_revision) is not int or item.applied_revision != 1
                    or item.before_json is None):
                return {}, None
            world = json.loads(item.before_json)
            captured = world.get("google_sheets")
            if not isinstance(captured, Mapping) or not isinstance(captured.get("rows"), list):
                return {}, None
            tabs = captured.get("worksheets")
            if not isinstance(tabs, list):
                return {}, None
            expected_tabs = [tab for tab in service.get("worksheets", []) if isinstance(tab, Mapping)
                             and tab.get("spreadsheet_id") == spreadsheet_id
                             and tab.get("id") == worksheet_id]
            actual_tabs = [tab for tab in tabs if isinstance(tab, Mapping)
                           and tab.get("spreadsheet_id") == spreadsheet_id
                           and tab.get("id") == worksheet_id]
            if len(expected_tabs) != 1 or len(actual_tabs) != 1 or not _contains_public(actual_tabs[0], expected_tabs[0]):
                return {}, None
            expected_sheets = service.get("spreadsheets")
            actual_sheets = captured.get("spreadsheets")
            if not isinstance(actual_sheets, list):
                return {}, None
            selected_sheets = [sheet for sheet in actual_sheets if isinstance(sheet, Mapping) and sheet.get("id") == spreadsheet_id]
            if len(selected_sheets) > 1:
                return {}, None
            if expected_sheets is not None:
                if not isinstance(expected_sheets, list):
                    return {}, None
                if any(not isinstance(sheet, Mapping) or type(sheet.get("id")) is not str for sheet in expected_sheets):
                    return {}, None
                expected_sheet = [sheet for sheet in expected_sheets if sheet["id"] == spreadsheet_id]
                if (len(expected_sheet) > 1 or len(selected_sheets) != len(expected_sheet)
                        or expected_sheet and not _contains_public(selected_sheets[0], expected_sheet[0])):
                    return {}, None
            rows = []
            for row in captured["rows"]:
                if not isinstance(row, Mapping) or type(row.get("spreadsheet_id")) is not str or type(row.get("worksheet_id")) is not str:
                    return {}, None
                if (row["spreadsheet_id"], row["worksheet_id"]) == (spreadsheet_id, worksheet_id):
                    rows.append(row)
            if len(rows) != len(public):
                return {}, None
            mapping, native = {}, set()
            for row in public:
                position = row.get("row_id")
                if type(position) not in {str, int}:
                    return {}, None
                key = (type(position).__name__, position)
                matches = [other for other in rows if type(other.get("row_id")) is type(position) and other["row_id"] == position]
                if (len(matches) != 1 or key in mapping or not _contains_public(matches[0], row)
                        or canonical_json(matches[0].get("cells")) != canonical_json(row.get("cells"))):
                    return {}, None
                identity = matches[0].get("id")
                if type(identity) is not str or not identity.strip() or identity in native:
                    return {}, None
                mapping[key] = identity
                native.add(identity)
            if agreed is not None and agreed != mapping:
                return {}, None
            scope = canonical_json({"spreadsheets": selected_sheets, "worksheets": actual_tabs, "rows": rows})
            if agreed_scope is not None and agreed_scope != scope:
                return {}, None
            agreed = mapping
            agreed_scope = scope
            before_json = before_json or item.before_json
        return agreed or {}, before_json
    except (ValueError, TypeError, KeyError, AttributeError):
        return {}, None


def capture_table(material: Mapping, source: TableSource) -> TableEvidence:
    """Project explicit collections; bind omitted IDs to proven initial captures."""
    base = {
        "source": source,
        "source_digest": _digest(material),
        "selector_digest": _digest(source.model_dump(mode="json")),
    }

    def unavailable(reason, rows=(), *, enumerated=False):
        return TableEvidence(**base, status="unavailable", closed=False,
                             enumerated=enumerated, reason=reason, rows=rows)

    service = material
    try:
        for part in source.path:
            if type(part) is int:
                if not isinstance(service, (list, tuple)):
                    return unavailable("table_path_unavailable")
                service = service[part]
            else:
                if not isinstance(service, Mapping):
                    return unavailable("table_path_unavailable")
                service = service[part]
    except (KeyError, IndexError):
        return unavailable("table_path_unavailable")
    if (
        not isinstance(service, Mapping)
        or not isinstance(service.get("worksheets"), list)
        or not isinstance(service.get("rows"), list)
    ):
        return unavailable("table_declared_collections_unavailable")
    tabs = service["worksheets"]
    exact = [
        tab
        for tab in tabs
        if isinstance(tab, Mapping)
        and tab.get("spreadsheet_id") == source.spreadsheet_id
        and tab.get("id") == source.worksheet_id
    ]
    if len(exact) != 1:
        return unavailable("table_worksheet_identity_unresolved")
    if "worksheets" in exact[0] or "rows" in exact[0]:
        return unavailable("table_nested_shape_unsupported")
    closed = all(
        isinstance(tab, Mapping)
        and type(tab.get("spreadsheet_id")) is str
        and type(tab.get("id")) is str
        for tab in tabs
    )
    needs_initial_binding = any(
        isinstance(row, Mapping) and "id" not in row
        and (row.get("spreadsheet_id"), row.get("worksheet_id"))
        == (source.spreadsheet_id, source.worksheet_id)
        for row in service["rows"]
    )
    initial_ids = _initial_native_ids(material, source, service) if needs_initial_binding else {}
    rows, identities, native_ids = [], set(), set()
    duplicate_identity = False
    for index, row in enumerate(service["rows"]):
        if (
            not isinstance(row, Mapping)
            or type(row.get("spreadsheet_id")) is not str
            or type(row.get("worksheet_id")) is not str
        ):
            closed = False
            continue
        if (row["spreadsheet_id"], row["worksheet_id"]) != (
            source.spreadsheet_id,
            source.worksheet_id,
        ):
            continue
        identity = row.get("row_id")
        if type(identity) not in {str, int} or isinstance(identity, str) and not identity:
            closed = False
            continue
        typed = (type(identity).__name__, cast(str | int, identity))
        if typed in identities:
            duplicate_identity = True
        identities.add(typed)
        native_id = row.get("id")
        if "id" not in row:
            native_id = initial_ids.get(typed)
        if "id" in row and (type(native_id) is not str or not native_id or not native_id.strip()):
            native_id = None
            closed = False
        if native_id is not None:
            if native_id in native_ids:
                duplicate_identity = True
            native_ids.add(native_id)
        cells = row.get("cells")
        if not isinstance(cells, Mapping) or any(type(key) is not str for key in cells):
            closed = False
            continue
        key = _key(cells, source.key_fields)
        missing = tuple(
            field
            for field in dict.fromkeys((*source.key_fields, *source.required_fields))
            if field not in cells
        )
        rows.append(
            RowEvidence(
                identity=(source.spreadsheet_id, source.worksheet_id, *typed),
                native_record_id=native_id,
                cells_json=canonical_json(dict(cells)),
                key_json=key,
                missing_fields=missing,
                source_path=(*source.path, "rows", index),
            )
        )
    if duplicate_identity:
        return unavailable("table_duplicate_row_identity", tuple(rows), enumerated=closed)
    return TableEvidence(
        **base,
        status="qualified" if closed else "partial",
        closed=closed,
        enumerated=closed,
        reason="table_declared_population" if closed else "table_population_incomplete",
        rows=tuple(rows),
    )


def left_lookup(table: TableEvidence, key: Mapping) -> LookupEvidence:
    """Preserve all definite matches; unknown rows prevent unique/negative claims."""
    wanted = _key(key, table.source.key_fields)
    if set(key) != set(table.source.key_fields) or wanted is None:
        return LookupEvidence(status="unavailable", reason="lookup_key_unavailable", matches=())
    matches = tuple(row for row in table.rows if row.key_json == wanted)
    unknown = tuple(row for row in table.rows if row.key_json is None)
    if table.status == "unavailable":
        status, reason = "unavailable", table.reason
    elif len(matches) > 1:
        status, reason = "ambiguous", "lookup_multiple_exact_matches"
    elif not table.closed or unknown:
        status, reason = "unavailable", "lookup_population_not_closed"
    elif matches and any(row.missing_fields for row in matches):
        status, reason = "unavailable", "lookup_matched_row_fields_unavailable"
    elif matches:
        status, reason = "matched", "lookup_unique_exact_match"
    else:
        status, reason = "not_found", "lookup_closed_population_no_match"
    return LookupEvidence(status=status, reason=reason, matches=matches, unresolved_rows=unknown)
