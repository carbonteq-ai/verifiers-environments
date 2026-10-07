"""Native Gmail effects and public sheet records, without semantic reward labels."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from email.utils import getaddresses
from types import MappingProxyType
from typing import Any, Literal

from .capture import CapturedAction
from .effect_index import EffectIndex


def _immutable(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _immutable(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_immutable(item) for item in value)
    return value


def _decode(value: Any) -> Any:
    for _ in range(3):
        if not isinstance(value, str):
            return value
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    return value if not isinstance(value, str) else None


def operation(action: CapturedAction) -> tuple[str, Mapping[str, Any]]:
    args = _decode(action.arguments_json)
    if not isinstance(args, dict):
        raise TypeError("operation_arguments_unresolved")
    name = action.tool_name
    if name == "execute_tool":
        name = args.get("tool_name")
        args = _decode(args.get("arguments"))
        if not isinstance(name, str) or not isinstance(args, dict):
            raise ValueError("nested_operation_unresolved")
    return name, _immutable(args)


def result_payload(action: CapturedAction) -> Mapping[str, Any] | None:
    result = _decode(action.result_json)
    return _immutable(result) if isinstance(result, dict) else None


def sheet_rows(
    world: Mapping[str, Any], spreadsheet_id: str, worksheet_id: str
) -> tuple[Mapping[str, Any], ...]:
    state = world.get("google_sheets")
    if not isinstance(state, Mapping):
        raise TypeError("sheet_service_unavailable")
    records = []
    found = False
    for sheet in state.get("spreadsheets", ()):
        if not isinstance(sheet, Mapping):
            raise TypeError("spreadsheet_schema_unresolved")
        if sheet.get("id", sheet.get("spreadsheet_id")) != spreadsheet_id:
            continue
        for tab in sheet.get("worksheets", ()):
            if tab.get("id", tab.get("worksheet_id")) == worksheet_id:
                found = True
                records.extend(tab.get("rows", ()))
    for tab in state.get("worksheets", ()):
        if tab.get("spreadsheet_id") == spreadsheet_id and tab.get("id") == worksheet_id:
            found = True
    for row in state.get("rows", ()):
        if row.get("spreadsheet_id") == spreadsheet_id and row.get("worksheet_id") == worksheet_id:
            records.append(row)
    if not found:
        raise ValueError("worksheet_population_unavailable")
    keys = []
    for row in records:
        if not isinstance(row, Mapping) or not isinstance(row.get("cells"), Mapping):
            raise TypeError("sheet_row_schema_unresolved")
        key = row.get("row_id")
        if type(key) not in (str, int):
            raise ValueError("sheet_row_identity_unresolved")
        keys.append(key)
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate_scoped_row_identity")
    return tuple(records)


def recipients(message: Mapping[str, Any]) -> tuple[str, ...]:
    result = []
    for field in ("to", "cc", "bcc"):
        values = message.get(field, ())
        if isinstance(values, str):
            values = (values,)
        if not isinstance(values, (tuple, list)):
            raise TypeError("recipient_schema_unresolved")
        for value in values:
            if not isinstance(value, str):
                raise TypeError("recipient_schema_unresolved")
            for _, address in getaddresses([value]):
                if not re.fullmatch(r"[^\s@,;]+@[^\s@,;]+", address):
                    raise ValueError("recipient_address_unresolved")
                result.append(address)
    return tuple(result)


@dataclass(frozen=True)
class NotificationEffect:
    origin: str
    invocation_id: str
    expected_revision: int | None
    applied_revision: int | None
    kind: Literal["send", "draft", "unknown"]
    status: Literal["qualified", "unavailable"]
    reason: str
    message_id: str | None = None
    message: Mapping[str, Any] | None = None
    recipients: tuple[str, ...] = ()


def _kind(name: str, args: Mapping[str, Any]) -> Literal["send", "draft", "unknown"]:
    if name in {"gmail_send_email", "gmail_reply_to_email"}:
        return "send"
    if name in {"gmail_create_draft", "gmail_create_draft_v2", "gmail_create_draft_reply"}:
        return "draft"
    if name == "api_fetch" and str(args.get("method", "")).upper() == "POST":
        url = str(args.get("url", "")).split("?", 1)[0]
        if re.search(r"(?:^|/)gmail/v1/users/[^/]+/(?:messages|drafts)/send$", url):
            return "send"
        if re.search(r"(?:^|/)gmail/v1/users/[^/]+/drafts$", url):
            return "draft"
    return "unknown"


def notifications(index: EffectIndex) -> tuple[NotificationEffect, ...]:
    """Join qualified operations, result IDs and persisted native message effects.

    An unknown capture can affect notification coverage. Reading or changing a
    message label does not establish delivery. Each real send retains its own
    invocation, even if its content duplicates another send.
    """
    effects = []
    for item in index.occurrences:
        kind: Literal["send", "draft", "unknown"] = "unknown"
        message = None
        identity = None
        try:
            if item.action is not None:
                name, args = operation(item.action)
                kind = _kind(name, args)
            if item.before_json is not None and item.after_json is not None:
                before = index.collection(item.before_json, "gmail", "messages")
                after = index.collection(item.after_json, "gmail", "messages")
                for records in (before, after):
                    identities = [record.get("id") for record in records]
                    if any(not isinstance(value, str) or not value for value in identities) or len(
                        set(identities)
                    ) != len(identities):
                        raise ValueError("message_population_identity_unresolved")

                def relevant(records):
                    return {
                        record.get("id"): (
                            record.get("subject"),
                            record.get("body_plain", record.get("body")),
                            record.get("body_html"),
                            tuple(record.get("to", ())),
                            tuple(record.get("cc", ())),
                            tuple(record.get("bcc", ())),
                            tuple(record.get("label_ids", record.get("labels", ()))),
                        )
                        for record in records
                    }

                if kind == "unknown" and relevant(before) == relevant(after):
                    continue
            else:
                raise ValueError("notification_capture_unavailable")
            if kind == "unknown":
                raise ValueError("notification_operation_unqualified")
            if item.evidence_status != "acknowledged" or item.action is None:
                raise ValueError("notification_acknowledgement_unavailable")
            if item.action.status != "returned" or item.action.error_json is not None:
                raise ValueError("notification_operation_failed")
            result = result_payload(item.action)
            if result is None or "error" in result or result.get("success") is False:
                raise ValueError("notification_result_unqualified")
            wrapped = result.get("message", {})
            identity = wrapped.get("id") if isinstance(wrapped, Mapping) else None
            if identity is None:
                identity = result.get("id") if kind == "send" else None
            if identity is None and kind == "draft":
                draft = result.get("draft", {})
                wrapped = draft.get("message", {}) if isinstance(draft, Mapping) else {}
                identity = wrapped.get("id") if isinstance(wrapped, Mapping) else None
            if not isinstance(identity, str) or not identity:
                raise ValueError("notification_result_identity_unresolved")
            matches = [record for record in after if record.get("id") == identity]
            previous = [record for record in before if record.get("id") == identity]
            if len(matches) != 1 or len(previous) > 1:
                raise ValueError("notification_effect_identity_unresolved")
            message = matches[0]
            if previous and previous[0] == message:
                raise ValueError("notification_effect_missing")
            if kind == "send" and (
                "SENT" not in message.get("label_ids", ())
                or "DRAFT" in message.get("label_ids", ())
            ):
                raise ValueError("notification_sent_state_unqualified")
            if kind == "draft":
                drafts = index.collection(item.after_json, "gmail", "drafts")
                if sum(draft.get("message_id") == identity for draft in drafts) != 1:
                    raise ValueError("notification_draft_wrapper_unqualified")
            addresses = recipients(message)
            if not addresses:
                raise ValueError("notification_recipient_unavailable")
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            effects.append(
                NotificationEffect(
                    item.origin,
                    item.invocation_id,
                    item.expected_revision,
                    item.applied_revision,
                    kind,
                    "unavailable",
                    str(error),
                    identity,
                    message,
                )
            )
        else:
            effects.append(
                NotificationEffect(
                    item.origin,
                    item.invocation_id,
                    item.expected_revision,
                    item.applied_revision,
                    kind,
                    "qualified",
                    "native_operation_and_persisted_effect",
                    identity,
                    message,
                    addresses,
                )
            )
    return tuple(effects)
