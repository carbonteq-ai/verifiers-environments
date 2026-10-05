"""Acknowledged Trello list search results; action records are not provider rows."""

import json
from collections.abc import Mapping
from typing import Literal

from automationbench.schema.world import WorldState
from automationbench.tools.zapier.action_utils import find_records
from automationbench.tools.zapier.trello.actions import (
    trello_board_list,
    trello_list_by_id,
    trello_to_board_list,
)

from ..capture import canonical_json
from .base import FrozenModel
from .native_record_reads import _equal, _plain, capture_native_record_reads


class TrelloListReadSource(FrozenModel):
    adapter: Literal["trello.list_reads@1"] = "trello.list_reads@1"
    kind: Literal["read_list"] = "read_list"


_READS = {"trello_board_list": trello_board_list, "trello_list_by_id": trello_list_by_id,
          "trello_to_board_list": trello_to_board_list}
# Audited native mutations used beside these searches; these never emit reads.
_WRITES = frozenset({"trello_card", "trello_card_v2", "trello_card_update", "trello_card_label", "trello_list"})


def _project(before, name, args, result):
    if name not in _READS:
        raise ValueError("trello_read_operation_unsupported")
    before, result = _plain(before), _plain(result)
    if not isinstance(result, Mapping) or result.get("success") is not True:
        raise ValueError("trello_read_result_unavailable")
    records = result.get("results")
    if not isinstance(records, list) or len(records) > 4096:
        raise ValueError("trello_read_result_budget_or_inventory")
    if len(canonical_json(before.get("trello", {})).encode()) > 8 * 1024 * 1024:
        raise ValueError("trello_read_source_budget")
    world = WorldState.model_validate(before)
    if name == "trello_board_list":
        # This handler is find-or-create. Prove a nonempty native search match
        # BEFORE calling it on the private world, so no random write is replayed.
        filters = {k: args[k] for k in ("board", "name") if args.get(k) is not None and args[k] != ""}
        if not find_records(world.trello, "board_list", filters):
            raise ValueError("trello_read_find_or_create_write_not_read")
        if result.get("found") is not True or result.get("created") is not False:
            raise ValueError("trello_read_find_branch_mismatch")
    expected = json.loads(_READS[name](world, **args))
    if not _equal(expected, result) or not _equal(world.trello.model_dump(mode="json"), before["trello"]):
        raise ValueError("trello_read_returned_source_mismatch")
    ids = [r.get("id") for r in records if isinstance(r, Mapping)]
    if len(ids) != len(records) or any(type(key) is not str or not key for key in ids) or len(set(ids)) != len(ids):
        raise ValueError("trello_read_returned_identity_unavailable")
    # Native seed searches ignore filters missing from stored params. Preserve
    # exact returned payload; never inject requested board/list as returned facts.
    return [{"native_record_id": r["id"], "record": r, "storage_kind": "action_record",
             "found": True, "returned_count": len(records)} for r in records] or [
                 {"storage_kind": "none", "found": False, "returned_count": 0}]


def capture_trello_list_reads(source, spec):
    return capture_native_record_reads(source, spec, service="trello", project=_project, writes=_WRITES)
