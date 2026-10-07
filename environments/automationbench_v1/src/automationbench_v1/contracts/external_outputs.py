"""Audited external authored fields, separate from summary-policy meaning."""

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import StrictBool, StrictStr
from verifiers.v1.assessments import SourceSnapshot

from automationbench.schema.gmail import Message as GmailMessage
from automationbench.schema.slack import Channel, Message, User
from automationbench.schema.zendesk import ZendeskComment, ZendeskTicket
from automationbench.tools.zapier.gmail.message import (
    _sent_summary,
    gmail_find_email,
    gmail_get_email_by_id,
    gmail_list_emails,
    gmail_send_email,
)
from automationbench.tools.zapier.salesforce.contact import salesforce_contact_update
from automationbench.tools.zapier.salesforce.record import salesforce_find_records
from automationbench.tools.zapier.slack.messaging import slack_send_direct_message
from automationbench.tools.zapier.slack.users import slack_find_user_by_name
from automationbench.tools.zapier.zendesk.tickets import (
    zendesk_find_ticket,
    zendesk_update_ticket,
)

from ..capture import canonical_json
from ..tools import AutomationBenchToolset, _registry
from .base import FrozenModel
from .invocation_inventory import InvocationEntry, capture_invocation_inventory
from .slack_effects import _collection, _send, _unique, _user
from .tables import Digest


class ExternalOutputSource(FrozenModel):
    adapter: Literal["external.outputs@1"] = "external.outputs@1"
    kind: Literal["authored_text"] = "authored_text"


class ExternalOutputFact(FrozenModel):
    output_id: StrictStr
    invocation_id: StrictStr
    surface: Literal["record_field", "message_field"] = "record_field"
    service: StrictStr
    collection: StrictStr
    record_id: StrictStr
    field: StrictStr
    text: StrictStr


class ActionRelation(FrozenModel):
    invocation_id: StrictStr
    service: StrictStr
    collection: StrictStr
    record_id: StrictStr
    field: StrictStr
    value_json: StrictStr
    changed: StrictBool


class InvocationOutputCoverage(FrozenModel):
    invocation_id: StrictStr
    operation: StrictStr | None
    disposition: Literal["no_authored_fields", "authored_fields", "unavailable"]
    reason: StrictStr


class ExternalOutputEvidence(FrozenModel):
    source_digest: Digest
    selector_digest: Digest
    invocation_coverage: tuple[InvocationOutputCoverage, ...] = ()
    text_records: tuple[ExternalOutputFact, ...] = ()
    action_relations: tuple[ActionRelation, ...] = ()
    status: Literal["qualified", "partial", "unavailable"]
    closed: StrictBool
    reason: StrictStr


_HANDLERS = {
    "gmail_find_email": gmail_find_email,
    "gmail_list_emails": gmail_list_emails,
    "gmail_get_email_by_id": gmail_get_email_by_id,
    "salesforce_find_records": salesforce_find_records,
    "salesforce_contact_update": salesforce_contact_update,
    "slack_send_direct_message": slack_send_direct_message,
    "slack_find_user_by_name": slack_find_user_by_name,
    "gmail_send_email": gmail_send_email,
    "zendesk_find_ticket": zendesk_find_ticket,
    "zendesk_update_ticket": zendesk_update_ticket,
}
_CONTACT_FIELDS = {"assistant_name": "AssistantName", "assistant_email": "AssistantEmail"}
_SEARCH_HANDLER = AutomationBenchToolset.search_tools
_EXECUTE_HANDLER = AutomationBenchToolset.execute_tool


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _same(left, right):
    return canonical_json(left) == canonical_json(right)


def _decoded(text):
    if type(text) is not str:
        raise ValueError("external_output_material_missing")
    return json.loads(text)


def _result(entry, *, allow_business_failure=False):
    value = _decoded(entry.result_json)
    if type(value) is str:
        value = json.loads(value)
    if not isinstance(value, (dict, list)):
        raise TypeError("external_output_result_unavailable")
    if (
        not allow_business_failure
        and isinstance(value, dict)
        and (value.get("error") is not None or value.get("success") is False)
    ):
        raise ValueError("external_output_business_result_failed")
    return value


def _contact(entry, before, after, params, result):
    if not isinstance(params, dict) or set(params) - {"id", *_CONTACT_FIELDS}:
        raise ValueError("external_output_contact_fields_unsupported")
    identity = params.get("id")
    if type(identity) is not str or not identity:
        raise ValueError("external_output_contact_identity_unavailable")
    submitted = {
        key: value for key, value in params.items() if key in _CONTACT_FIELDS and value is not None
    }
    if not submitted or any(type(value) is not str for value in submitted.values()):
        raise ValueError("external_output_contact_values_unavailable")
    old = before["salesforce"]["contacts"]
    new = after["salesforce"]["contacts"]
    if not isinstance(old, list) or not isinstance(new, list):
        raise TypeError("external_output_contact_collection_unavailable")
    old_matches = [
        (index, item)
        for index, item in enumerate(old)
        if isinstance(item, dict) and item.get("id") == identity
    ]
    new_matches = [
        (index, item)
        for index, item in enumerate(new)
        if isinstance(item, dict) and item.get("id") == identity
    ]
    if len(old_matches) != 1 or len(new_matches) != 1 or old_matches[0][0] != new_matches[0][0]:
        raise ValueError("external_output_original_contact_unavailable")
    index, initial = old_matches[0]
    final = new_matches[0][1]
    if (
        not isinstance(result, dict)
        or result.get("success") is not True
        or not isinstance(result.get("contact"), dict)
        or result["contact"].get("Id") != identity
    ):
        raise ValueError("external_output_contact_response_unavailable")
    display = result["contact"]
    for field, value in submitted.items():
        if (
            field not in initial
            or final.get(field) != value
            or display.get(_CONTACT_FIELDS[field]) != value
        ):
            raise ValueError("external_output_contact_field_disagreement")
    expected = json.loads(canonical_json(before))
    expected_record = expected["salesforce"]["contacts"][index]
    expected_record.update(submitted)
    stamp = final.get("last_modified_date")
    if type(stamp) is not str or datetime.fromisoformat(stamp).tzinfo is None:
        raise ValueError("external_output_contact_timestamp_unavailable")
    expected_record["last_modified_date"] = stamp
    if not _same(expected, after):
        raise ValueError("external_output_contact_unexplained_world_change")
    facts, relations = [], []
    for field, value in sorted(submitted.items()):
        facts.append(
            ExternalOutputFact(
                output_id=f"{entry.invocation_id}:contact:{identity}:{field}",
                invocation_id=entry.invocation_id,
                service="salesforce",
                collection="contacts",
                record_id=identity,
                field=field,
                text=value,
            )
        )
        relations.append(
            ActionRelation(
                invocation_id=entry.invocation_id,
                service="salesforce",
                collection="contacts",
                record_id=identity,
                field=field,
                value_json=canonical_json(value),
                changed=not _same(initial[field], value),
            )
        )
    return facts, relations


def _slack_lookup(before, after, params, result):
    """Installed name lookup is a read, including its known not-found branch."""
    if not isinstance(params, dict) or set(params) - {"full_name", "name", "query"}:
        raise ValueError("external_output_slack_lookup_arguments_unsupported")
    if any(value is not None and type(value) is not str for value in params.values()):
        raise ValueError("external_output_slack_lookup_argument_type")
    if not _same(before, after):
        raise ValueError("external_output_slack_lookup_changed_world")
    name = params.get("full_name") or params.get("name") or params.get("query") or ""
    users = _collection(before, "users")
    matches = (
        _unique(
            users,
            (
                lambda user: type(user.get("name")) is str and user["name"].lower() == name.lower(),
                lambda user: type(user.get("name")) is str and name.lower() in user["name"].lower(),
            ),
        )
        if name
        else None
    )
    expected = {"success": False, "error": f"User with name '{name}' not found"}
    if matches is not None:
        user = User.model_validate_json(canonical_json(matches), strict=True)
        if not _same(user.model_dump(mode="json"), matches):
            raise ValueError("external_output_slack_lookup_user_schema")
        expected = {"success": True, "user": user.to_display_dict()}
    if not _same(result, expected):
        raise ValueError("external_output_slack_lookup_result_mismatch")
    return [], [], "no_authored_fields", "external_output_audited_slack_lookup"


def _slack_dm(entry, before, after, params, result):
    """Preserve known message fields even when an independent field is unresolved."""
    if not isinstance(params, dict) or set(params) - {"user", "text", "as_bot", "username"}:
        raise ValueError("external_output_slack_dm_arguments_unsupported")
    if (
        type(params.get("user")) is not str
        or type(params.get("text")) is not str
        or type(params.get("as_bot", True)) is not bool
        or params.get("username") is not None
        and type(params["username"]) is not str
        or not isinstance(result, dict)
    ):
        raise ValueError("external_output_slack_dm_argument_type")
    user = _user(_collection(before, "users"), params["user"])
    if result.get("success") is False:
        # The only business failure in this exact installed DM handler occurs
        # before channel/message creation when recipient lookup finds nothing.
        expected = {"success": False, "error": f"User '{params['user']}' not found"}
        if user is not None or not _same(before, after) or not _same(result, expected):
            raise ValueError("external_output_slack_dm_failure_unqualified")
        return [], [], "no_authored_fields", "external_output_audited_slack_dm_not_found"
    qualified = _send(before, after, "slack_send_direct_message", params, result)
    if qualified is None or user is None:
        raise ValueError("external_output_slack_dm_send_unavailable")
    identity = canonical_json([qualified["channel_id"], qualified["message_ts"]])
    facts, relations = [], []

    def relation(field, value):
        relations.append(
            ActionRelation(
                invocation_id=entry.invocation_id,
                service="slack",
                collection="messages",
                record_id=identity,
                field=field,
                value_json=canonical_json(value),
                changed=True,
            )
        )

    def authored(field, value):
        facts.append(
            ExternalOutputFact(
                output_id=canonical_json([entry.invocation_id, "slack", identity, field]),
                invocation_id=entry.invocation_id,
                surface="message_field",
                service="slack",
                collection="messages",
                record_id=identity,
                field=field,
                text=value,
            )
        )
        relation(field, value)

    authored("text", qualified["text"])
    for field in ("channel_id", "recipient_user_id", "sender_user_id"):
        relation(field, qualified[field])
    # The shared send proof establishes text and routing. Qualify remaining
    # fields and complete footprint separately; failure cannot erase that text.
    try:
        raw = after["slack"]["messages"][-1]
        message = Message.model_validate_json(canonical_json(raw), strict=True)
        bot = params.get("as_bot", True)
        bot_name = (params.get("username") or "Zapier") if bot else None
        if message.bot_name != bot_name:
            raise ValueError("external_output_slack_dm_bot_name_mismatch")
        if not _same(result["message"], message.to_display_dict()):
            raise ValueError("external_output_slack_dm_display_mismatch")
        if bot and params.get("username"):
            authored("bot_name", params["username"])
        if message.created_at is None:
            raise ValueError("external_output_slack_dm_timestamp_unavailable")
        expected_message = Message(
            ts=message.ts,
            channel_id=qualified["channel_id"],
            user_id=qualified["sender_user_id"],
            text=params["text"],
            is_bot=bot,
            bot_name=bot_name,
            created_at=message.created_at,
        )
        if not _same(expected_message.model_dump(mode="json"), raw):
            raise ValueError("external_output_slack_dm_message_footprint_mismatch")
        expected = json.loads(canonical_json(before))
        expected["slack"]["messages"].append(raw)
        if len(after["slack"]["channels"]) == len(before["slack"]["channels"]) + 1:
            channel = Channel(
                id=qualified["channel_id"],
                name="dm-" + str(user.get("username")),
                is_private=True,
                channel_type="dm",
                member_ids=[user["id"], "UAUTHUSER"],
            )
            expected["slack"]["channels"].append(channel.model_dump(mode="json"))
        if not _same(expected, after):
            raise ValueError("external_output_slack_dm_unexplained_world_change")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return facts, relations, "unavailable", str(error)
    return facts, relations, "authored_fields", "external_output_audited_slack_dm"


def _records(world, service, collection):
    rows = world[service][collection]
    if not isinstance(rows, list):
        raise TypeError("external_output_record_collection_missing")
    ids = [r.get("id") if isinstance(r, dict) else None for r in rows]
    if any(type(i) is not str or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("external_output_record_identity_ambiguous")
    return rows


def _field(entry, service, collection, identity, field, value, *, changed=True, text=True):
    relation = ActionRelation(
        invocation_id=entry.invocation_id,
        service=service,
        collection=collection,
        record_id=identity,
        field=field,
        value_json=canonical_json(value),
        changed=changed,
    )
    fact = (
        ExternalOutputFact(
            output_id=canonical_json([entry.invocation_id, service, collection, identity, field]),
            invocation_id=entry.invocation_id,
            surface="message_field" if service == "gmail" else "record_field",
            service=service,
            collection=collection,
            record_id=identity,
            field=field,
            text=value,
        )
        if text
        else None
    )
    return fact, relation


def _gmail_send(entry, before, after, params, result):
    """Exact installed send transforms; no normalized-away authored headers."""
    allowed = {
        "to",
        "subject",
        "body",
        "cc",
        "bcc",
        "from_",
        "from_name",
        "reply_to",
        "body_type",
        "signature",
        "label_ids",
        "file",
    }
    if not isinstance(params, dict) or set(params) - allowed:
        raise ValueError("external_output_gmail_arguments_unsupported")
    if any(type(params.get(k)) is not str for k in ("to", "subject", "body")) or any(
        v is not None and type(v) is not str for v in params.values()
    ):
        raise ValueError("external_output_gmail_argument_type")
    old, new = _records(before, "gmail", "messages"), _records(after, "gmail", "messages")
    if (
        len(new) != len(old) + 1
        or not _same(new[:-1], old)
        or new[-1]["id"] in {r["id"] for r in old}
    ):
        raise ValueError("external_output_gmail_fresh_append_unavailable")
    raw = new[-1]
    identity = raw["id"]
    if type(raw.get("thread_id")) is not str or not raw["thread_id"]:
        raise ValueError("external_output_gmail_thread_unavailable")
    # The acknowledgement omits body; exact request and persisted content bind it.
    summary = {
        k: raw.get(k) for k in ("id", "thread_id", "subject", "to", "cc", "bcc", "label_ids")
    }
    summary = {k: v for k, v in summary.items() if v not in (None, [])}
    if not _same(result, {"success": True, "message": summary}):
        raise ValueError("external_output_gmail_result_mismatch")
    split = lambda value: [v.strip() for v in (value or "").split(",") if v.strip()]
    body = params["body"] + ("\n\n" + params["signature"] if params.get("signature") else "")
    html = params.get("body_type") == "html"
    body_field = "body_html" if html else "body_plain"
    facts, relations, reasons = [], [], []
    values = {
        "subject": params["subject"],
        body_field: body,
        "to": split(params["to"]),
        "cc": split(params.get("cc")),
        "bcc": split(params.get("bcc")),
        "from_": params.get("from_") or "user@gmail.com",
        "from_name": params.get("from_name"),
        "reply_to": params.get("reply_to"),
        "label_ids": ["SENT", *split(params.get("label_ids"))],
    }
    for field, value in values.items():
        if field not in raw or not _same(raw[field], value):
            reasons.append("external_output_gmail_field_mismatch:" + field)
            continue
        # Generated defaults have a relation, but are not agent-authored text.
        authored = field not in {"from_", "from_name", "reply_to"} or (
            params.get(field) is not None and (field != "from_" or bool(params[field]))
        )
        if isinstance(value, list):
            relations.append(
                _field(entry, "gmail", "messages", identity, field, value, text=False)[1]
            )
            for index, item in enumerate(value):
                if field == "label_ids" and index == 0:
                    continue
                fact, relation = _field(
                    entry, "gmail", "messages", identity, f"{field}.{index}", item
                )
                facts.append(fact)
                relations.append(relation)
        else:
            fact, relation = _field(
                entry,
                "gmail",
                "messages",
                identity,
                field,
                value,
                text=authored and value is not None,
            )
            if fact is not None:
                facts.append(fact)
            relations.append(relation)
    relations.append(
        _field(entry, "gmail", "messages", identity, "thread_id", raw["thread_id"], text=False)[1]
    )
    try:
        if any(type(raw.get(field)) is not int for field in ("date", "internal_date")):
            raise ValueError("external_output_gmail_timestamp_type")
        message = GmailMessage.model_validate_json(canonical_json(raw), strict=True)
        expected_message = GmailMessage(
            id=identity,
            thread_id=raw["thread_id"],
            from_=values["from_"],
            from_name=values["from_name"],
            to=values["to"],
            cc=values["cc"],
            bcc=values["bcc"],
            subject=values["subject"],
            body_plain=None if html else body,
            body_html=body if html else f"<html><body>{body}</body></html>",
            snippet=params["body"][:100],
            label_ids=values["label_ids"],
            is_read=True,
            reply_to=values["reply_to"],
            in_reply_to=None,
            has_attachments=params.get("file") is not None,
            date=raw["date"],
            internal_date=raw["internal_date"],
        )
        if not _same(expected_message.model_dump(mode="json"), raw) or not _same(
            result, {"success": True, "message": _sent_summary(message)}
        ):
            raise ValueError("external_output_gmail_message_footprint_mismatch")
        expected = json.loads(canonical_json(before))
        expected["gmail"]["messages"].append(raw)
        if not _same(expected, after):
            raise ValueError("external_output_gmail_unexplained_world_change")
        if params.get("file") is not None:
            raise ValueError("external_output_gmail_attachment_content_unavailable")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    return (
        facts,
        relations,
        "unavailable" if reasons else "authored_fields",
        reasons[0] if reasons else "external_output_audited_gmail_send",
    )


def _zendesk(entry, before, after, params, result):
    lookup = entry.operation == "zendesk_find_ticket"
    allowed = (
        {"ticket_id", "query"} if lookup else {"ticket_id", "status", "comment", "comment_public"}
    )
    if not isinstance(params, dict) or set(params) - allowed:
        raise ValueError("external_output_zendesk_arguments_unsupported")
    if any(
        v is not None and type(v) is not str for k, v in params.items() if k != "comment_public"
    ):
        raise ValueError("external_output_zendesk_argument_type")
    old = _records(before, "zendesk", "tickets")
    identity = params.get("ticket_id")
    if lookup:
        if not _same(before, after):
            raise ValueError("external_output_zendesk_read_changed_world")
        selected = (
            [r for r in old if r["id"] == identity]
            if identity
            else [
                r
                for r in old
                if params.get("query")
                and (
                    params["query"].lower() in r["subject"].lower()
                    or params["query"].lower() in (r.get("description") or "").lower()
                )
            ]
        )
        models = [
            ZendeskTicket.model_validate_json(canonical_json(r), strict=True) for r in selected
        ]
        if any(
            not _same(m.model_dump(mode="json"), r) for m, r in zip(models, selected, strict=True)
        ):
            raise ValueError("external_output_zendesk_read_schema")
        expected = {
            "success": True,
            "found": bool(selected),
            "tickets": [m.to_display_dict() for m in models],
            "count": len(selected),
        }
        if not _same(result, expected):
            raise ValueError("external_output_zendesk_read_result_mismatch")
        return [], [], "no_authored_fields", "external_output_audited_zendesk_find"
    if (
        type(identity) is not str
        or not identity
        or type(params.get("comment_public", True)) is not bool
    ):
        raise ValueError("external_output_zendesk_update_argument_type")
    status = params.get("status")
    if status is not None and status not in {"new", "open", "pending", "hold", "solved", "closed"}:
        raise ValueError("external_output_zendesk_status_unsupported")
    matches = [(i, r) for i, r in enumerate(old) if r["id"] == identity]
    if not matches:
        if not _same(before, after) or not _same(
            result, {"success": False, "error": f"Ticket with ID {identity} not found"}
        ):
            raise ValueError("external_output_zendesk_failure_unqualified")
        return [], [], "no_authored_fields", "external_output_audited_zendesk_not_found"
    index, initial = matches[0]
    admitted_initial = ZendeskTicket.model_validate_json(canonical_json(initial), strict=True)
    if not _same(admitted_initial.model_dump(mode="json"), initial):
        raise ValueError("external_output_zendesk_initial_schema")
    new = _records(after, "zendesk", "tickets")
    if len(new) != len(old) or new[index]["id"] != identity:
        raise ValueError("external_output_zendesk_target_changed")
    final = new[index]
    ticket = ZendeskTicket.model_validate_json(canonical_json(final), strict=True)
    if not _same(ticket.model_dump(mode="json"), final) or not _same(
        result, {"success": True, "ticket": ticket.to_display_dict(), "ticket_id": identity}
    ):
        raise ValueError("external_output_zendesk_update_result_mismatch")
    facts, relations, reasons = [], [], []
    if status is not None:
        if final["status"] != status:
            reasons.append("external_output_zendesk_status_mismatch")
        else:
            relations.append(
                _field(
                    entry,
                    "zendesk",
                    "tickets",
                    identity,
                    "status",
                    status,
                    changed=initial["status"] != status,
                    text=False,
                )[1]
            )
    comment = params.get("comment")
    expected = json.loads(canonical_json(before))
    target = expected["zendesk"]["tickets"][index]
    if status:
        target["status"] = status
    target["updated_at"] = final["updated_at"]
    if comment:
        comments = _records({"zendesk": {"comments": initial["comments"]}}, "zendesk", "comments")
        appended = _records({"zendesk": {"comments": final["comments"]}}, "zendesk", "comments")
        if (
            len(appended) != len(comments) + 1
            or not _same(appended[:-1], comments)
            or appended[-1]["id"] in {c["id"] for c in comments}
        ):
            raise ValueError("external_output_zendesk_comment_append_unavailable")
        raw = appended[-1]
        canonical = ZendeskComment(
            id=raw["id"],
            body=comment,
            public=params.get("comment_public", True),
            created_at=raw["created_at"],
        )
        if not _same(canonical.model_dump(mode="json"), raw):
            raise ValueError("external_output_zendesk_comment_mismatch")
        comment_id = canonical_json([identity, raw["id"]])
        fact, relation = _field(entry, "zendesk", "comments", comment_id, "body", comment)
        facts.append(fact)
        relations.extend(
            [
                relation,
                _field(
                    entry, "zendesk", "comments", comment_id, "public", raw["public"], text=False
                )[1],
                _field(entry, "zendesk", "comments", comment_id, "ticket_id", identity, text=False)[
                    1
                ],
            ]
        )
        target["comments"].append(raw)
    if not _same(expected, after):
        reasons.append("external_output_zendesk_unexplained_world_change")
    return (
        facts,
        relations,
        "unavailable" if reasons else "authored_fields" if facts else "no_authored_fields",
        reasons[0] if reasons else "external_output_audited_zendesk_update",
    )


def _classify(entry: InvocationEntry):
    if entry.status != "qualified":
        raise ValueError(entry.reason)
    before, after = _decoded(entry.before_json), _decoded(entry.after_json)
    params, result = (
        _decoded(entry.operation_arguments_json),
        _result(
            entry,
            allow_business_failure=entry.operation
            in {"slack_send_direct_message", "slack_find_user_by_name", "zendesk_update_ticket"},
        ),
    )
    if entry.outer_tool == "search_tools":
        if AutomationBenchToolset.search_tools is not _SEARCH_HANDLER:
            raise ValueError("external_output_installed_handler_mismatch")
        if not isinstance(params, dict) or set(params) != {"query", "top_k"}:
            raise ValueError("external_output_search_arguments_unavailable")
        if (
            type(params["query"]) is not str
            or type(params["top_k"]) is not int
            or not isinstance(result, list)
        ):
            raise ValueError("external_output_search_result_unavailable")
        if not _same(before, after):
            raise ValueError("external_output_discovery_changed_world")
        return [], [], "no_authored_fields", "external_output_audited_operation"
    if entry.outer_tool != "execute_tool" or entry.operation not in _HANDLERS:
        raise ValueError("external_output_operation_unsupported")
    if AutomationBenchToolset.execute_tool is not _EXECUTE_HANDLER:
        raise ValueError("external_output_installed_handler_mismatch")
    if _registry()._tool_map.get(entry.operation) is not _HANDLERS[entry.operation]:
        raise ValueError("external_output_installed_handler_mismatch")
    if entry.operation == "slack_send_direct_message":
        return _slack_dm(entry, before, after, params, result)
    if entry.operation == "slack_find_user_by_name":
        return _slack_lookup(before, after, params, result)
    if entry.operation == "gmail_send_email":
        return _gmail_send(entry, before, after, params, result)
    if entry.operation in {"zendesk_find_ticket", "zendesk_update_ticket"}:
        return _zendesk(entry, before, after, params, result)
    if entry.operation == "salesforce_contact_update":
        facts, relations = _contact(entry, before, after, params, result)
        return facts, relations, "authored_fields", "external_output_audited_operation"
    if not isinstance(params, dict) or not _same(before, after):
        raise ValueError("external_output_read_changed_world")
    return [], [], "no_authored_fields", "external_output_audited_operation"


def capture_external_outputs(
    source: Mapping, spec: ExternalOutputSource, *, native_source: SourceSnapshot | None = None
) -> ExternalOutputEvidence:
    spec = ExternalOutputSource.model_validate(spec.model_dump(mode="python", warnings=False))
    inventory = capture_invocation_inventory(source, native_source=native_source)
    coverage, records, relations, reasons = [], [], [], []
    if not inventory.closed:
        reasons.append(inventory.reason)
    for entry in inventory.entries:
        try:
            text, acts, disposition, reason = _classify(entry)
            records.extend(text)
            relations.extend(acts)
            if disposition == "unavailable":
                reasons.append(reason)
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            disposition, reason = "unavailable", str(error)
            reasons.append(reason)
        coverage.append(
            InvocationOutputCoverage(
                invocation_id=entry.invocation_id,
                operation=entry.operation,
                disposition=disposition,
                reason=reason,
            )
        )
    return ExternalOutputEvidence(
        source_digest=_digest(source),
        selector_digest=_digest(spec.model_dump(mode="json")),
        invocation_coverage=tuple(coverage),
        text_records=tuple(records),
        action_relations=tuple(relations),
        closed=not reasons,
        status="qualified" if not reasons else "partial" if records else "unavailable",
        reason=reasons[0] if reasons else "external_output_inventory_closed",
    )


def validate_external_outputs(
    evidence: ExternalOutputEvidence,
    source: Mapping,
    spec: ExternalOutputSource,
    *,
    native_source: SourceSnapshot | None = None,
) -> None:
    admitted = ExternalOutputEvidence.model_validate(
        evidence.model_dump(mode="python", warnings=False)
    )
    actual = capture_external_outputs(source, spec, native_source=native_source)
    if canonical_json(admitted.model_dump(mode="json")) != canonical_json(
        actual.model_dump(mode="json")
    ):
        raise ValueError("external_output_raw_source_or_projection_mismatch")
