"""Qualified native Sheets writes; occurrence and terminal state stay separate."""

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from automationbench.tools.zapier.google_sheets._common import parse_cells

from ..capture import canonical_json
from ..effect_evidence import world_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation, result_payload
from .base import FrozenModel, Identifier
from .effects import EffectEvidence, EffectFact
from .handler_scope import handler_footprints, outside_service
from .tables import Digest, initial_sheet_world


class SheetEffectSource(FrozenModel):
    adapter: Literal["google_sheets.row_writes@1"] = "google_sheets.row_writes@1"
    kind: Literal["append", "update"]
    spreadsheet_id: Identifier
    worksheet_id: Identifier
    # Services through which public policy lets the same effect happen outside
    # this worksheet (e.g. a ticket queue that could also be a helpdesk). A call
    # that can touch one of them leaves this scope open rather than letting the
    # worksheet alone certify absence. Omitted when empty (legacy digests).
    alternative_services: tuple[Identifier, ...] = Field(default=(), exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def known_alternatives(self):
        from automationbench.schema.world import WorldState

        services = self.alternative_services
        if (len(set(services)) != len(services) or "google_sheets" in services
                or any(service not in WorldState.model_fields for service in services)):
            raise ValueError("sheet_alternative_services_invalid")
        return self


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


# Exact installed native-handler audit, not name-prefix or metadata inference.
# row.py/_common.py and worksheet.py/spreadsheet.py only read Sheets state in
# these paths (lookup_row's metadata says search_or_write, but its implementation
# is _search_rows and never creates records). meta.search_tools only queries the
# tool registry; it has no WorldState argument. Gmail message.py find/send touch
# Gmail only; google_drive.actions.find_multiple_files reads Drive + Sheets but
# never mutates either. slack.search.py and its helpers read Slack state only.
# The source must originate in the installed native tool-server dispatch; this
# audit cannot authenticate arbitrary caller-written handlers with forged names.
_READS = frozenset({"google_sheets_get_many_rows", "google_sheets_get_spreadsheet_by_id",
                   "google_sheets_get_row_by_id", "google_sheets_lookup_row", "google_sheets_find_worksheet",
                   "google_sheets_find_many_rows"})
_NO_SHEET_WRITES = _READS | frozenset({
    "search_tools", "gmail_find_email", "gmail_send_email", "google_drive_find_multiple_files",
    "slack_find_message", "slack_find_message_in_channel", "slack_get_message",
    "slack_get_message_reactions", "slack_list_channel_messages", "slack_get_channel_messages",
    "slack_get_thread_replies",
})


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _id(value):
    if type(value) not in {str, int} or type(value) is str and not value:
        raise ValueError("sheet_row_identity_unavailable")
    return type(value).__name__, value


def _collection(world, spec):
    service = world.get("google_sheets")
    if not isinstance(service, Mapping):
        raise TypeError("sheet_service_unavailable")
    for key in ("spreadsheets", "worksheets", "rows"):
        if not isinstance(service.get(key), (tuple, list)):
            raise TypeError("sheet_collection_unavailable")
    tabs = service["worksheets"]
    if (any(isinstance(sheet, Mapping) and ("worksheets" in sheet or "rows" in sheet)
            for sheet in service["spreadsheets"])
            or any(isinstance(tab, Mapping) and "rows" in tab for tab in tabs)):
        raise ValueError("sheet_nested_population_unsupported")
    if any(not isinstance(tab, Mapping) or type(tab.get("id")) is not str
           or type(tab.get("spreadsheet_id")) is not str for tab in tabs):
        raise ValueError("sheet_worksheet_scope_unavailable")
    selected = [tab for tab in tabs if tab["spreadsheet_id"] == spec.spreadsheet_id
                and tab["id"] == spec.worksheet_id]
    if len(selected) != 1:
        raise ValueError("sheet_worksheet_identity_unavailable")
    rows, ids, native_ids = [], set(), set()
    for row in service["rows"]:
        if (not isinstance(row, Mapping) or type(row.get("spreadsheet_id")) is not str
                or type(row.get("worksheet_id")) is not str):
            raise ValueError("sheet_row_scope_unavailable")
        if (row["spreadsheet_id"], row["worksheet_id"]) != (spec.spreadsheet_id, spec.worksheet_id):
            continue
        key = _id(row.get("row_id"))
        if key in ids or type(row.get("id")) is not str or not row["id"] or row["id"] in native_ids:
            raise ValueError("sheet_row_population_identity_unavailable")
        if not isinstance(row.get("cells"), Mapping) or any(type(field) is not str for field in row["cells"]):
            raise ValueError("sheet_row_cells_unavailable")
        ids.add(key)
        native_ids.add(row["id"])
        rows.append(row)
    return service, selected[0], tuple(rows)


def _scope(world, spec):
    service, tab, rows = _collection(world, spec)
    spreadsheets = [sheet for sheet in service["spreadsheets"] if isinstance(sheet, Mapping)
                    and sheet.get("id") == spec.spreadsheet_id]
    return canonical_json(_plain({"spreadsheets": spreadsheets, "worksheet": tab, "rows": rows}))


def _target(service, args):
    sheet_ref = args.get("spreadsheet") or args.get("spreadsheet_id")
    tab_ref = args.get("worksheet") or args.get("worksheet_id")
    if ((sheet_ref is not None and type(sheet_ref) is not str)
            or (tab_ref is not None and type(tab_ref) is not str)):
        raise ValueError("sheet_requested_target_unavailable")
    sheets, tabs = service["spreadsheets"], service["worksheets"]
    known = {tab["spreadsheet_id"] for tab in tabs}
    known.update(row["spreadsheet_id"] for row in service["rows"])
    for sheet in sheets:
        if not isinstance(sheet, Mapping) or type(sheet.get("id")) is not str:
            raise ValueError("sheet_spreadsheet_identity_unavailable")
        known.add(sheet["id"])
    sheet_ref = sheet_ref.strip() if sheet_ref else None
    tab_ref = tab_ref.strip() if tab_ref else None
    if not sheet_ref:
        owners = {tab["spreadsheet_id"] for tab in tabs if tab_ref and
                  (tab["id"] == tab_ref or type(tab.get("title")) is str
                   and tab["title"].strip().lower() == tab_ref.lower())}
        if len(owners) != 1:
            raise ValueError("sheet_requested_spreadsheet_ambiguous")
        sheet_id = owners.pop()
    elif sheet_ref in known:
        sheet_id = sheet_ref
    else:
        matches = [sheet["id"] for sheet in sheets if type(sheet.get("title")) is str
                   and sheet["title"].strip().lower() == sheet_ref.lower()]
        if len(matches) != 1:
            raise ValueError("sheet_requested_spreadsheet_ambiguous")
        sheet_id = matches[0]
    candidates = [tab for tab in tabs if tab["spreadsheet_id"] == sheet_id]
    if not tab_ref:
        if len(candidates) != 1:
            raise ValueError("sheet_requested_worksheet_ambiguous")
        return sheet_id, candidates[0]["id"]
    exact = [tab for tab in candidates if tab["id"] == tab_ref]
    matches = exact or [tab for tab in candidates if type(tab.get("title")) is str
                        and tab["title"].strip().lower() == tab_ref.lower()]
    if len(matches) != 1:
        raise ValueError("sheet_requested_worksheet_ambiguous")
    return sheet_id, matches[0]["id"]


def _requested_cells(name, args, tab, rows):
    headers = tab.get("headers")
    if not isinstance(headers, (tuple, list)) or any(type(header) is not str for header in headers):
        raise ValueError("sheet_headers_unavailable")
    headers = list(headers)
    if not headers:
        headers = list(dict.fromkeys(field for row in rows for field in row["cells"]))
    raw = args.get("cells")
    if name == "google_sheets_append_row":
        # The installed legacy wrapper selects row/row_data before values;
        # add_row itself has a different precedence. Preserve the actual call.
        raw = raw or args.get("row") or args.get("row_data") or args.get("values") or args.get("fields")
    elif name == "google_sheets_add_row":
        raw = raw or args.get("values") or args.get("row") or args.get("row_data") or args.get("fields")
    return parse_cells(_plain(raw), headers)


def _requested_row(args):
    value = args.get("row")
    if value is None or value == "":
        value = args.get("row_id")
    if type(value) not in {str, int}:
        raise ValueError("sheet_requested_row_unavailable")
    # Installed update tool parses an integer row reference, including #N.
    try:
        return int(str(value).strip().lstrip("#"))
    except ValueError:
        return str(value).strip()


def capture_sheet_effects(source: Mapping, spec: SheetEffectSource) -> EffectEvidence:
    spec = SheetEffectSource.model_validate(spec.model_dump(mode="python"))
    source_id, selector_id = _digest(source), _digest(spec.model_dump(mode="json"))
    facts, reasons = [], []
    def result():
        return EffectEvidence(source_id, selector_id, tuple(facts), not reasons,
                              reasons[0] if reasons else "reconciled_native_sheet_write_inventory")
    try:
        for key in ("tool_execution_events", "state_write_receipts"):
            if not isinstance(source.get(key), (tuple, list)):
                raise TypeError("sheet_execution_inventory_unavailable")
        index = EffectIndex(world_transitions(dict(source)))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
        return result()
    for occurrence in index.occurrences:
        try:
            if occurrence.origin != "tool_server" or occurrence.action is None:
                raise ValueError("sheet_execution_origin_or_action_unavailable")
            if occurrence.before_json is None or occurrence.after_json is None:
                raise ValueError("sheet_write_capture_unavailable")
            footprint = handler_footprints().get(operation(occurrence.action)[0])
            if spec.alternative_services and footprint is not None and footprint & set(spec.alternative_services):
                raise ValueError("sheet_alternative_channel_unobserved")
            if outside_service(operation(occurrence.action)[0], "google_sheets",
                               index.world(occurrence.before_json), index.world(occurrence.after_json)):
                continue
            before, after = index.world(occurrence.before_json), index.world(occurrence.after_json)
            before_service, tab, old = _collection(before, spec)
            _, _, new = _collection(after, spec)
            name, args = operation(occurrence.action)
            if occurrence.evidence_status != "acknowledged" or occurrence.action.status != "returned" or occurrence.action.error_json is not None:
                raise ValueError("sheet_write_acknowledgement_unavailable")
            if EffectIndex((occurrence,)).serial_chain().status != "qualified":
                raise ValueError("sheet_write_revision_unavailable")
            kinds = {"google_sheets_add_row": "append", "google_sheets_append_row": "append",
                     "google_sheets_update_row": "update"}
            if name not in kinds:
                # A reviewed handler effect scope plus unchanged source-backed
                # selected objects rules out a selected-table write. Unknown
                # APIs remain open even if their endpoints happen to agree.
                if name in _NO_SHEET_WRITES and _scope(before, spec) == _scope(after, spec):
                    continue
                raise ValueError("sheet_operation_scope_unsupported")
            target = _target(before_service, args)
            if target != (spec.spreadsheet_id, spec.worksheet_id):
                if _scope(before, spec) != _scope(after, spec):
                    raise ValueError("sheet_other_target_changed_selected_population")
                continue
            returned = result_payload(occurrence.action)
            if returned is None or returned.get("success") is not True or "error" in returned:
                raise ValueError("sheet_write_result_failed")
            row_view = returned.get("row")
            if not isinstance(row_view, Mapping) or not isinstance(row_view.get("cells"), Mapping):
                raise TypeError("sheet_returned_row_unavailable")
            row_id = row_view.get("row_id")
            key = _id(row_id)
            previous = [row for row in old if _id(row["row_id"]) == key]
            current = [row for row in new if _id(row["row_id"]) == key]
            if len(current) != 1 or len(previous) > 1:
                raise ValueError("sheet_persisted_target_unavailable")
            current_row = current[0]
            if canonical_json(_plain(row_view["cells"])) != canonical_json(_plain(current_row["cells"])):
                raise ValueError("sheet_returned_cells_disagree")
            requested = _requested_cells(name, args, tab, old)
            kind = kinds[name]
            if kind == "append":
                if previous or any(row["id"] == current_row["id"] for row in old):
                    raise ValueError("sheet_append_not_new")
                if (returned.get("spreadsheet_id"), returned.get("worksheet_id")) != target:
                    raise ValueError("sheet_returned_scope_disagree")
                if type(row_id) is not int or row_id != max(
                        (row["row_id"] for row in old if type(row["row_id"]) is int), default=1) + 1:
                    raise ValueError("sheet_appended_row_position_disagree")
                expected = requested
                old_cells = None
            else:
                if _id(_requested_row(args)) != key or len(previous) != 1 or previous[0]["id"] != current_row["id"]:
                    raise ValueError("sheet_updated_target_disagree")
                old_cells = _plain(previous[0]["cells"])
                expected = old_cells | requested
            if canonical_json(expected) != canonical_json(_plain(current_row["cells"])):
                raise ValueError("sheet_requested_fields_disagree")
            others_old = [row for row in old if _id(row["row_id"]) != key]
            others_new = [row for row in new if _id(row["row_id"]) != key]
            if canonical_json(_plain(others_old)) != canonical_json(_plain(others_new)):
                raise ValueError("sheet_write_other_rows_changed")
            if kind != spec.kind:
                continue
            after_cells = _plain(current_row["cells"])
            changed = tuple(field for field in dict.fromkeys((*(old_cells or {}), *after_cells))
                if old_cells is None or field not in old_cells or field not in after_cells
                or canonical_json(old_cells[field]) != canonical_json(after_cells[field]))
            params = {"spreadsheet_id": spec.spreadsheet_id, "worksheet_id": spec.worksheet_id,
                "row_id": row_id, "row_id_type": key[0], "native_record_id": current_row["id"],
                "before_cells": old_cells, "after_cells": after_cells,
                "requested_fields": tuple(requested), "changed_fields": changed}
            facts.append(EffectFact(canonical_json([*target, *key]), occurrence.invocation_id,
                "tool_server", kind, canonical_json(params), "qualified",
                "native_sheet_write_ack_result_and_persisted_row", occurrence.expected_revision, occurrence.applied_revision))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            reasons.append(str(error))
            facts.append(EffectFact(None, occurrence.invocation_id, "tool_server", spec.kind, None,
                "unavailable", str(error), occurrence.expected_revision, occurrence.applied_revision))
    try:
        task = source["task_evidence"]
        _collection(task["final"], spec)
        if task.get("complete") is not True:
            raise ValueError("sheet_finalization_unavailable")
        chain = index.serial_chain()
        if (chain.status != "qualified" or chain.revision_interval is None
                or chain.revision_interval[0] != 0):
            raise ValueError("sheet_history_revision_unavailable")
        writes = source["state_write_receipts"]
        expected_ids = {occurrence.invocation_id for occurrence in index.occurrences}
        if ({write["write_id"] for write in writes} != expected_ids or len(writes) != len(expected_ids)):
            raise ValueError("sheet_ack_inventory_mismatch")
        initial_text = canonical_json(task["initial"])
        if chain.ordered[0].before_json != initial_text:
            initial_text = initial_sheet_world(source, spec.spreadsheet_id, spec.worksheet_id)
        if (initial_text is None or chain.ordered[0].before_json is None
                or _scope(json.loads(initial_text), spec) != _scope(index.world(chain.ordered[0].before_json), spec)
                or chain.ordered[-1].after_json != canonical_json(task["final"])):
            raise ValueError("sheet_initial_terminal_reconciliation_failed")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    return result()


class RetainedRow(FrozenModel):
    identity: tuple[StrictStr, StrictStr, StrictStr, StrictStr | StrictInt]
    native_record_id: Identifier
    cells_json: StrictStr

    @model_validator(mode="after")
    def coherent(self):
        if (self.identity[2] != type(self.identity[3]).__name__
                or any(not part.strip() for part in self.identity[:2])
                or type(self.identity[3]) is str and not self.identity[3]):
            raise ValueError("sheet_retained_identity_invalid")
        cells = json.loads(self.cells_json)
        if not isinstance(cells, dict) or canonical_json(cells) != self.cells_json:
            raise ValueError("sheet_retained_cells_invalid")
        return self


class SheetRetentionEvidence(FrozenModel):
    source_digest: Digest
    selector_digest: Digest
    status: Literal["qualified", "unavailable"]
    closed: StrictBool
    reason: StrictStr
    rows: tuple[RetainedRow, ...] = ()

    @model_validator(mode="after")
    def coherent(self):
        if self.closed != (self.status == "qualified") or len({row.identity for row in self.rows}) != len(self.rows):
            raise ValueError("sheet_retained_population_invalid")
        if len({row.native_record_id for row in self.rows}) != len(self.rows):
            raise ValueError("sheet_retained_native_identity_ambiguous")
        if len({row.identity[:2] for row in self.rows}) > 1:
            raise ValueError("sheet_retained_population_scope_ambiguous")
        return self


def capture_sheet_retention(source: Mapping, spec: SheetEffectSource) -> SheetRetentionEvidence:
    spec = SheetEffectSource.model_validate(spec.model_dump(mode="python"))
    base = {"source_digest": _digest(source), "selector_digest": _digest(spec.model_dump(mode="json"))}
    rows = ()
    try:
        task = source["task_evidence"]
        _, _, population = _collection(task["final"], spec)
        rows = tuple(RetainedRow(identity=(spec.spreadsheet_id, spec.worksheet_id, *_id(row["row_id"])),
            native_record_id=row["id"], cells_json=canonical_json(_plain(row["cells"]))) for row in population)
        if task.get("complete") is not True:
            raise ValueError("sheet_terminal_finalization_unavailable")
        return SheetRetentionEvidence(**base, status="qualified", closed=True,
                                      reason="captured_final_sheet_population", rows=rows)
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return SheetRetentionEvidence(**base, status="unavailable", closed=False, reason=str(error), rows=rows)


def validate_sheet_retention(evidence: SheetRetentionEvidence, source: Mapping, spec: SheetEffectSource) -> None:
    admitted = SheetRetentionEvidence.model_validate(evidence.model_dump(mode="python", warnings=False))
    actual = capture_sheet_retention(source, spec)
    if canonical_json(admitted.model_dump(mode="json")) != canonical_json(actual.model_dump(mode="json")):
        raise ValueError("sheet_retained_source_or_projection_mismatch")
