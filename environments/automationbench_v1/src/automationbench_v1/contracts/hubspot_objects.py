"""Native HubSpot objects and acknowledged writes, without business policy.

Object JSON contains canonical native fields, never display aliases. Membership,
field coverage, finalization and observed action closure are separate facts.
``receipt_id`` identifies the qualified native receipt; HubSpot has no audit row.
Consumers must authenticate the native source before using these projections.
"""

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import StrictBool, StrictInt, StrictStr, TypeAdapter, model_validator

from automationbench.schema.hubspot import HubSpotContact, HubSpotDeal

from ..capture import canonical_json
from ..effect_evidence import world_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation, result_payload
from .base import FrozenModel, Identifier
from .handler_scope import outside_service
from .tables import Digest


class HubSpotObjectSource(FrozenModel):
    adapter: Literal["hubspot.objects@1"] = "hubspot.objects@1"
    collection: Literal["contacts", "deals"]


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _json(value: Any) -> str:
    return canonical_json(_plain(value))


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _text(value: Any) -> bool:
    return type(value) is str and bool(value.strip())


def _model(collection: str):
    return HubSpotContact if collection == "contacts" else HubSpotDeal


def _exact_numeric(value: Any, annotation: Any) -> None:
    """Avoid Pydantic's bool/numeric Literal equality and float overflow."""
    origin, branches = get_origin(annotation), get_args(annotation)
    if origin is Union:
        for branch in branches:
            try:
                _exact_numeric(value, branch)
                TypeAdapter(branch).validate_json(_json(value), strict=True)
                return
            except (ValueError, TypeError):
                pass
        raise ValueError("hubspot_field_type_invalid")
    if origin is Literal and not any(type(value) is type(item) and value == item for item in branches):
        raise ValueError("hubspot_literal_type_invalid")
    if annotation is int and type(value) is not int:
        raise ValueError("hubspot_integer_type_invalid")
    if annotation is float and (type(value) not in (int, float) or not math.isfinite(value)):
        raise ValueError("hubspot_number_type_invalid")


def _fields(raw: Mapping, collection: str) -> tuple[dict, bool]:
    fields = _model(collection).model_fields
    values: dict = {}
    complete = set(raw) == set(fields)
    for name, value in raw.items():
        if name not in fields:
            complete = False
            continue
        try:
            _exact_numeric(value, fields[name].annotation)
            admitted = TypeAdapter(fields[name].annotation).validate_json(_json(value), strict=True)
            if isinstance(admitted, float) and not math.isfinite(admitted):
                raise ValueError("hubspot_numeric_overflow")
            values[name] = _plain(value)
        except (ValueError, TypeError, OverflowError):
            complete = False
    return values, complete


class HubSpotObjectFact(FrozenModel):
    object_id: Identifier
    object_json: StrictStr

    @model_validator(mode="after")
    def coherent(self):
        raw = json.loads(self.object_json)
        if not isinstance(raw, dict) or _json(raw) != self.object_json or raw.get("id") != self.object_id:
            raise ValueError("hubspot_object_identity_or_encoding_invalid")
        return self


class HubSpotInventory(FrozenModel):
    status: Literal["qualified", "partial", "unavailable"]
    closed: StrictBool
    reason: StrictStr
    finalized: StrictBool = True
    identities_complete: StrictBool = False
    fields_complete: StrictBool = False
    all_object_ids: tuple[Identifier, ...] = ()
    duplicate_ids: tuple[Identifier, ...] = ()
    objects: tuple[HubSpotObjectFact, ...] = ()

    @model_validator(mode="after")
    def coherent(self):
        ids = tuple(item.object_id for item in self.objects)
        if (len(set(self.all_object_ids)) != len(self.all_object_ids)
                or len(set(self.duplicate_ids)) != len(self.duplicate_ids)
                or len(set(ids)) != len(ids) or not set(ids) <= set(self.all_object_ids)
                or set(ids) & set(self.duplicate_ids)
                or not set(self.duplicate_ids) <= set(self.all_object_ids)):
            raise ValueError("hubspot_inventory_identity_invalid")
        if self.closed != (self.status == "qualified") or self.closed and (
                not self.identities_complete or not self.fields_complete or not self.finalized or self.duplicate_ids):
            raise ValueError("hubspot_inventory_closure_invalid")
        return self


class HubSpotTransition(FrozenModel):
    invocation_id: Identifier
    origin: Identifier = "tool_server"
    kind: Literal["create", "association_update", "unknown"]
    status: Literal["qualified", "unavailable"]
    reason: StrictStr
    object_id: Identifier | None = None
    receipt_id: Identifier | None = None
    before_object_json: StrictStr | None = None
    after_object_json: StrictStr | None = None
    expected_revision: StrictInt | None = None
    applied_revision: StrictInt | None = None
    requested_fields: tuple[Identifier, ...] = ()
    changed_fields: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def coherent(self):
        if self.status == "qualified":
            if (self.origin != "tool_server" or self.kind == "unknown" or self.object_id is None
                    or self.receipt_id != self.invocation_id or self.receipt_id == self.object_id
                    or self.after_object_json is None or self.expected_revision is None
                    or self.expected_revision < 0 or self.applied_revision != self.expected_revision + 1
                    or (self.kind == "create") != (self.before_object_json is None)):
                raise ValueError("hubspot_transition_qualification_invalid")
            for value in (self.before_object_json, self.after_object_json):
                if value is not None:
                    HubSpotObjectFact(object_id=self.object_id, object_json=value)
        if any(len(set(values)) != len(values) for values in (self.requested_fields, self.changed_fields)):
            raise ValueError("hubspot_transition_fields_duplicate")
        return self


class HubSpotEvidence(FrozenModel):
    source_digest: Digest
    selector_digest: Digest
    initial: HubSpotInventory
    final: HubSpotInventory
    transitions: tuple[HubSpotTransition, ...]
    complete: StrictBool
    reason: StrictStr


def _rows(world: Mapping, collection: str):
    if not isinstance(world, Mapping):
        raise ValueError("hubspot_world_unavailable")  # noqa: TRY004
    state = world.get("hubspot")
    if not isinstance(state, Mapping) or not isinstance(state.get(collection), (tuple, list)):
        raise ValueError("hubspot_collection_unavailable")  # noqa: TRY004
    return state[collection]


def _ids(rows):
    ids = [row["id"] for row in rows if isinstance(row, Mapping) and _text(row.get("id"))]
    return ids, len(ids) == len(rows)


def _inventory(world: Mapping, spec: HubSpotObjectSource, *, finalized=True):
    try:
        rows = _rows(world, spec.collection)
    except ValueError as error:
        return HubSpotInventory(status="unavailable", closed=False, reason=str(error), finalized=finalized)
    ids, identities = _ids(rows)
    duplicates = tuple(sorted(key for key, count in Counter(ids).items() if count > 1))
    objects, coverage = [], identities and not duplicates
    for row in rows:
        if not isinstance(row, Mapping) or not _text(row.get("id")) or row["id"] in duplicates:
            coverage = False
            continue
        values, full = _fields(row, spec.collection)
        coverage = coverage and full
        objects.append(HubSpotObjectFact(object_id=row["id"], object_json=_json(values)))
    closed = identities and coverage and finalized
    return HubSpotInventory(status="qualified" if closed else "partial", closed=closed,
        reason="hubspot_inventory_complete" if closed else "hubspot_inventory_partial",
        finalized=finalized, identities_complete=identities, fields_complete=coverage,
        all_object_ids=tuple(dict.fromkeys(ids)), duplicate_ids=duplicates, objects=tuple(objects))


def _receipt_binding(source: Mapping, item) -> None:
    if item.action is None:
        raise ValueError("hubspot_action_unavailable")
    for event in source["tool_execution_events"]:
        receipt = json.loads(event["receipt_json"])
        if receipt.get("invocation_id") != item.invocation_id:
            continue
        if "tool_name" in receipt and receipt["tool_name"] != item.action.tool_name:
            raise ValueError("hubspot_native_tool_mismatch")
        if "arguments_json" in receipt:
            arguments = json.loads(receipt["arguments_json"])
            if (not isinstance(arguments, dict) or arguments.get("args") != []
                    or _json(arguments.get("kwargs")) != item.action.arguments_json):
                raise ValueError("hubspot_native_arguments_mismatch")
        if receipt.get("phase") == "returned" and "result_json" in receipt and receipt["result_json"] != item.action.result_json:
            raise ValueError("hubspot_native_result_mismatch")


def _initial(source: Mapping, index: EffectIndex, spec: HubSpotObjectSource):
    raw = source.get("task_evidence", {}).get("initial", {})
    direct = _inventory(raw, spec)
    # Only an explicit complete identity list can be enriched with omitted schema
    # fields. No missing list or generated ID is inferred from later evidence.
    if not direct.identities_complete or direct.duplicate_ids:
        return direct
    anchors = []
    for item in index.occurrences:
        if (type(item.expected_revision) is not int or item.expected_revision != 0
                or item.before_json is None or item.action is None
                or item.action.status != "returned" or item.action.error_json is not None
                or EffectIndex((item,)).serial_chain().status != "qualified"):
            continue
        try:
            _receipt_binding(source, item)
            before = index.world(item.before_json)
            hydrated = _inventory(before, spec)
            public_rows, native_rows = _rows(raw, spec.collection), _rows(before, spec.collection)
            if (not hydrated.closed or _json(direct.all_object_ids) != _json(hydrated.all_object_ids)
                    or len(public_rows) != len(native_rows)):
                raise ValueError("hubspot_initial_membership_mismatch")
            by_id = {row["id"]: row for row in native_rows}
            for row in public_rows:
                native = by_id[row["id"]]
                if any(key not in native or _json(value) != _json(native[key]) for key, value in row.items()):
                    raise ValueError("hubspot_initial_fields_mismatch")
            anchors.append(hydrated)
        except (ValueError, TypeError, KeyError):
            return direct
    if anchors and all(anchor == anchors[0] for anchor in anchors):
        return anchors[0]
    return direct


def _properties(args: Mapping) -> dict:
    result = {}
    additional = args.get("additional_properties_json")
    if additional:
        if type(additional) is not str:
            raise ValueError("hubspot_properties_argument_invalid")
        parsed = json.loads(additional)
        if not isinstance(parsed, dict):
            raise ValueError("hubspot_properties_argument_invalid")
        result.update({key: str(value) for key, value in parsed.items()})
    properties = args.get("properties")
    if properties:
        if not isinstance(properties, Mapping):
            raise ValueError("hubspot_properties_argument_invalid")
        result.update({key: str(_plain(value)) for key, value in properties.items()})
    return result


def _create_fields(args: Mapping, collection: str) -> dict:
    if collection == "contacts":
        allowed = {"email", "firstname", "lastname", "phone", "company", "jobtitle", "lifecyclestage",
                   "additional_properties_json", "properties", "first_name", "last_name"}
        fields = {key: args.get(key) for key in ("email", "phone", "company", "jobtitle")}
        for key, alias in (("firstname", "first_name"), ("lastname", "last_name")):
            fields[key] = args.get(key) or args.get(alias)
        fields["lifecyclestage"] = args.get("lifecyclestage", "lead")
    else:
        allowed = {"dealname", "dealstage", "pipeline", "amount", "closedate", "dealtype",
                   "hubspot_owner_id", "additional_properties_json"}
        fields = {key: args.get(key) for key in ("dealname", "dealstage", "amount", "closedate", "hubspot_owner_id")}
        fields.update(pipeline=args.get("pipeline", "default"), dealtype=args.get("dealtype", "newbusiness"))
    if set(args) - allowed:
        raise ValueError("hubspot_create_arguments_unsupported")
    fields["properties"] = _properties(args)
    # Validation only: conversion of numeric int to float or serialized datetime
    # is the installed handler contract; it never alters retained object facts.
    for key, value in fields.items():
        _exact_numeric(value, _model(collection).model_fields[key].annotation)
        TypeAdapter(_model(collection).model_fields[key].annotation).validate_json(_json(value), strict=True)
    return fields


def _transition(item, index: EffectIndex, spec: HubSpotObjectSource):
    if (item.origin == "tool_server" and item.action is not None
            and item.before_json is not None and item.after_json is not None
            and outside_service(operation(item.action)[0], "hubspot",
                                index.world(item.before_json), index.world(item.after_json))):
        return None
    if (item.origin != "tool_server" or item.action is None or item.action.status != "returned"
            or item.action.error_json is not None or item.evidence_status != "acknowledged"
            or item.before_json is None or item.after_json is None
            or EffectIndex((item,)).serial_chain().status != "qualified"):
        raise ValueError("hubspot_ack_or_local_result_unavailable")
    before, after = index.world(item.before_json), index.world(item.after_json)
    name, args = operation(item.action)
    creates = {"hubspot_create_contact": "contacts", "hubspot_create_deal": "deals"}
    if name not in creates and name != "hubspot_add_contact_to_deal":
        raise ValueError("hubspot_operation_scope_unsupported")
    collection = creates.get(name, "deals")
    response = result_payload(item.action)
    if not isinstance(response, Mapping) or response.get("success") is not True or "error" in response:
        raise ValueError("hubspot_response_unsuccessful")
    key = "contact_id" if collection == "contacts" else "deal_id"
    identity = response.get(key)
    if not _text(identity) or identity == item.invocation_id:
        raise ValueError("hubspot_response_identity_unavailable")
    old_rows, new_rows = _rows(before, collection), _rows(after, collection)
    old_ids, old_known = _ids(old_rows)
    new_ids, new_known = _ids(new_rows)
    if not old_known or not new_known or new_ids.count(identity) != 1:
        raise ValueError("hubspot_transition_membership_unavailable")
    current = next(row for row in new_rows if row["id"] == identity)
    values, full = _fields(current, collection)
    if not full:
        raise ValueError("hubspot_transition_fields_unavailable")
    expected = _plain(before)
    prior = None
    if name in creates:
        if identity in old_ids or len(new_rows) != len(old_rows) + 1:
            raise ValueError("hubspot_birth_not_proven")
        request = _create_fields(args, collection)
        # Reconstruct with actual native generated identity/timestamps; all other
        # defaults must be installed model defaults, not supplied arbitrary fields.
        expected_record = _model(collection).model_validate({**request, "id": identity,
            "created_at": current["created_at"], "updated_at": current["updated_at"]}).model_dump(mode="json")
        if _json(expected_record) != _json(current):
            raise ValueError("hubspot_created_fields_disagree_with_request")
        display = _model(collection).model_validate(_plain(current)).to_display_dict()
        if _json(response.get("contact" if collection == "contacts" else "deal")) != _json(display):
            raise ValueError("hubspot_response_object_mismatch")
        expected["hubspot"][collection].append(_plain(current))
        requested_names = set(args) & set(request)
        for alias, canonical in (("first_name", "firstname"), ("last_name", "lastname"),
                                 ("additional_properties_json", "properties")):
            if alias in args:
                requested_names.add(canonical)
        requested = tuple(sorted(requested_names))
        changed = tuple(sorted(key for key in values if key not in {"id", "created_at", "updated_at"}))
    else:
        if set(args) != {"deal_id", "contact_id"} or args.get("deal_id") != identity or not _text(args.get("contact_id")):
            raise ValueError("hubspot_association_requested_target_mismatch")
        contact_id = args["contact_id"]
        contact_ids, known = _ids(_rows(before, "contacts"))
        if not known or contact_ids.count(contact_id) != 1 or old_ids.count(identity) != 1:
            raise ValueError("hubspot_association_contact_or_deal_unavailable")
        if response.get("associated") is not True or response.get("contact_id") != contact_id:
            raise ValueError("hubspot_association_result_mismatch")
        prior = next(row for row in old_rows if row["id"] == identity)
        _, prior_full = _fields(prior, collection)
        if not prior_full:
            raise ValueError("hubspot_association_baseline_unavailable")
        wanted = _plain(prior)
        if contact_id not in wanted["associated_contact_ids"]:
            wanted["associated_contact_ids"].append(contact_id)
        wanted["updated_at"] = current["updated_at"]
        if _json(wanted) != _json(current):
            raise ValueError("hubspot_association_state_mismatch")
        expected["hubspot"][collection] = [_plain(current) if row["id"] == identity else _plain(row) for row in old_rows]
        requested = ("associated_contact_ids",)
        changed = requested if _json(prior["associated_contact_ids"]) != _json(current["associated_contact_ids"]) else ()
    if _json(expected) != _json(after):
        raise ValueError("hubspot_unrelated_state_changed")
    if collection != spec.collection:
        return None
    return HubSpotTransition(invocation_id=item.invocation_id, kind="create" if prior is None else "association_update",
        status="qualified", reason="native_hubspot_ack_result_and_persisted_object",
        object_id=identity, receipt_id=item.invocation_id, before_object_json=_json(prior) if prior is not None else None,
        after_object_json=_json(current), expected_revision=item.expected_revision,
        applied_revision=item.applied_revision, requested_fields=requested, changed_fields=changed)


def capture_hubspot_evidence(source: Mapping, spec: HubSpotObjectSource) -> HubSpotEvidence:
    spec = HubSpotObjectSource.model_validate(spec.model_dump(mode="python"))
    task = source.get("task_evidence", {})
    initial = _inventory(task.get("initial", {}), spec)
    final = _inventory(task.get("final", {}), spec, finalized=task.get("complete") is True)
    reasons, transitions = [], []
    try:
        if any(not isinstance(source.get(key), (tuple, list)) for key in ("tool_execution_events", "state_write_receipts")):
            raise ValueError("hubspot_execution_inventory_unavailable")
        index = EffectIndex(world_transitions(dict(source)))
        initial = _initial(source, index, spec)
        for item in index.occurrences:
            try:
                _receipt_binding(source, item)
                fact = _transition(item, index, spec)
                if fact is not None:
                    transitions.append(fact)
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
                reasons.append(str(error))
                transitions.append(HubSpotTransition(invocation_id=item.invocation_id, origin=item.origin,
                    kind="unknown", status="unavailable", reason=str(error)))
        chain = index.serial_chain()
        writes = source["state_write_receipts"]
        if (len(writes) != len(index.occurrences)
                or {write["write_id"] for write in writes} != {item.invocation_id for item in index.occurrences}):
            raise ValueError("hubspot_ack_inventory_mismatch")
        if index.occurrences:
            if (chain.status != "qualified" or chain.revision_interval is None
                    or chain.revision_interval[0] != 0 or chain.ordered[-1].after_json != _json(task.get("final"))):
                raise ValueError("hubspot_history_reconciliation_unavailable")
        elif _json(task.get("initial")) != _json(task.get("final")):
            raise ValueError("hubspot_empty_history_state_mismatch")
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        reasons.append(str(error))
    if not initial.closed:
        reasons.append(initial.reason)
    if not final.closed:
        reasons.append(final.reason)
    return HubSpotEvidence(source_digest=_digest(source), selector_digest=_digest(spec.model_dump(mode="json")),
        initial=initial, final=final, transitions=tuple(transitions), complete=not reasons,
        reason=reasons[0] if reasons else "reconciled_native_hubspot_object_history")


def validate_hubspot_evidence(evidence: HubSpotEvidence, source: Mapping, spec: HubSpotObjectSource) -> None:
    admitted = HubSpotEvidence.model_validate(evidence.model_dump(mode="python", warnings=False))
    actual = capture_hubspot_evidence(source, spec)
    if _json(admitted.model_dump(mode="json")) != _json(actual.model_dump(mode="json")):
        raise ValueError("hubspot_evidence_source_or_selector_mismatch")
