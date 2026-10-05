"""Acknowledged native Slack user lookups, separate from message reads."""

import json
from collections.abc import Mapping
from typing import Literal

from automationbench.schema.world import WorldState
from automationbench.tools.zapier.slack import users

from ..capture import canonical_json
from .base import FrozenModel
from .native_record_reads import _equal, _plain, capture_native_record_reads


class SlackUserReadSource(FrozenModel):
    adapter: Literal["slack.user_reads@1"] = "slack.user_reads@1"
    kind: Literal["read_user"] = "read_user"


_LOOKUPS = {name: getattr(users, name) for name in (
    "slack_find_user_by_email", "slack_find_user_by_id",
    "slack_find_user_by_name", "slack_find_user_by_username",
)}


def _project(before, name, args, result):
    handler = _LOOKUPS.get(name)
    if handler is None:
        raise ValueError("slack_user_read_operation_unsupported")
    before, args, result = _plain(before), _plain(args), _plain(result)
    if len(canonical_json(before.get("slack", {})).encode()) > 8 * 1024 * 1024:
        raise ValueError("slack_user_read_source_budget")
    world = WorldState.model_validate(before)
    expected = json.loads(handler(world, **args))
    if not _equal(expected, result) or not _equal(world.slack.model_dump(mode="json"), before["slack"]):
        raise ValueError("slack_user_read_returned_source_mismatch")
    scope = {"query_operation": name, "query_args": args}
    if result.get("success") is False:
        return [{**scope, "storage_kind": "none", "found": False, "returned_count": 0}]
    record = result.get("user")
    if not isinstance(record, Mapping) or type(record.get("id")) is not str or not record["id"]:
        raise ValueError("slack_user_read_returned_identity_unavailable")
    return [{**scope, "native_record_id": record["id"], "record": record,
             "storage_kind": "user", "found": True, "returned_count": 1}]


def capture_slack_user_reads(source, spec):
    return capture_native_record_reads(
        source, spec, service="slack", project=_project,
        writes=frozenset({"slack_send_direct_message", "slack_send_channel_message"}),
    )
