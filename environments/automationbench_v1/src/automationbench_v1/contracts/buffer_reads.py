"""Acknowledged native Buffer channel listings, preserving fallback scope."""

import json
from collections.abc import Mapping
from typing import Literal

from automationbench.schema.world import WorldState
from automationbench.tools.zapier.buffer.posts import buffer_list_channels

from ..capture import canonical_json
from .base import FrozenModel
from .native_record_reads import _equal, _plain, capture_native_record_reads


class BufferChannelReadSource(FrozenModel):
    adapter: Literal["buffer.channel_reads@1"] = "buffer.channel_reads@1"
    kind: Literal["read_channels"] = "read_channels"


def _project(before, name, args, result):
    if name != "buffer_list_channels":
        raise ValueError("buffer_read_operation_unsupported")
    before, result = _plain(before), _plain(result)
    if not isinstance(result, Mapping) or result.get("success") is not True:
        raise ValueError("buffer_read_result_unavailable")
    records = result.get("channels")
    if not isinstance(records, list) or len(records) > 4096:
        raise ValueError("buffer_read_result_budget_or_inventory")
    if len(canonical_json(before.get("buffer", {})).encode()) > 8 * 1024 * 1024:
        raise ValueError("buffer_read_source_budget")
    world = WorldState.model_validate(before)
    expected = json.loads(buffer_list_channels(world, **args))
    if not _equal(expected, result) or not _equal(world.buffer.model_dump(mode="json"), before["buffer"]):
        raise ValueError("buffer_read_returned_source_mismatch")
    ids = [r.get("id") for r in records if isinstance(r, Mapping)]
    if len(ids) != len(records) or any(type(key) is not str or not key for key in ids) or len(set(ids)) != len(ids):
        raise ValueError("buffer_read_returned_identity_unavailable")
    # The native handler includes channels with absent organization identity.
    # Do not promote a query argument to those records' organization authority.
    return [{"native_record_id": r["id"], "record": r,
             "queried_organization_id": args["organization_id"], "storage_kind": "channel",
             "found": True, "returned_count": len(records)} for r in records] or [
                 {"queried_organization_id": args["organization_id"], "storage_kind": "none",
                  "found": False, "returned_count": 0}]


def capture_buffer_channel_reads(source, spec):
    return capture_native_record_reads(source, spec, service="buffer", project=_project,
                                       writes=frozenset({"buffer_add_to_queue"}))
