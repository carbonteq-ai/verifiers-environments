"""Acknowledged Gmail simulator sends, independent of content policy or reward."""

import hashlib
import json
import re
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Literal

from ..capture import canonical_json
from ..effect_evidence import persisted_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import notifications, operation, recipients, result_payload
from .base import FrozenModel
from .effects import EffectEvidence, EffectFact
from .handler_scope import _plain, handler_footprints, outside_service
from .service_hydration import public_service_matches

# Gmail-touching handlers audited as read-only: they filter or return stored
# messages without mutating them. Any other handler closes send scope only when
# its static footprint (handler_scope) excludes Gmail.
_GMAIL_READS = frozenset({"gmail_find_email", "gmail_get_email_by_id", "gmail_list_emails"})
# Audited Gmail handlers that only file existing messages (labels, read and
# star flags, archive/trash labels) or define a label; never a send. Each
# occurrence must also be observed to change nothing else (_filing_only).
_GMAIL_FILING = frozenset({
    "gmail_add_label_to_email", "gmail_remove_label_from_email", "gmail_remove_thread_label",
    "gmail_create_label", "gmail_mark_as_read", "gmail_mark_as_unread", "gmail_archive_email",
    "gmail_trash_email", "gmail_star_messages",
})
_FILING_FIELDS = frozenset({"label_ids", "is_read", "is_starred"})


class NotificationEffectSource(FrozenModel):
    adapter: Literal["gmail.messages@1"] = "gmail.messages@1"
    kind: Literal["send"] = "send"


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _filing_only(name, before, after):
    """A filing handler whose footprint is Gmail alone and whose observed change
    is limited to existing messages' labels/read/star flags and label definitions."""
    footprint = handler_footprints().get(name) if type(name) is str else None
    if name not in _GMAIL_FILING or footprint is None or not footprint <= {"gmail"}:
        return False
    old, new = before.get("gmail"), after.get("gmail")
    if not isinstance(old, Mapping) or not isinstance(new, Mapping) or set(old) != set(new):
        return False
    if any(canonical_json(_plain(old[key])) != canonical_json(_plain(new[key]))
           for key in old if key not in {"messages", "labels"}):
        return False
    first, second = _messages(before), _messages(after)
    if [record["id"] for record in first] != [record["id"] for record in second]:
        return False

    def unfiled(record):
        return canonical_json({key: _plain(value) for key, value in record.items() if key not in _FILING_FIELDS})

    def delivery_labels(record):
        labels = record.get("label_ids")
        return {label for label in labels if label in {"SENT", "DRAFT"}} if isinstance(labels, (list, tuple)) else None

    # Relabelling a draft as SENT (or dropping DRAFT) imitates delivery: keep it
    # unsupported rather than decide it is not a send.
    return all(isinstance(a, Mapping) and isinstance(b, Mapping) and set(a) == set(b) and unfiled(a) == unfiled(b)
               and delivery_labels(a) is not None and delivery_labels(a) == delivery_labels(b)
               for a, b in zip(first, second, strict=True))


def _messages(world):
    service = world.get("gmail")
    if not isinstance(service, Mapping) or not isinstance(service.get("messages"), (list, tuple)):
        raise TypeError("gmail_message_population_unavailable")
    records = service["messages"]
    ids = [record.get("id") if isinstance(record, Mapping) else None for record in records]
    if any(type(identity) is not str or not identity for identity in ids) or len(set(ids)) != len(
        ids
    ):
        raise ValueError("gmail_message_population_identity_unresolved")
    return records


def _initial_gmail_matches(initial, before_json):
    """Public initial Gmail reconciles with the native BEFORE Gmail service."""
    if before_json is None:
        return False
    if canonical_json(initial) == before_json:
        return True
    before = json.loads(before_json)
    return isinstance(before, Mapping) and public_service_matches(initial, "gmail", before.get("gmail"))


class _TextExtractor(HTMLParser):
    _BLOCKS = frozenset({"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "table", "ul", "ol"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip:
            self.skip -= 1
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_text(value):
    """Visible text of an HTML body, or None when unavailable."""
    if type(value) is not str:
        return None
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


def _addresses(value):
    return recipients({"to": value if value is not None else ()})


def _requested_message(name, args, before):
    if name == "api_fetch":
        if str(args.get("method", "")).upper() != "POST" or not re.fullmatch(
            r"(?:https?://[^/]+)?/?gmail/v1/users/[^/]+/drafts/send",
            str(args.get("url", "")).split("?", 1)[0],
        ):
            raise ValueError("gmail_api_send_payload_unsupported")
        body = args.get("body")
        if not isinstance(body, Mapping) or set(body) != {"id"}:
            raise ValueError("gmail_draft_send_identity_unavailable")
        drafts = before.get("gmail", {}).get("drafts")
        if not isinstance(drafts, (list, tuple)):
            raise ValueError("gmail_draft_population_unavailable")
        matching = [
            draft
            for draft in drafts
            if isinstance(draft, Mapping) and draft.get("id") == body["id"]
        ]
        if len(matching) != 1:
            raise ValueError("gmail_draft_identity_unresolved")
        originals = [
            message
            for message in _messages(before)
            if message["id"] == matching[0].get("message_id")
        ]
        if len(originals) != 1:
            raise ValueError("gmail_draft_message_identity_unresolved")
        original = originals[0]
        return {
            "to": _addresses(original.get("to")),
            "cc": _addresses(original.get("cc")),
            "bcc": _addresses(original.get("bcc")),
            "subject": original.get("subject") or "",
            "body_plain": original.get("body_plain") or "",
        }
    if name not in {"gmail_send_email", "gmail_reply_to_email"}:
        raise ValueError("gmail_send_operation_unsupported")
    requested = dict(args)
    if name == "gmail_reply_to_email":
        identity = args.get("thread_id") or args.get("message_id")
        records = _messages(before)
        matches = [message for message in records if message.get("thread_id") == identity]
        if not matches:
            matches = [message for message in records if message.get("id") == identity]
        if not matches:
            raise ValueError("gmail_reply_parent_unresolved")
        # The installed simulator binds the first message in retained thread
        # order; this is operation semantics, not a business-policy selector.
        original = matches[0]
        requested["to"] = args.get("to") or original.get("from_")
        requested["subject"] = args.get("subject") or (
            "Re: " + original["subject"] if original.get("subject") else "Re:"
        )
        requested["body"] = args.get("body") or ""
    subject, body = requested.get("subject"), requested.get("body")
    if type(subject) is not str or type(body) is not str:
        raise ValueError("gmail_requested_content_unavailable")
    signature = requested.get("signature")
    if signature is not None and type(signature) is not str:
        raise ValueError("gmail_requested_signature_unavailable")
    if signature:
        body += "\n\n" + signature
    body_type = requested.get("body_type", "plain")
    if body_type not in (None, "plain", "html"):
        raise ValueError("gmail_requested_body_type_unsupported")
    return {
        "to": _addresses(requested.get("to")),
        "cc": _addresses(requested.get("cc")),
        "bcc": _addresses(requested.get("bcc")),
        "subject": subject,
        "body_html" if body_type == "html" else "body_plain": body,
    }


def capture_notification_effects(source: dict, spec: NotificationEffectSource) -> EffectEvidence:
    """Keep qualified send witnesses even when broader occurrence accounting fails."""
    spec = NotificationEffectSource.model_validate(spec.model_dump(mode="json"))
    source_id, selector_id = _digest(source), _digest(spec.model_dump(mode="json"))
    facts, reasons = [], []

    def result():
        return EffectEvidence(
            source_id,
            selector_id,
            tuple(facts),
            not reasons,
            reasons[0] if reasons else "reconciled_gmail_simulator_send_inventory",
        )

    try:
        for field in ("tool_execution_events", "state_write_receipts"):
            if not isinstance(source.get(field), (tuple, list)):
                raise TypeError("execution_inventory_missing")
        index = EffectIndex(persisted_transitions(source))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
        return result()
    for occurrence in index.occurrences:
        if occurrence.origin != "tool_server":
            reasons.append("unsupported_execution_origin")
            continue
        try:
            if (
                occurrence.before_json is None
                or occurrence.after_json is None
                or occurrence.action is None
            ):
                raise ValueError("gmail_occurrence_capture_unavailable")
            if outside_service(operation(occurrence.action)[0], "gmail",
                               index.world(occurrence.before_json), index.world(occurrence.after_json)):
                continue
            before, after = index.world(occurrence.before_json), index.world(occurrence.after_json)
            _messages(before)
            _messages(after)
            if _filing_only(operation(occurrence.action)[0], before, after):
                continue  # labels, read/star flags, archive/trash: never a send
            if EffectIndex((occurrence,)).serial_chain().status != "qualified":
                raise ValueError("gmail_occurrence_revision_unqualified")
            name, args = operation(occurrence.action)
            observed = notifications(EffectIndex((occurrence,)))
            if not observed and name in _GMAIL_READS:
                continue
            if len(observed) != 1 or observed[0].status != "qualified":
                raise ValueError(
                    observed[0].reason if observed else "gmail_operation_scope_unsupported"
                )
            notice = observed[0]
            if notice.kind == "draft":
                # A native draft is independently qualified, but never a send.
                continue
            if notice.kind != "send" or notice.message is None or notice.message_id is None:
                raise ValueError("gmail_send_witness_unavailable")
            if name in {"gmail_send_email", "gmail_reply_to_email"}:
                returned = result_payload(occurrence.action)
                if returned is None or returned.get("success") is not True:
                    raise ValueError("gmail_send_success_ack_unavailable")
            requested = _requested_message(name, args, before)
            message = notice.message
            for field, expected in requested.items():
                actual = (
                    _addresses(message.get(field))
                    if field in {"to", "cc", "bcc"}
                    else message.get(field)
                )
                if actual != expected:
                    raise ValueError("gmail_requested_persisted_message_mismatch")
            if type(message.get("subject")) is not str or not any(
                type(message.get(field)) is str for field in ("body_plain", "body_html")
            ):
                raise ValueError("gmail_persisted_content_unavailable")
            params = {
                "message_id": notice.message_id,
                "thread_id": message.get("thread_id"),
                "to": list(_addresses(message.get("to"))),
                "cc": list(_addresses(message.get("cc"))),
                "bcc": list(_addresses(message.get("bcc"))),
                "recipients": list(notice.recipients),
                "subject": message["subject"],
                "body_plain": message.get("body_plain"),
                "body_html": message.get("body_html"),
                # Readable text for content checks: the plain body, or text
                # extracted from an HTML-only body (block tags become lines).
                "body_text": message.get("body_plain")
                if type(message.get("body_plain")) is str
                else html_text(message.get("body_html")),
                "operation": name,
            }
            facts.append(
                EffectFact(
                    notice.message_id,
                    occurrence.invocation_id,
                    "tool_server",
                    "send",
                    canonical_json(params),
                    "qualified",
                    notice.reason,
                    occurrence.expected_revision,
                    occurrence.applied_revision,
                )
            )
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            reasons.append(str(error))
            facts.append(
                EffectFact(
                    None,
                    occurrence.invocation_id,
                    "tool_server",
                    "send",
                    None,
                    "unavailable",
                    str(error),
                    occurrence.expected_revision,
                    occurrence.applied_revision,
                )
            )
    try:
        task = source["task_evidence"]
        # Public initial state may omit Gmail: it then starts at schema defaults.
        _messages(task["final"])
        if task.get("complete") is not True:
            raise ValueError("task_finalization_unavailable")
        expected = {
            item.invocation_id for item in index.occurrences if item.origin == "tool_server"
        }
        writes = source["state_write_receipts"]
        if {item["write_id"] for item in writes} != expected or len(writes) != len(expected):
            raise ValueError("effect_invocation_ack_inventory_mismatch")
        if not index.occurrences:
            if not public_service_matches(task["initial"], "gmail", task["final"]["gmail"]):
                raise ValueError("gmail_initial_terminal_reconciliation_failed")
        else:
            chain = index.serial_chain()
            if (
                chain.status != "qualified"
                or chain.revision_interval is None
                or chain.revision_interval[0] != 0
            ):
                raise ValueError("gmail_complete_revision_chain_unavailable")
            if not _initial_gmail_matches(task["initial"], chain.ordered[0].before_json) or chain.ordered[-1].after_json != canonical_json(task["final"]):
                raise ValueError("gmail_initial_terminal_reconciliation_failed")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    return result()
