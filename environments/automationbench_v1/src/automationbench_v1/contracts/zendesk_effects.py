"""Acknowledged native Zendesk status updates, without task policy or credit."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict
from typing import Literal

from automationbench.tools.api.fetch import _url_to_internal_path
from automationbench.tools.api.routes.zendesk import route_zendesk

from ..capture import canonical_json
from ..effect_evidence import world_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation, result_payload
from .base import FrozenModel
from .effects import EffectEvidence, EffectFact
from .handler_scope import outside_service
from .service_hydration import public_collection, public_service_matches


class ZendeskTicketEffectSource(FrozenModel):
    adapter: Literal["zendesk.ticket_updates@1"] = "zendesk.ticket_updates@1"
    kind: Literal["status_update"] = "status_update"


_STATUSES = frozenset({"new", "open", "pending", "hold", "solved", "closed"})


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


def _tickets(world):
    # Sparse public state may omit tickets (or Zendesk): the schema default.
    tickets = public_collection(world, "zendesk", "tickets")
    if not isinstance(tickets, (list, tuple)):
        raise TypeError("zendesk_ticket_collection_unavailable")
    return tickets


def _target(records, identity):
    # Unknown unrelated records do not erase an independently unique native ID.
    matches = [record for record in records if isinstance(record, Mapping) and record.get("id") == identity]
    if len(matches) != 1:
        raise ValueError("zendesk_target_identity_unavailable")
    return matches[0]


def _request(name, args):
    if name == "zendesk_update_ticket":
        identity, body, native = args.get("ticket_id"), args, True
    elif name == "api_fetch":
        url, method = args.get("url"), args.get("method", "GET")
        if type(url) is not str or type(method) is not str or method.upper() not in {"PUT", "PATCH"}:
            raise ValueError("zendesk_operation_scope_unsupported")
        path, router = _url_to_internal_path(url)
        match = re.fullmatch(r"zendesk/api/v2/tickets/([^/]+)", path or "")
        if router is not route_zendesk or match is None:
            raise ValueError("zendesk_operation_scope_unsupported")
        identity, body, native = match[1], args.get("body"), False
        if isinstance(body, str):
            body = json.loads(body)
        if not isinstance(body, Mapping):
            raise ValueError("zendesk_request_body_unavailable")
        body = body.get("ticket", body)
    else:
        raise ValueError("zendesk_operation_scope_unsupported")
    if type(identity) is not str or not identity or not isinstance(body, Mapping):
        raise ValueError("zendesk_requested_identity_unavailable")
    status = body.get("status")
    if type(status) is not str or status not in _STATUSES:
        raise ValueError("zendesk_requested_status_unavailable")
    return identity, status, native


def _update(before, after, name, args, returned):
    identity, status, native = _request(name, args)
    old, new = _tickets(before), _tickets(after)
    if (native and returned.get("success") is False or not native and returned.get("error") == "RecordNotFound"):
        if (any(isinstance(record, Mapping) and record.get("id") == identity for record in old)
                or not _equal(before["zendesk"], after["zendesk"])):
            raise ValueError("zendesk_failed_result_inconsistent")
        if native and (type(returned.get("error")) is not str or not returned["error"]):
            raise ValueError("zendesk_failed_result_error_unavailable")
        return None
    if "error" in returned:
        raise ValueError("zendesk_result_error_inconsistent")
    if set(returned) != ({"success", "ticket", "ticket_id"} if native else {"ticket"}):
        raise ValueError("zendesk_result_shape_unavailable")
    if native and returned.get("success") is not True:
        raise ValueError("zendesk_result_success_unavailable")
    first, last = _target(old, identity), _target(new, identity)
    if type(first.get("status")) is not str or first["status"] not in _STATUSES:
        raise ValueError("zendesk_before_status_unavailable")
    if type(last.get("status")) is not str or last["status"] != status:
        raise ValueError("zendesk_persisted_status_mismatch")
    if not _equal([record for record in old if record is not first], [record for record in new if record is not last]):
        raise ValueError("zendesk_update_rewrote_other_tickets")
    ticket = returned.get("ticket")
    if (not isinstance(ticket, Mapping) or type(ticket.get("id")) is not str or ticket["id"] != identity
            or type(ticket.get("status")) is not str or ticket["status"] != status
            or native and returned.get("ticket_id") != identity):
        raise ValueError("zendesk_returned_target_mismatch")
    # Native display uses `type` for the stored ticket_type and omits comments/channel.
    displayed = {"id", "subject", "description", "status", "priority", "type", "requester_id", "assignee_id",
                 "group_id", "organization_id", "tags", "external_id", "created_at", "updated_at"}
    if set(ticket) != displayed:
        raise ValueError("zendesk_returned_record_shape_unavailable")
    for field, value in ticket.items():
        stored = "ticket_type" if field == "type" else field
        if stored not in last or not _equal(value, last[stored]):
            raise ValueError("zendesk_returned_record_mismatch")
    return {"native_record_id": identity, "before_fields": {"status": first["status"]},
            "after_fields": {"status": last["status"]}, "requested_fields": ["status"],
            "changed_fields": ["status"] if first["status"] != last["status"] else []}


def capture_zendesk_ticket_effects(source: Mapping, spec: ZendeskTicketEffectSource) -> EffectEvidence:
    spec = ZendeskTicketEffectSource.model_validate(spec.model_dump(mode="python", warnings=False))
    facts, reasons = [], []
    source_id, selector_id = _digest(source), _digest(spec.model_dump(mode="json"))
    try:
        if any(not isinstance(source.get(field), (list, tuple)) for field in ("tool_execution_events", "state_write_receipts")):
            raise ValueError("zendesk_execution_inventory_missing")
        index = EffectIndex(world_transitions(dict(source)))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return EffectEvidence(source_id, selector_id, (), False, str(error))
    for occurrence in index.occurrences:
        try:
            if (occurrence.origin != "tool_server" or occurrence.before_json is None or occurrence.after_json is None
                    or occurrence.action is None or EffectIndex((occurrence,)).serial_chain().status != "qualified"):
                raise ValueError("zendesk_occurrence_capture_or_ack_unavailable")
            if outside_service(operation(occurrence.action)[0], "zendesk",
                               index.world(occurrence.before_json), index.world(occurrence.after_json)):
                continue
            if occurrence.action.status != "returned" or occurrence.action.error_json is not None:
                raise ValueError("zendesk_local_action_result_unqualified")
            name, args = operation(occurrence.action)
            returned = result_payload(occurrence.action)
            if returned is None:
                raise ValueError("zendesk_result_unavailable")
            params = _update(index.world(occurrence.before_json), index.world(occurrence.after_json), name, args, returned)
            if params is not None:
                effect_id = _digest([occurrence.invocation_id, params["native_record_id"], occurrence.expected_revision,
                                     occurrence.applied_revision])
                facts.append(EffectFact(effect_id, occurrence.invocation_id, "tool_server", spec.kind,
                    canonical_json(params), "qualified", "acknowledged_zendesk_status_update",
                    occurrence.expected_revision, occurrence.applied_revision))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            reasons.append(str(error))
            facts.append(EffectFact(None, occurrence.invocation_id, "tool_server", spec.kind, None,
                "unavailable", str(error), occurrence.expected_revision, occurrence.applied_revision))
    try:
        task = source["task_evidence"]
        initial, final = task["initial"], task["final"]
        _tickets(initial)
        _tickets(final)
        if task.get("complete") is not True:
            raise ValueError("zendesk_finalization_unavailable")
        expected = {item.invocation_id for item in index.occurrences}
        if len(source["state_write_receipts"]) != len(expected) or {item["write_id"] for item in source["state_write_receipts"]} != expected:
            raise ValueError("zendesk_ack_inventory_mismatch")
        if index.occurrences:
            chain = index.serial_chain()
            if chain.status != "qualified" or chain.revision_interval is None or chain.revision_interval[0] != 0:
                raise ValueError("zendesk_complete_chain_unavailable")
            first, last = chain.ordered[0], chain.ordered[-1]
            if first.before_json is None or last.after_json is None:
                raise ValueError("zendesk_boundary_capture_unavailable")
            if (not public_service_matches(initial, "zendesk", index.world(first.before_json)["zendesk"])
                    or not _equal(final["zendesk"], index.world(last.after_json)["zendesk"])):
                raise ValueError("zendesk_initial_terminal_scope_mismatch")
        elif not public_service_matches(initial, "zendesk", final["zendesk"]):
            raise ValueError("zendesk_unobserved_scope_change")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    return EffectEvidence(source_id, selector_id, tuple(facts), not reasons,
        reasons[0] if reasons else "reconciled_zendesk_status_update_inventory")


def validate_zendesk_ticket_effects(evidence: EffectEvidence, source: Mapping, spec: ZendeskTicketEffectSource) -> None:
    actual = capture_zendesk_ticket_effects(source, spec)
    if canonical_json(asdict(evidence)) != canonical_json(asdict(actual)):
        raise ValueError("zendesk_raw_source_or_projection_mismatch")
