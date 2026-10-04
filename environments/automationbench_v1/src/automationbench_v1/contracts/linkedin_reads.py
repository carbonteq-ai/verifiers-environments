"""Native returned LinkedIn records; no claim about subsequent model conditioning.

One fact per record an acknowledged successful read call returned
(``read_record``): profiles, connections, companies and posts. Every returned
record must exist in the pre-call world under its native ``id`` and every
returned field must agree with that stored record, so a forged or coherently
rewritten result cannot invent a read. Failed or empty reads return nothing;
job lookups return no facts. LinkedIn writes (messages, invitations, shares,
company updates) are not reads and are skipped; calls whose static footprint
excludes LinkedIn and which left it unchanged are skipped. Any other operation
(``api_fetch``, unknown tools) leaves the inventory incomplete.

Identity: profile, company and post ids are public. A connection's ``id`` is
generated at hydration when public state omits it, so facts also carry
``profile_id`` (a profile's id, or a connection's ``connected_profile_id``)
and ``email``; ``identity`` is the best stable identity (``profile_id``, else
``email``, else null for an anonymous connection).
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict
from typing import Literal

from ..capture import canonical_json
from ..effect_evidence import persisted_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation, result_payload
from .base import FrozenModel
from .effects import EffectEvidence, EffectFact
from .handler_scope import outside_service
from .service_hydration import public_collection, public_service_matches
from .slack_effects import _equal, _plain, _text


class LinkedInReadSource(FrozenModel):
    adapter: Literal["linkedin.reads@1"] = "linkedin.reads@1"
    kind: Literal["read_record"] = "read_record"


# Installed LinkedIn handlers that write state; never a read.
_LINKEDIN_WRITES = frozenset({
    "linkedin_send_message", "linkedin_send_invite", "linkedin_create_share", "linkedin_create_company_update",
})
# Audited reads whose results carry no profile/connection/company/post.
_NO_RECORDS = frozenset({"linkedin_get_job", "linkedin_find_jobs"})
_READS = frozenset({
    "linkedin_get_my_profile", "linkedin_get_connections", "linkedin_get_profile", "linkedin_find_profile",
    "linkedin_find_post", "linkedin_list_companies", "linkedin_get_company",
})
_COLLECTIONS = {"profile": "profiles", "connection": "connections", "company": "companies", "post": "posts"}
# Result envelope keys that are not record fields.
_ENVELOPE = frozenset({"success"})


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _collection(world, name):
    records = public_collection(world, "linkedin", name)
    if not isinstance(records, (list, tuple)) or any(not isinstance(record, Mapping) for record in records):
        raise TypeError("linkedin_collection_unavailable:" + name)
    identities = [record.get("id") for record in records]
    if any(not _text(identity) for identity in identities) or len(set(identities)) != len(identities):
        raise ValueError("linkedin_record_identity_unavailable:" + name)
    return records


def _returned(name, args, result, world):
    """(record type, returned record) pairs, or () for a failed/empty read."""
    if type(result.get("success")) is not bool:
        raise ValueError("linkedin_read_result_success_unavailable")
    if result["success"] is not True or "error" in result or name in _NO_RECORDS:
        return ()
    if name == "linkedin_get_my_profile":
        if result.get("id") is None:
            return ()  # no authenticated user profile
        return (("profile", {key: value for key, value in result.items() if key not in _ENVELOPE}),)
    if name == "linkedin_get_connections":
        if "connection" in result:
            return (("connection", result["connection"]),)
        records = result.get("connections")
        if not isinstance(records, (list, tuple)) or result.get("count") != len(records):
            raise ValueError("linkedin_read_result_count_unavailable")
        return tuple(("connection", record) for record in records)
    if name in {"linkedin_get_profile", "linkedin_find_profile"}:
        records = (result.get("profile"),) if name == "linkedin_get_profile" else result.get("profiles")
        if not isinstance(records, (list, tuple)):
            raise ValueError("linkedin_read_profiles_unavailable")
        if name == "linkedin_find_profile" and result.get("count") != len(records):
            raise ValueError("linkedin_read_result_count_unavailable")
        profiles = {record["id"] for record in _collection(world, "profiles")}
        connections = {record["id"] for record in _collection(world, "connections")}
        typed = []
        for record in records:
            identity = record.get("id") if isinstance(record, Mapping) else None
            if (identity in profiles) == (identity in connections):
                raise ValueError("linkedin_read_record_type_unresolved")
            typed.append(("profile" if identity in profiles else "connection", record))
        if name == "linkedin_get_profile":
            kind, record = typed[0]
            requested = args.get("profile_id")
            if (record.get("id") if kind == "profile" else record.get("connected_profile_id")) != requested:
                raise ValueError("linkedin_read_requested_returned_identity_mismatch")
        return tuple(typed)
    if name == "linkedin_find_post":
        if "post" in result:
            if result["post"].get("id") != args.get("post_id") if isinstance(result["post"], Mapping) else True:
                raise ValueError("linkedin_read_requested_returned_identity_mismatch")
            return (("post", result["post"]),)
        records = result.get("posts")
        if not isinstance(records, (list, tuple)) or result.get("count") != len(records):
            raise ValueError("linkedin_read_result_count_unavailable")
        return tuple(("post", record) for record in records)
    if "company" in result:
        requested = args.get("company_id") if name == "linkedin_get_company" else args.get("organization_id")
        if not isinstance(result["company"], Mapping) or result["company"].get("id") != requested:
            raise ValueError("linkedin_read_requested_returned_identity_mismatch")
        return (("company", result["company"]),)
    records = result.get("companies")
    if name != "linkedin_list_companies" or not isinstance(records, (list, tuple)) \
            or result.get("total_count") != len(records):
        raise ValueError("linkedin_read_result_count_unavailable")
    return tuple(("company", record) for record in records)


def _full_name(stored):
    first, last = stored.get("first_name"), stored.get("last_name")
    return f"{first} {last}" if type(first) is str and type(last) is str else None


def _projection(kind, record, world, name):
    if not isinstance(record, Mapping):
        raise TypeError("linkedin_read_returned_record_unavailable")
    identity = record.get("id")
    matches = [row for row in _collection(world, _COLLECTIONS[kind]) if row["id"] == identity]
    if not _text(identity) or len(matches) != 1:
        raise ValueError("linkedin_read_before_identity_unavailable")
    stored = matches[0]
    for field, value in record.items():
        if field in stored:
            agrees = _equal(_strip(value), _strip(stored[field]))
        elif field == "full_name":
            agrees = value == _full_name(stored)
        else:
            agrees = value is None
        if not agrees:
            raise ValueError("linkedin_read_returned_field_mismatch:" + str(field))
    profile_id = stored["id"] if kind == "profile" else stored.get("connected_profile_id") \
        if kind == "connection" else None
    email = stored.get("email") if kind in {"profile", "connection"} else None
    params = {"record_type": kind, "record_id": identity,
              "identity": (profile_id if _text(profile_id) else email if _text(email) else None)
              if kind in {"profile", "connection"} else identity,
              "profile_id": profile_id if _text(profile_id) else None,
              "email": email if _text(email) else None,
              "returned_fields": sorted(str(field) for field in record if record[field] is not None)}
    if kind in {"profile", "connection"}:
        params["full_name"] = _full_name(stored)
        params["public_profile_url"] = stored.get("public_profile_url") if kind == "profile" else None
        params["company"] = stored.get("current_company") if kind == "profile" else stored.get("company")
        params["headline"] = stored.get("headline")
    elif kind == "company":
        params["name"] = stored.get("name")
    else:
        params["author_id"], params["text"] = stored.get("author_id"), stored.get("text")
        params["is_deleted"] = stored.get("is_deleted") if type(stored.get("is_deleted")) is bool else None
    params["operation"] = name
    return params


def _strip(value):
    """Display dicts omit null fields (``model_dump(exclude_none=True)``)."""
    if isinstance(value, Mapping):
        return {key: _strip(item) for key, item in value.items() if item is not None}
    if isinstance(value, (list, tuple)):
        return [_strip(item) for item in value]
    return value


def capture_linkedin_reads(source: Mapping, spec: LinkedInReadSource) -> EffectEvidence:
    spec = LinkedInReadSource.model_validate(spec.model_dump(mode="python", warnings=False))
    source_id, selector_id = _digest(source), _digest(spec.model_dump(mode="json"))
    facts, reasons = [], []
    try:
        if any(not isinstance(source.get(field), (list, tuple)) for field in ("tool_execution_events", "state_write_receipts")):
            raise ValueError("linkedin_read_execution_inventory_missing")
        index = EffectIndex(persisted_transitions(dict(source)))
        terminals = {}
        for event in source["tool_execution_events"]:
            receipt = json.loads(event["receipt_json"])
            if receipt["phase"] != "dispatch":
                terminals[event["source"], receipt["invocation_id"]] = receipt
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return EffectEvidence(source_id, selector_id, (), False, str(error))
    for occurrence in index.occurrences:
        try:
            if (occurrence.origin != "tool_server" or occurrence.action is None or occurrence.before_json is None
                    or occurrence.after_json is None or EffectIndex((occurrence,)).serial_chain().status != "qualified"):
                raise ValueError("linkedin_read_ack_or_capture_unavailable")
            action = occurrence.action
            before, after = index.world(occurrence.before_json), index.world(occurrence.after_json)
            name, args = operation(action)
            if name in _LINKEDIN_WRITES or outside_service(name, "linkedin", before, after):
                continue  # writes and calls that cannot reach LinkedIn are not reads
            if name not in _READS and name not in _NO_RECORDS:
                raise ValueError("linkedin_read_operation_unsupported")
            receipt = terminals[occurrence.origin, occurrence.invocation_id]
            native_arguments = json.loads(receipt.get("arguments_json", "null"))
            if (receipt.get("tool_name") != action.tool_name or not isinstance(native_arguments, dict)
                    or set(native_arguments) != {"args", "kwargs"} or native_arguments["args"] != []
                    or not _equal(native_arguments["kwargs"], json.loads(action.arguments_json))):
                raise ValueError("linkedin_read_native_invocation_mismatch")
            if (action.status != "returned" or action.error_json is not None or action.result_json is None
                    or receipt.get("error_json") is not None or receipt.get("state_error_json") is not None
                    or receipt.get("result_json") != action.result_json):
                raise ValueError("linkedin_read_local_native_return_mismatch")
            if not _equal(before.get("linkedin"), after.get("linkedin")):
                raise ValueError("linkedin_read_changed_scope")
            result = result_payload(action)
            if result is None:
                raise ValueError("linkedin_read_result_unavailable")
            projections = [_projection(kind, record, before, name)
                           for kind, record in _returned(name, args, result, before)]
            ids = [(params["record_type"], params["record_id"]) for params in projections]
            if len(set(ids)) != len(ids):
                raise ValueError("linkedin_read_returned_identity_ambiguous")
            for params in projections:
                facts.append(EffectFact(
                    _digest([occurrence.invocation_id, params["record_type"], params["record_id"]]),
                    occurrence.invocation_id, "tool_server", spec.kind, canonical_json(params), "qualified",
                    "acknowledged_native_returned_linkedin_record", occurrence.expected_revision,
                    occurrence.applied_revision))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            reasons.append(str(error))
            facts.append(EffectFact(None, occurrence.invocation_id, "tool_server", spec.kind, None,
                "unavailable", str(error), occurrence.expected_revision, occurrence.applied_revision))
    try:
        task = source["task_evidence"]
        if task.get("complete") is not True:
            raise ValueError("linkedin_read_finalization_unavailable")
        final_linkedin = task["final"].get("linkedin", {})
        expected = {item.invocation_id for item in index.occurrences}
        if len(source["state_write_receipts"]) != len(expected) or {item["write_id"] for item in source["state_write_receipts"]} != expected:
            raise ValueError("linkedin_read_ack_inventory_mismatch")
        if index.occurrences:
            chain = index.serial_chain()
            if chain.status != "qualified" or chain.revision_interval is None or chain.revision_interval[0] != 0:
                raise ValueError("linkedin_read_complete_chain_unavailable")
            first, last = chain.ordered[0], chain.ordered[-1]
            if first.before_json is None or last.after_json is None:
                raise ValueError("linkedin_read_boundary_capture_unavailable")
            if (not public_service_matches(task["initial"], "linkedin", index.world(first.before_json)["linkedin"])
                    or not _equal(final_linkedin, index.world(last.after_json)["linkedin"])):
                raise ValueError("linkedin_read_initial_terminal_scope_mismatch")
        elif not public_service_matches(task["initial"], "linkedin", final_linkedin):
            raise ValueError("linkedin_read_unobserved_scope_change")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    return EffectEvidence(source_id, selector_id, tuple(facts), not reasons,
        reasons[0] if reasons else "reconciled_linkedin_returned_record_inventory")


def validate_linkedin_reads(evidence: EffectEvidence, source: Mapping, spec: LinkedInReadSource) -> None:
    actual = capture_linkedin_reads(source, spec)
    if canonical_json(_plain(asdict(evidence))) != canonical_json(asdict(actual)):
        raise ValueError("linkedin_read_raw_source_or_projection_mismatch")
