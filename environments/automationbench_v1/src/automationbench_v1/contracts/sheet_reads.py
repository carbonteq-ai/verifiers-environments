"""Native Google Sheets reads; no claim about subsequent model conditioning.

One fact per acknowledged successful read call per returned worksheet of the
declared spreadsheet (and worksheet, when declared). The read target is
resolved with the simulator's own reference resolution over the pre-call
world, exactly as the handler resolved it, because Sheets results do not name
their spreadsheet. Every returned row must exist in the pre-call target
worksheet with the same cell values, and returned worksheet metadata must
match the pre-call worksheet, so a forged or coherently rewritten result
cannot invent a read. A successful search that matched no row still read the
worksheet (``row_count`` 0, ``cell_values_returned`` false); failed reads
return nothing. Sheets writes are not reads; calls whose static footprint
excludes Sheets and which left it unchanged are skipped; metadata-only
discovery (Drive file search) returns nothing. ``api_fetch`` and unknown tools
leave the inventory incomplete.
"""

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict
from typing import Literal

from pydantic import Field

from automationbench.schema.google_sheets.base import GoogleSheetsState
from automationbench.tools.zapier.google_sheets._common import (
    SheetsReferenceError,
    resolve_spreadsheet,
    resolve_target,
)

from ..capture import canonical_json
from ..effect_evidence import world_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation, result_payload
from .base import FrozenModel, Identifier
from .effects import EffectEvidence, EffectFact
from .handler_scope import outside_service
from .service_hydration import public_service_matches
from .call_identity import same_call


class SheetReadSource(FrozenModel):
    adapter: Literal["google_sheets.reads@1"] = "google_sheets.reads@1"
    kind: Literal["read_sheet"] = "read_sheet"
    spreadsheet_id: Identifier
    # Omitted: every worksheet of the spreadsheet a call returned.
    worksheet_id: Identifier | None = Field(default=None, exclude_if=lambda value: value is None)


# Installed Sheets handlers that write state; never a read of stored rows.
_SHEET_WRITES = frozenset({
    "google_sheets_add_row", "google_sheets_append_row", "google_sheets_update_row",
    "google_sheets_delete_row", "google_sheets_create_spreadsheet", "google_sheets_create_worksheet",
})
# Audited reads whose results carry no worksheet content (Drive file metadata).
_NO_CONTENT = frozenset({"google_drive_find_multiple_files"})
_SEARCHES = frozenset({"google_sheets_find_many_rows", "google_sheets_lookup_row"})
_ROW_READS = _SEARCHES | {"google_sheets_get_many_rows", "google_sheets_get_row_by_id"}
_METADATA = frozenset({"google_sheets_find_worksheet", "google_sheets_get_spreadsheet_by_id"})
_READS = _NO_CONTENT | _ROW_READS | _METADATA


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _equal(left, right):
    return canonical_json(_plain(left)) == canonical_json(_plain(right))


def _key(value):
    if type(value) not in {str, int} or type(value) is str and not value:
        raise ValueError("sheet_read_row_identity_unavailable")
    return type(value).__name__, value


def _service(world):
    service = world.get("google_sheets")
    if not isinstance(service, Mapping) or any(
            not isinstance(service.get(key), (list, tuple)) for key in ("spreadsheets", "worksheets", "rows")):
        raise TypeError("sheet_read_service_unavailable")
    for key in ("worksheets", "rows"):
        if any(not isinstance(item, Mapping) or type(item.get("spreadsheet_id")) is not str
               for item in service[key]):
            raise ValueError("sheet_read_scope_unavailable")
    return service


def _target_rows(service, spreadsheet_id, worksheet_id):
    rows = [row for row in service["rows"]
            if row["spreadsheet_id"] == spreadsheet_id and row.get("worksheet_id") == worksheet_id]
    keys = [_key(row.get("row_id")) for row in rows]
    natives = [row.get("id") for row in rows]
    if (len(set(keys)) != len(keys) or any(type(value) is not str or not value for value in natives)
            or len(set(natives)) != len(natives) or any(not isinstance(row.get("cells"), Mapping) for row in rows)):
        raise ValueError("sheet_read_target_population_unavailable")
    return rows


def _tab(service, spreadsheet_id, worksheet_id):
    tabs = [tab for tab in service["worksheets"]
            if tab["spreadsheet_id"] == spreadsheet_id and tab.get("id") == worksheet_id]
    if len(tabs) > 1:
        raise ValueError("sheet_read_worksheet_identity_ambiguous")
    return tabs[0] if tabs else None


def _resolve(name, args, service):
    """The handler's own (spreadsheet, worksheet) resolution over the pre-call state."""
    state = GoogleSheetsState.model_validate(copy.deepcopy(_plain(service)))
    if name == "google_sheets_get_spreadsheet_by_id":
        reference = args.get("spreadsheet") or args.get("spreadsheet_id") or args.get("id") or ""
        resolved = resolve_spreadsheet(state, reference)
        if resolved is None:
            raise ValueError("sheet_read_requested_target_unresolved")
        return resolved, None
    if name == "google_sheets_find_worksheet":
        sheet, tab = args.get("spreadsheet") or args.get("spreadsheet_id") or "", args.get("title") or ""
    elif name == "google_sheets_get_row_by_id":
        sheet, tab = args.get("spreadsheet"), args.get("worksheet")
    elif name == "google_sheets_get_many_rows":
        sheet = args.get("spreadsheet") or args.get("spreadsheet_id")
        tab = args.get("worksheet") or args.get("worksheet_id") or args.get("worksheet_title")
    else:
        sheet = args.get("spreadsheet") or args.get("spreadsheet_id")
        tab = args.get("worksheet") or args.get("worksheet_id")
    try:
        return resolve_target(state, sheet, tab)
    except SheetsReferenceError as error:
        raise ValueError("sheet_read_requested_target_unresolved") from error


def _count(result, rows):
    if (type(result.get("result_count")) is not int or result["result_count"] != len(rows)
            or type(result.get("total_count")) is not int or result["total_count"] < len(rows)):
        raise ValueError("sheet_read_result_count_unavailable")


def _project_rows(returned, originals, *, headers=None):
    """Returned row views checked against the pre-call worksheet rows."""
    by_key = {_key(row["row_id"]): row for row in originals}
    seen, row_ids, natives, fields, values = set(), [], [], set(), False
    for view in returned:
        if not isinstance(view, Mapping):
            raise TypeError("sheet_read_returned_row_unavailable")
        key = _key(view.get("row_id"))
        if key in seen:
            raise ValueError("sheet_read_returned_identity_ambiguous")
        seen.add(key)
        original = by_key.get(key)
        if original is None:
            raise ValueError("sheet_read_before_identity_unavailable")
        stored = {field: _plain(value) for field, value in original["cells"].items()}
        if headers is None:
            cells = view.get("cells")
            if not isinstance(cells, Mapping):
                raise TypeError("sheet_read_returned_cells_unavailable")
            if any(field not in stored or not _equal(value, stored[field]) for field, value in cells.items()):
                raise ValueError("sheet_read_returned_cells_mismatch")
            returned_fields = list(cells)
        else:
            raw = view.get("values")
            if not isinstance(raw, (list, tuple)) or len(raw) != len(headers):
                raise TypeError("sheet_read_returned_values_unavailable")
            if any(not _equal(value, stored.get(field)) for field, value in zip(headers, raw, strict=True)):
                raise ValueError("sheet_read_returned_cells_mismatch")
            returned_fields = [field for field in headers if field in stored]
        fields.update(returned_fields)
        values = values or bool(returned_fields)
        row_ids.append(view["row_id"])
        natives.append(original["id"])
    every = {_key(row["row_id"]) for row in originals} == seen
    return {"row_ids": row_ids, "native_row_ids": natives, "row_count": len(row_ids),
            "returned_fields": sorted(fields), "cell_values_returned": values, "all_rows_returned": every}


def _metadata(view, tab):
    """A returned worksheet entry must be the pre-call worksheet object."""
    if not isinstance(view, Mapping) or tab is None:
        raise ValueError("sheet_read_returned_worksheet_unavailable")
    for field in ("id", "title", "headers", "spreadsheet_id"):
        if field in view and (field not in tab or not _equal(view[field], tab[field])):
            raise ValueError("sheet_read_returned_worksheet_mismatch:" + field)


def _empty():
    return {"row_ids": [], "native_row_ids": [], "row_count": 0, "returned_fields": [],
            "cell_values_returned": False, "all_rows_returned": False}


def _returned(name, args, result, service, selected):
    """(spreadsheet_id, worksheet_id, row projection) per worksheet the call returned."""
    if type(result.get("success")) is not bool:
        raise ValueError("sheet_read_result_success_unavailable")
    if result["success"] is not True or "error" in result:
        return []  # an acknowledged failed read returned nothing
    if name in _NO_CONTENT:
        return []
    spreadsheet_id, worksheet_id = _resolve(name, args, service)
    if spreadsheet_id != selected:
        return []  # another spreadsheet: resolved, not a read of this scope
    if name == "google_sheets_get_spreadsheet_by_id":
        sheet = result.get("spreadsheet")
        if not isinstance(sheet, Mapping) or sheet.get("id") != spreadsheet_id:
            raise ValueError("sheet_read_returned_spreadsheet_mismatch")
        tabs = sheet.get("worksheets")
        if not isinstance(tabs, (list, tuple)):
            raise TypeError("sheet_read_returned_worksheets_unavailable")
        ids = [view.get("id") if isinstance(view, Mapping) else None for view in tabs]
        if len(set(ids)) != len(ids):
            raise ValueError("sheet_read_returned_identity_ambiguous")
        out = []
        for view in tabs:
            _metadata(view, _tab(service, spreadsheet_id, view.get("id")))
            originals = _target_rows(service, spreadsheet_id, view["id"])
            if "rows" in view:
                rows = view["rows"]
                if (not isinstance(rows, (list, tuple)) or type(view.get("row_count")) is not int
                        or view["row_count"] != len(originals)):
                    raise ValueError("sheet_read_grid_count_unavailable")
                out.append((spreadsheet_id, view["id"], _project_rows(rows, originals)))
            else:
                out.append((spreadsheet_id, view["id"], _empty()))
        return out
    originals = _target_rows(service, spreadsheet_id, worksheet_id)
    tab = _tab(service, spreadsheet_id, worksheet_id)
    if name == "google_sheets_find_worksheet":
        view = result.get("worksheet")
        _metadata(view, tab)
        if view.get("id") != worksheet_id:
            raise ValueError("sheet_read_returned_worksheet_mismatch:id")
        return [(spreadsheet_id, worksheet_id, _empty())]
    if name == "google_sheets_get_row_by_id":
        view = result.get("row")
        if not isinstance(view, Mapping):
            raise TypeError("sheet_read_get_result_unavailable")
        return [(spreadsheet_id, worksheet_id, _project_rows((view,), originals))]
    rows = result.get("rows")
    if not isinstance(rows, (list, tuple)):
        raise TypeError("sheet_read_rows_unavailable")
    _count(result, rows)
    headers = None
    if name == "google_sheets_get_many_rows" and result.get("output_format") == "raw_rows":
        headers = result.get("headers")
        if not isinstance(headers, (list, tuple)) or any(type(field) is not str for field in headers):
            raise TypeError("sheet_read_returned_headers_unavailable")
    return [(spreadsheet_id, worksheet_id, _project_rows(rows, originals, headers=headers))]


def capture_sheet_reads(source: Mapping, spec: SheetReadSource) -> EffectEvidence:
    spec = SheetReadSource.model_validate(spec.model_dump(mode="python", warnings=False))
    source_id, selector_id = _digest(source), _digest(spec.model_dump(mode="json"))
    facts, reasons = [], []
    try:
        if any(not isinstance(source.get(field), (list, tuple)) for field in ("tool_execution_events", "state_write_receipts")):
            raise ValueError("sheet_read_execution_inventory_missing")
        index = EffectIndex(world_transitions(dict(source)))
        terminals = {}
        for event in source["tool_execution_events"]:
            receipt = json.loads(event["receipt_json"])
            if receipt["phase"] != "dispatch":
                terminals[event["source"], receipt["invocation_id"]] = receipt
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return EffectEvidence(source_id, selector_id, (), False, str(error))
    for occurrence in index.occurrences:
        try:
            if (occurrence.origin != "tool_server" or occurrence.action is None or occurrence.before_json is None
                    or occurrence.after_json is None or EffectIndex((occurrence,)).serial_chain().status != "qualified"):
                raise ValueError("sheet_read_ack_or_capture_unavailable")
            action = occurrence.action
            before, after = index.world(occurrence.before_json), index.world(occurrence.after_json)
            name, args = operation(action)
            if name in _SHEET_WRITES or outside_service(name, "google_sheets", before, after):
                continue  # writes and calls that cannot reach Sheets are not reads
            receipt = terminals[occurrence.origin, occurrence.invocation_id]
            native_arguments = json.loads(receipt.get("arguments_json", "null"))
            if (receipt.get("tool_name") != action.tool_name or not isinstance(native_arguments, dict)
                    or set(native_arguments) != {"args", "kwargs"} or native_arguments["args"] != []
                    or not same_call(action.tool_name, native_arguments["kwargs"], json.loads(action.arguments_json))):
                raise ValueError("sheet_read_native_invocation_mismatch")
            if (action.status != "returned" or action.error_json is not None or action.result_json is None
                    or receipt.get("error_json") is not None or receipt.get("state_error_json") is not None
                    or receipt.get("result_json") != action.result_json):
                raise ValueError("sheet_read_local_native_return_mismatch")
            if name not in _READS:
                raise ValueError("sheet_read_operation_unsupported")
            if not _equal(before.get("google_sheets"), after.get("google_sheets")):
                raise ValueError("sheet_read_changed_scope")
            result = result_payload(action)
            if result is None:
                raise ValueError("sheet_read_result_unavailable")
            service = _service(before)
            # Every returned worksheet of the spreadsheet is checked, then filtered.
            for spreadsheet_id, worksheet_id, projection in _returned(name, args, result, service,
                                                                      spec.spreadsheet_id):
                if spreadsheet_id != spec.spreadsheet_id or spec.worksheet_id not in {None, worksheet_id}:
                    continue
                tab = _tab(service, spreadsheet_id, worksheet_id)
                title = tab.get("title") if tab is not None else None
                params = {"spreadsheet_id": spreadsheet_id, "worksheet_id": worksheet_id,
                          "worksheet_title": title if type(title) is str else None,
                          **projection, "operation": name}
                facts.append(EffectFact(_digest([occurrence.invocation_id, spreadsheet_id, worksheet_id]),
                    occurrence.invocation_id, "tool_server", spec.kind, canonical_json(params), "qualified",
                    "acknowledged_native_returned_sheet_read", occurrence.expected_revision,
                    occurrence.applied_revision))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            reasons.append(str(error))
            facts.append(EffectFact(None, occurrence.invocation_id, "tool_server", spec.kind, None,
                "unavailable", str(error), occurrence.expected_revision, occurrence.applied_revision))
    try:
        task = source["task_evidence"]
        if task.get("complete") is not True:
            raise ValueError("sheet_read_finalization_unavailable")
        _service(task["final"])
        expected = {item.invocation_id for item in index.occurrences}
        if len(source["state_write_receipts"]) != len(expected) or {item["write_id"] for item in source["state_write_receipts"]} != expected:
            raise ValueError("sheet_read_ack_inventory_mismatch")
        if index.occurrences:
            chain = index.serial_chain()
            if chain.status != "qualified" or chain.revision_interval is None or chain.revision_interval[0] != 0:
                raise ValueError("sheet_read_complete_chain_unavailable")
            first, last = chain.ordered[0], chain.ordered[-1]
            if first.before_json is None or last.after_json is None:
                raise ValueError("sheet_read_boundary_capture_unavailable")
            if (not public_service_matches(task["initial"], "google_sheets", index.world(first.before_json)["google_sheets"])
                    or not _equal(task["final"]["google_sheets"], index.world(last.after_json)["google_sheets"])):
                raise ValueError("sheet_read_initial_terminal_scope_mismatch")
        elif not public_service_matches(task["initial"], "google_sheets", task["final"]["google_sheets"]):
            raise ValueError("sheet_read_unobserved_scope_change")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    return EffectEvidence(source_id, selector_id, tuple(facts), not reasons,
        reasons[0] if reasons else "reconciled_sheet_read_inventory")


def validate_sheet_reads(evidence: EffectEvidence, source: Mapping, spec: SheetReadSource) -> None:
    actual = capture_sheet_reads(source, spec)
    if canonical_json(_plain(asdict(evidence))) != canonical_json(asdict(actual)):
        raise ValueError("sheet_read_raw_source_or_projection_mismatch")
