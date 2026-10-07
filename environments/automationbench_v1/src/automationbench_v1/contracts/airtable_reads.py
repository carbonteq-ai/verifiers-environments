"""Acknowledged Airtable search results, reconciled with the native pre-call world.

Seeded action results are explicitly distinct from stored table records. A
requested base/table spelling never establishes storage scope for seeded results.
"""

import hashlib
import json
from collections.abc import Mapping
from typing import Literal

from automationbench.schema.world import WorldState
from automationbench.tools.zapier.airtable.actions import (
    airtable_findManyRecords,
    airtable_findRecord,
)

from ..capture import canonical_json
from .base import FrozenModel
from .native_record_reads import capture_native_record_reads


class AirtableReadSource(FrozenModel):
    adapter: Literal["airtable.record_reads@1"] = "airtable.record_reads@1"
    kind: Literal["read_record"] = "read_record"


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _equal(left, right):
    return canonical_json(_plain(left)) == canonical_json(_plain(right))


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _project(before, name, args, result):
    result = _plain(result)
    handlers = {"airtable_findRecord": airtable_findRecord, "airtable_findManyRecords": airtable_findManyRecords}
    if name not in handlers:
        raise ValueError("airtable_read_operation_unsupported")
    if not isinstance(result, Mapping) or result.get("success") is not True:
        raise ValueError("airtable_read_result_unavailable")
    records = result.get("results")
    if not isinstance(records, list) or len(records) > 4096:
        raise ValueError("airtable_read_result_budget_or_inventory")
    before = _plain(before)
    airtable = before.get("airtable", {})
    if len(canonical_json(airtable).encode()) > 8 * 1024 * 1024:
        raise ValueError("airtable_read_source_budget")
    # Re-execute only the audited pure search against a private copy of the
    # captured world, using the installed handler's exact search semantics.
    world = WorldState.model_validate(before)
    expected = json.loads(handlers[name](world, **args))
    if not _equal(expected, result):
        raise ValueError("airtable_read_returned_source_mismatch")
    ids = [record.get("id") for record in records if isinstance(record, Mapping)]
    if len(ids) != len(records) or any(type(key) is not str or not key for key in ids) or len(set(ids)) != len(ids):
        raise ValueError("airtable_read_returned_identity_unavailable")
    # Removing seeded actions distinguishes a stored-table hit from the
    # simulator's fallback seed search, which intentionally ignores base names.
    world.airtable.actions = {}
    stored = json.loads(handlers[name](world, **args))["results"]
    storage = "stored_table" if stored else "seeded_action" if records else "none"
    if stored and not _equal(stored, records):
        raise ValueError("airtable_read_storage_inventory_mismatch")
    return [{"native_record_id": record["id"], "record": record,
             "storage_kind": storage, "found": True, "returned_count": len(records)} for record in records] or [
                 {"storage_kind": "none", "found": False, "returned_count": 0}]


def capture_airtable_reads(source, spec):
    return capture_native_record_reads(source, spec, service="airtable", project=_project)
