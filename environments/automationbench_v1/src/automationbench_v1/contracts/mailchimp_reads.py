"""Acknowledged native Mailchimp audience subscriber listings."""

import json
from collections.abc import Mapping
from typing import Literal

from automationbench.schema.world import WorldState
from automationbench.tools.zapier.mailchimp.subscribers import mailchimp_list_subscribers

from ..capture import canonical_json
from .base import FrozenModel
from .native_record_reads import _equal, _plain, capture_native_record_reads


class MailchimpSubscriberReadSource(FrozenModel):
    adapter: Literal["mailchimp.subscriber_reads@1"] = "mailchimp.subscriber_reads@1"
    kind: Literal["read_subscribers"] = "read_subscribers"


def _project(before, name, args, result):
    if name != "mailchimp_list_subscribers":
        raise ValueError("mailchimp_read_operation_unsupported")
    before, result = _plain(before), _plain(result)
    if not isinstance(result, Mapping) or result.get("success") is not True:
        raise ValueError("mailchimp_read_result_unavailable")
    records = result.get("subscribers")
    if not isinstance(records, list) or len(records) > 4096:
        raise ValueError("mailchimp_read_result_budget_or_inventory")
    if len(canonical_json(before.get("mailchimp", {})).encode()) > 8 * 1024 * 1024:
        raise ValueError("mailchimp_read_source_budget")
    world = WorldState.model_validate(before)
    expected = json.loads(mailchimp_list_subscribers(world, **args))
    if not _equal(expected, result) or not _equal(world.mailchimp.model_dump(mode="json"), before["mailchimp"]):
        raise ValueError("mailchimp_read_returned_source_mismatch")
    ids = [r.get("id") for r in records if isinstance(r, Mapping)]
    if len(ids) != len(records) or any(type(key) is not str or not key for key in ids) or len(set(ids)) != len(ids):
        raise ValueError("mailchimp_read_returned_identity_unavailable")
    return [{"native_record_id": r["id"], "record": r, "list_id": args["list_id"],
             "storage_kind": "subscriber", "found": True, "returned_count": len(records)} for r in records] or [
                 {"list_id": args["list_id"], "storage_kind": "none", "found": False, "returned_count": 0}]


def capture_mailchimp_subscriber_reads(source, spec):
    # Audited add-or-update mutations are authenticated separately and emit no
    # read facts. All other in-service operations remain explicitly unsupported.
    return capture_native_record_reads(source, spec, service="mailchimp", project=_project,
                                       writes=frozenset({"mailchimp_add_subscriber"}))
