"""Receipt-backed Jira issue facts; no policy, reward, or legacy issue hydration.

Callers must first admit the native source. Recapture authenticates projections
against that source, not a caller's right to manufacture an entire native trace.
Inventory knowledge, individual transitions and history closure are separate.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal, cast

from pydantic import StrictBool, StrictInt, StrictStr, model_validator

from automationbench.schema.jira import JiraActionRecord, JiraState
from automationbench.tools.api.fetch import _url_to_internal_path
from automationbench.tools.api.routes.jira import route_jira

from ..capture import canonical_json
from ..effect_evidence import persisted_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation, result_payload
from .base import FrozenModel, Identifier
from .handler_scope import outside_service
from .tables import Digest
from .call_identity import same_call


class JiraIssueSource(FrozenModel):
    adapter: Literal["jira.issues@1"] = "jira.issues@1"
    project_id: Identifier | None = None


class JiraIssueFact(FrozenModel):
    issue_id: Identifier
    issue_json: StrictStr

    @model_validator(mode="after")
    def coherent(self):
        raw = json.loads(self.issue_json)
        if canonical_json(raw) != self.issue_json or raw.get("id") != self.issue_id:
            raise ValueError("jira_issue_fact_identity_or_encoding_invalid")
        _canonical_issue(raw)
        return self


class JiraInventory(FrozenModel):
    status: Literal["qualified", "partial", "unavailable"]
    closed: StrictBool
    reason: StrictStr
    finalized: StrictBool = True
    identities_complete: StrictBool = False
    all_issue_ids: tuple[Identifier, ...] = ()
    duplicate_ids: tuple[Identifier, ...] = ()
    issues: tuple[JiraIssueFact, ...] = ()

    @model_validator(mode="after")
    def coherent(self):
        if self.closed != (self.status == "qualified"):
            raise ValueError("jira_inventory_status_invalid")
        if len(set(self.all_issue_ids)) != len(self.all_issue_ids):
            raise ValueError("jira_inventory_ids_not_unique")
        ids = [issue.issue_id for issue in self.issues]
        if (len(ids) != len(set(ids)) or not set(ids) <= set(self.all_issue_ids)
                or set(ids) & set(self.duplicate_ids)
                or not set(self.duplicate_ids) <= set(self.all_issue_ids)):
            raise ValueError("jira_inventory_identity_invalid")
        if self.closed and (not self.identities_complete or self.duplicate_ids or not self.finalized):
            raise ValueError("jira_inventory_closure_invalid")
        return self


class JiraTransition(FrozenModel):
    invocation_id: Identifier
    origin: Identifier = "tool_server"
    kind: Literal["create", "status_update", "unknown"]
    status: Literal["qualified", "unavailable"]
    reason: StrictStr
    issue_id: Identifier | None = None
    audit_id: Identifier | None = None
    before_issue_json: StrictStr | None = None
    after_issue_json: StrictStr | None = None
    expected_revision: StrictInt | None = None
    applied_revision: StrictInt | None = None
    changed_fields: tuple[Identifier, ...] = ()
    requested_fields: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def coherent(self):
        if self.status == "qualified":
            if (self.origin != "tool_server" or self.kind == "unknown" or self.issue_id is None or self.audit_id is None
                    or self.issue_id == self.audit_id or self.after_issue_json is None
                    or self.expected_revision is None or self.expected_revision < 0
                    or self.applied_revision != self.expected_revision + 1
                    or (self.kind == "create") != (self.before_issue_json is None)):
                raise ValueError("jira_transition_identity_or_revision_invalid")
            for raw in (self.before_issue_json, self.after_issue_json):
                if raw is not None:
                    JiraIssueFact(issue_id=self.issue_id, issue_json=raw)
        return self


class JiraEvidence(FrozenModel):
    source_digest: Digest
    selector_digest: Digest
    transitions: tuple[JiraTransition, ...] = ()
    initial: JiraInventory
    final: JiraInventory
    complete: StrictBool
    reason: StrictStr


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _json(value):
    return canonical_json(_plain(value))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _text(value):
    return type(value) is str and bool(value.strip())


def _service(world):
    service = world.get("jira")
    if not isinstance(service, Mapping) or not isinstance(service.get("actions"), Mapping):
        raise TypeError("jira_service_or_actions_unavailable")
    if not isinstance(service.get("issues"), (tuple, list)):
        raise TypeError("jira_issue_collection_unavailable")
    return service


def _canonical_issue(issue):
    if not isinstance(issue, Mapping) or not _text(issue.get("id")):
        raise ValueError("jira_issue_identity_unavailable")
    if "key" in issue and not _text(issue["key"]):
        raise ValueError("jira_issue_key_unavailable")
    fields = issue.get("fields")
    if not isinstance(fields, Mapping) or not _text(fields.get("summary")):
        raise ValueError("jira_issue_fields_unavailable")
    project = fields.get("project")
    if (not isinstance(project, Mapping) or not project
            or set(project) - {"id", "key", "name"}
            or any(not _text(value) for value in project.values())):
        raise ValueError("jira_issue_project_unavailable")
    for name in ("issuetype", "status", "priority"):
        if name == "priority" and name not in fields:
            continue
        value = fields.get(name)
        if not isinstance(value, Mapping) or set(value) != {"name"} or not _text(value["name"]):
            raise ValueError("jira_issue_named_field_unavailable")
    for name in ("creation_action_id", "last_action_id"):
        if name in issue and (not _text(issue[name]) or issue[name] == issue["id"]):
            raise ValueError("jira_issue_audit_identity_invalid")
    _json(issue)
    return issue


def _ids(rows) -> tuple[list[str], bool]:
    identities = [cast(str, row.get("id")) for row in rows if isinstance(row, Mapping) and _text(row.get("id"))]
    return identities, len(identities) == len(rows)


def _inventory(world, spec, *, finalized=True):
    try:
        service = _service(world)
        rows = service["issues"]
        identities, known = _ids(rows)
        counts = Counter(identities)
        duplicate = tuple(sorted(identity for identity, count in counts.items() if count > 1))
        issues, reasons = [], []
        if not known:
            reasons.append("jira_inventory_unknown_identity")
        if duplicate:
            reasons.append("jira_inventory_duplicate_identity")
        state = JiraState.model_validate(_plain(service))
        for row in rows:
            try:
                _canonical_issue(row)
                if row["id"] in duplicate:
                    continue
                fields = row["fields"]
                project = fields["project"]
                resolved = state.resolve_project(project.get("id") or project.get("key") or project.get("name"))
                if any(resolved.get(key) != value for key, value in project.items()):
                    raise ValueError("jira_issue_project_conflict")
                if spec.project_id is None or resolved.get("id") == spec.project_id:
                    issues.append(JiraIssueFact(issue_id=row["id"], issue_json=_json(row)))
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                reasons.append(str(error))
        if not finalized:
            reasons.append("jira_inventory_finalization_unavailable")
        return JiraInventory(status="partial" if reasons else "qualified", closed=not reasons,
            reason=reasons[0] if reasons else "captured_jira_issue_inventory",
            finalized=finalized,
            identities_complete=known, all_issue_ids=tuple(sorted(counts)), duplicate_ids=duplicate,
            issues=tuple(sorted(issues, key=lambda item: item.issue_id)))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return JiraInventory(status="unavailable", closed=False, reason=str(error), finalized=finalized)


def _explicit_membership(raw, reason):
    if not isinstance(raw, Mapping) or not isinstance(raw.get("issues"), (list, tuple)):
        return JiraInventory(status="unavailable", closed=False, reason=reason)
    # Public identity membership is independent of whether captured before-worlds
    # can supply omitted schema defaults. Never import issue fields from an
    # ambiguous anchor, or treat an omitted public collection as empty.
    ids, known = _ids(raw["issues"])
    counts = Counter(ids)
    return JiraInventory(status="partial", closed=False, reason=reason,
        identities_complete=known, all_issue_ids=tuple(sorted(counts)),
        duplicate_ids=tuple(sorted(key for key, count in counts.items() if count > 1)))


def _initial(source, index, spec):
    raw = None
    try:
        declared = source["task_evidence"]["initial"]
        raw = declared.get("jira")
        if not isinstance(raw, Mapping):
            raise TypeError("jira_initial_service_unavailable")
        anchors = [item for item in index.occurrences if item.expected_revision == 0
                   and type(item.expected_revision) is int
                   and item.action is not None and item.action.status == "returned"
                   and item.action.error_json is None
                   and EffectIndex((item,)).serial_chain().status == "qualified"]
        if not anchors and isinstance(raw.get("issues"), (list, tuple)):
            return _explicit_membership(raw, "jira_explicit_initial_membership_without_anchor")
        if len(anchors) != 1 or anchors[0].before_json is None:
            raise ValueError("jira_initial_revision_zero_anchor_unavailable")
        _receipt_binding(source, anchors[0])
        before = index.world(anchors[0].before_json)
        native = _service(before)
        prepared = _plain(raw)
        # Only generated action-record defaults may be supplied by this exact
        # acknowledged initial anchor; no issue is constructed from a log.
        actions = prepared.get("actions", {})
        for key, rows in actions.items():
            captured = native["actions"].get(key)
            if not isinstance(captured, (tuple, list)) or len(rows) != len(captured):
                raise ValueError("jira_initial_actions_mismatch")
            for row, actual in zip(rows, captured, strict=True):
                for field in ("id", "created_at"):
                    if field not in row:
                        row[field] = actual[field]
        normalized = JiraState.model_validate(prepared).model_dump(mode="json")
        if _json(normalized) != _json(native):
            raise ValueError("jira_initial_schema_reconciliation_failed")
        return _inventory(before, spec)
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return _explicit_membership(raw, str(error))


def _operation(action):
    name, args = operation(action)
    if name != "api_fetch":
        return name, args
    path, router = _url_to_internal_path(args.get("url", ""))
    method = args.get("method")
    if router is route_jira and type(method) is str:
        if method.upper() == "POST" and path == "jira/rest/api/3/issue":
            body = args.get("body") or {}
            if isinstance(body, str):
                body = json.loads(body)
            if not isinstance(body, Mapping):
                raise ValueError("jira_api_body_invalid")
            return "jira_api_create", body
        if method.upper() == "GET" and path == "jira/rest/api/3/project/search":
            return "jira_project", args
    return name, args


def _params(name, args, state):
    if name == "jira_update_issue":
        if set(args) - {"issueKey", "transition", "format_info"}:
            raise ValueError("jira_update_arguments_unsupported")
        return {k: _plain(v) for k, v in args.items() if v is not None and v != ""}
    if name == "jira_api_create":
        if set(args) - {"fields", "project", "issuetype", "summary", "priority", "description"}:
            raise ValueError("jira_create_arguments_unsupported")
        values = {k: _plain(v) for k, v in args.items() if k != "fields"}
        nested = args.get("fields") or {}
        if not isinstance(nested, Mapping) or set(nested) - {"project", "issuetype", "summary", "priority", "description"}:
            raise ValueError("jira_nested_fields_unsupported")
        for key, value in nested.items():
            if key == "project" and isinstance(value, Mapping):
                if not value or set(value) - {"id", "key", "name"}:
                    raise ValueError("jira_project_arguments_unsupported")
                resolved = [state.resolve_project(ref) for ref in value.values()]
                if any(ref != resolved[0] for ref in resolved):
                    raise ValueError("jira_project_arguments_conflict")
                value = value.get("id") or value.get("key") or value.get("name")
            if key in {"issuetype", "priority"} and isinstance(value, Mapping):
                if set(value) != {"name"}:
                    raise ValueError("jira_named_argument_unsupported")
                value = value["name"]
            if key in values and values[key] is not None:
                same = (state.resolve_project(values[key]) == state.resolve_project(value)
                        if key == "project" else _json(values[key]) == _json(value))
                if not same:
                    raise ValueError("jira_argument_alias_conflict")
            values[key] = _plain(value)
        if values.get("issuetype") is None:
            values["issuetype"] = "Task"
    else:
        if set(args) - {"project", "project_key", "issuetype", "issue_type", "summary", "priority", "description", "format_info"}:
            raise ValueError("jira_create_arguments_unsupported")
        values = {k: _plain(v) for k, v in args.items() if k not in {"project_key", "issue_type"}}
        for key, alias in (("project", "project_key"), ("issuetype", "issue_type")):
            if args.get(key) and args.get(alias):
                same = (state.resolve_project(args[key]) == state.resolve_project(args[alias])
                        if key == "project" else args[key] == args[alias])
                if not same:
                    raise ValueError("jira_argument_alias_conflict")
            values[key] = args.get(key) or args.get(alias) or ""
    return {key: value for key, value in values.items() if value is not None and value != ""}


_READS = frozenset({"search_tools", "jira_project", "jira_issue_key", "jira_fetch_issues", "jira_list_issues"})


def _receipt_binding(source, item):
    """Check optional full native envelope fields when present in this projection."""
    action = item.action
    if action is None:
        raise ValueError("jira_action_capture_unavailable")
    for event in source["tool_execution_events"]:
        receipt = json.loads(event["receipt_json"])
        if receipt.get("invocation_id") != item.invocation_id:
            continue
        if "tool_name" in receipt and receipt["tool_name"] != action.tool_name:
            raise ValueError("jira_native_tool_identity_mismatch")
        if "arguments_json" in receipt:
            arguments = json.loads(receipt["arguments_json"])
            if (not isinstance(arguments, dict) or arguments.get("args") != []
                    or not same_call(action.tool_name, arguments.get("kwargs"), json.loads(action.arguments_json))):
                raise ValueError("jira_native_arguments_mismatch")
    # Native write body_digest covers the whole tool state, not just world.
    # Its integrity belongs to native source admission; do not compare it to
    # the captured world's after_digest or manufacture a replacement digest.


def _transition(item, index, spec):
    if item.origin != "tool_server" or item.action is None:
        raise ValueError("jira_execution_origin_or_action_unavailable")
    if item.before_json is not None and item.after_json is not None and outside_service(
        _operation(item.action)[0], "jira", index.world(item.before_json), index.world(item.after_json)
    ):
        return None
    if (item.evidence_status != "acknowledged" or item.action.status != "returned"
            or item.action.error_json is not None
            or EffectIndex((item,)).serial_chain().status != "qualified"
            or item.before_json is None or item.after_json is None):
        raise ValueError("jira_execution_ack_or_revision_unavailable")
    before, after = index.world(item.before_json), index.world(item.after_json)
    old, new = _service(before), _service(after)
    name, args = _operation(item.action)
    if name in _READS and _json(old) == _json(new):
        return None
    if name not in {"jira_create_issue", "jira_api_create", "jira_update_issue"}:
        raise ValueError("jira_operation_scope_unsupported")
    state = JiraState.model_validate(_plain(old))
    params = _params(name, args, state)
    response = result_payload(item.action)
    if (not isinstance(response, Mapping) or "error" in response
            or "success" in response and response["success"] is not True):
        raise ValueError("jira_response_unavailable")
    if name == "jira_api_create":
        result = response
    else:
        if response.get("success") is not True or type(response.get("count")) is not int or response["count"] != 1:
            raise ValueError("jira_response_unsuccessful")
        results = response.get("results")
        if not isinstance(results, (tuple, list)) or len(results) != 1:
            raise ValueError("jira_response_cardinality_invalid")
        result = results[0]
    if not isinstance(result, Mapping) or not _text(result.get("id")) or not _text(result.get("action_record_id")):
        raise ValueError("jira_response_identity_unavailable")
    identity, audit_id = result["id"], result["action_record_id"]
    ids, known = _ids(old["issues"])
    after_ids, after_known = _ids(new["issues"])
    if not known or not after_known or after_ids.count(identity) != 1:
        raise ValueError("jira_transition_identity_inventory_unavailable")
    current = next(issue for issue in new["issues"] if issue["id"] == identity)
    _canonical_issue(current)
    if identity == audit_id or current.get("last_action_id") != audit_id:
        raise ValueError("jira_issue_audit_link_mismatch")
    if any(key not in result or _json(result[key]) != _json(value) for key, value in current.items()):
        raise ValueError("jira_response_issue_mismatch")
    kind = "status_update" if name == "jira_update_issue" else "create"
    bucket = "update_issue" if kind == "status_update" else "create_issue"
    original_logs = old["actions"].get(bucket, ())
    logs = new["actions"].get(bucket)
    if (not isinstance(original_logs, (tuple, list)) or not isinstance(logs, (tuple, list))
            or len(logs) != len(original_logs) + 1
            or _json(logs[:-1]) != _json(original_logs)):
        raise ValueError("jira_audit_append_unqualified")
    audit = logs[-1]
    if not isinstance(audit, Mapping) or type(audit.get("created_at")) is not str:
        raise ValueError("jira_audit_timestamp_unavailable")
    JiraActionRecord.model_validate(_plain(audit))
    if (audit.get("id") != audit_id or audit.get("action_key") != bucket
            or _json(audit.get("params")) != _json(params)):
        raise ValueError("jira_audit_parameters_mismatch")
    # Validate the complete action record including timestamp; no time ordering
    # is inferred from created_at (receipt revisions establish causal order).
    if any(record.get("id") == audit_id for rows in old["actions"].values() for record in rows):
        raise ValueError("jira_audit_identity_not_new")
    expected = _plain(old)
    expected.setdefault("actions", {}).setdefault(bucket, []).append(_plain(audit))
    prior = None
    if kind == "create":
        if identity in ids or current.get("creation_action_id") != audit_id:
            raise ValueError("jira_birth_not_proven")
        fields = {"project": state.resolve_project(params.get("project")),
                  "issuetype": {"name": params.get("issuetype")},
                  "summary": params.get("summary"), "status": {"name": "To Do"}}
        if "priority" in params:
            fields["priority"] = {"name": params["priority"]}
        if "description" in params:
            fields["description"] = params["description"]
        if _json(fields) != _json(current["fields"]):
            raise ValueError("jira_created_fields_disagree_with_request")
        expected["issues"].append(_plain(current))
    else:
        prior = state.issue(params.get("issueKey"))
        if prior["id"] != identity or ids.count(identity) != 1:
            raise ValueError("jira_update_target_mismatch")
        _canonical_issue(prior)
        status = params.get("transition")
        if not _text(status) or status.isdecimal():
            raise ValueError("jira_status_transition_unsupported")
        wanted = deepcopy(prior)
        wanted["fields"]["status"] = {"name": status}
        wanted["last_action_id"] = audit_id
        if _json(wanted) != _json(current):
            raise ValueError("jira_status_update_fields_mismatch")
        expected["issues"] = [_plain(current) if issue["id"] == identity else issue for issue in expected["issues"]]
    if _json(expected) != _json(new):
        raise ValueError("jira_other_state_changed")
    if spec.project_id is not None and current["fields"]["project"].get("id") != spec.project_id:
        return None
    changed = tuple(sorted(key for key in current["fields"]
        if prior is None or _json(prior["fields"].get(key)) != _json(current["fields"][key])))
    return JiraTransition(invocation_id=item.invocation_id, kind=kind, status="qualified",
        reason="native_jira_issue_ack_result_audit_and_state", issue_id=identity, audit_id=audit_id,
        before_issue_json=_json(prior) if prior is not None else None,
        after_issue_json=_json(current), expected_revision=item.expected_revision,
        applied_revision=item.applied_revision, changed_fields=changed,
        requested_fields=tuple(sorted(set(params) & set(current["fields"]))) if kind == "create" else ("status",))


def capture_jira_evidence(source: Mapping, spec: JiraIssueSource) -> JiraEvidence:
    spec = JiraIssueSource.model_validate(spec.model_dump(mode="python"))
    reasons, transitions = [], []
    unavailable = JiraInventory(status="unavailable", closed=False, reason="jira_history_unavailable")
    initial = unavailable
    task = source.get("task_evidence", {})
    final = _inventory(task.get("final", {}), spec, finalized=task.get("complete") is True)
    try:
        if any(not isinstance(source.get(key), (tuple, list)) for key in ("tool_execution_events", "state_write_receipts")):
            raise ValueError("jira_execution_inventory_unavailable")
        index = EffectIndex(persisted_transitions(dict(source)))
        initial = _initial(source, index, spec)
        for item in index.occurrences:
            try:
                _receipt_binding(source, item)
                fact = _transition(item, index, spec)
                if fact is not None:
                    transitions.append(fact)
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                reasons.append(str(error))
                transitions.append(JiraTransition(invocation_id=item.invocation_id, kind="unknown",
                    origin=item.origin, status="unavailable", reason=str(error)))
        chain = index.serial_chain()
        expected = {item.invocation_id for item in index.occurrences}
        writes = source["state_write_receipts"]
        if len(writes) != len(expected) or {item["write_id"] for item in writes} != expected:
            raise ValueError("jira_ack_inventory_mismatch")
        if (chain.status != "qualified" or chain.revision_interval is None
                or chain.revision_interval[0] != 0 or chain.ordered[-1].after_json != _json(task.get("final"))):
            raise ValueError("jira_history_reconciliation_unavailable")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    if not initial.closed:
        reasons.append(initial.reason)
    if not final.closed:
        reasons.append(final.reason)
    return JiraEvidence(source_digest=_digest(source), selector_digest=_digest(spec.model_dump(mode="json")),
        transitions=tuple(transitions), initial=initial, final=final, complete=not reasons,
        reason=reasons[0] if reasons else "reconciled_native_jira_issue_history")


def validate_jira_evidence(evidence: JiraEvidence, source: Mapping, spec: JiraIssueSource) -> None:
    admitted = JiraEvidence.model_validate(evidence.model_dump(mode="python", warnings=False))
    actual = capture_jira_evidence(source, spec)
    if _json(admitted.model_dump(mode="json")) != _json(actual.model_dump(mode="json")):
        raise ValueError("jira_evidence_source_or_selector_mismatch")
