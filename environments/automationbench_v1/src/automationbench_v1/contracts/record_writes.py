"""Acknowledged persisted record writes in any ID-keyed simulator collection.

One adapter covers both simulator storage styles: typed collections such as
``zoom.meetings`` or ``salesforce.tasks`` (lists of records with ``id``) and
action-record services such as Airtable, Monday or Notion
(``actions[<action_key>]`` lists of ``{id, action_key, params, created_at}``).

Each acknowledged, serially qualified occurrence is diffed between its native
BEFORE and AFTER snapshots for the declared collection, keyed by record ``id``.
State is the authority, so writes through any tool (including ``api_fetch``)
are observed; nothing is inferred from tool names or results. An occurrence
whose static footprint excludes the service and leaves it unchanged is skipped.
Scope closes only with a complete revision chain from 0, a matching
acknowledgement inventory, public initial service state that reconciles with
the first BEFORE snapshot, and a final service equal to the last AFTER.
Creating then deleting a record inside one call leaves no persisted effect and
is not reported.
"""

import hashlib
import typing
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, model_validator

from ..capture import canonical_json
from ..effect_evidence import world_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation
from .base import FrozenModel, Identifier
from .effects import EffectEvidence, EffectFact
from .handler_scope import outside_service
from .service_hydration import public_service_matches

RecordKind = Literal["create", "update", "delete"]


def _digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _list_model(annotation):
    if typing.get_origin(annotation) in (list, typing.List):  # noqa: UP006
        (item,) = typing.get_args(annotation) or (None,)
        if isinstance(item, type) and hasattr(item, "model_fields"):
            return item
    return None


def collection_shape(service: str, collection: tuple[str, ...]) -> Literal["list", "actions"]:
    """Validate a collection path against the installed simulator schema."""
    from automationbench.schema.world import WorldState

    if service not in WorldState.model_fields:
        raise ValueError("record_writes_service_unknown")
    model = WorldState.model_fields[service].annotation
    fields = getattr(model, "model_fields", {})
    if not collection or collection[0] not in fields:
        raise ValueError("record_writes_collection_unknown")
    annotation = fields[collection[0]].annotation
    item = _list_model(annotation)
    if item is not None:
        if len(collection) != 1 or "id" not in item.model_fields:
            raise ValueError("record_writes_collection_identity_unavailable")
        return "list"
    if typing.get_origin(annotation) in (dict, typing.Dict):  # noqa: UP006
        _, value = typing.get_args(annotation)
        item = _list_model(value)
        keys = collection[1:]
        if (collection[0] == "actions" and item is not None and "id" in item.model_fields
                and keys and len(set(keys)) == len(keys)):
            return "actions"
    raise ValueError("record_writes_collection_unsupported")


class RecordWriteSource(FrozenModel):
    adapter: Literal["service.record_writes@1"] = "service.record_writes@1"
    service: Identifier
    # [<list field>] or ["actions", <action_key>, ...]: several action keys form
    # one inventory, so an equivalent write through a sibling action counts.
    collection: tuple[Identifier, ...] = Field(min_length=1, max_length=9)
    kind: RecordKind
    # Composite identity for list collections whose ``id`` repeats across a
    # parent (Mailchimp subscribers: [["list_id"], ["id"]]). The record id is
    # then the canonical JSON list of these string fields, matching
    # ``initial.records@1`` composite identities. Omitted when empty.
    identity_paths: tuple[tuple[Identifier], ...] = Field(default=(), exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def installed_collection(self):
        shape = collection_shape(self.service, self.collection)
        if self.identity_paths:
            from automationbench.schema.world import WorldState

            fields = WorldState.model_fields[self.service].annotation.model_fields  # type: ignore[union-attr]
            item = _list_model(fields[self.collection[0]].annotation)
            if (shape != "list" or item is None or not 2 <= len(self.identity_paths) <= 4
                    or len(set(self.identity_paths)) != len(self.identity_paths)
                    or any(path[0] not in item.model_fields or item.model_fields[path[0]].annotation is not str
                           for path in self.identity_paths)):
                raise ValueError("record_writes_identity_paths_invalid")
        return self


def _collection(world, spec: RecordWriteSource):
    service = world.get(spec.service)
    if not isinstance(service, Mapping):
        raise TypeError("record_writes_service_unavailable")
    value = service.get(spec.collection[0])
    if len(spec.collection) > 1:
        if not isinstance(value, Mapping):
            raise TypeError("record_writes_actions_unavailable")
        merged = []
        for key in spec.collection[1:]:
            items = value.get(key, [])
            if not isinstance(items, (list, tuple)):
                raise TypeError("record_writes_collection_unavailable")
            merged.extend(items)
        return merged
    if not isinstance(value, (list, tuple)):
        raise TypeError("record_writes_collection_unavailable")
    return value


def _records(world, spec: RecordWriteSource) -> dict[str, tuple]:
    records: dict[str, tuple] = {}
    for record in _collection(world, spec):
        if spec.identity_paths:
            parts = [record.get(path[0]) if isinstance(record, Mapping) else None for path in spec.identity_paths]
            if any(type(part) is not str or not part for part in parts):
                raise ValueError("record_writes_identity_unresolved")
            identity = canonical_json(parts)
        else:
            identity = record.get("id") if isinstance(record, Mapping) else None
        if type(identity) not in {str, int} or identity == "":
            raise ValueError("record_writes_identity_unresolved")
        key = canonical_json(identity)
        if key in records:
            raise ValueError("record_writes_duplicate_identity")
        records[key] = (identity, _plain(record))
    return records


def _values_text(record) -> str:
    """Scalar leaf values, one per line, for content checks over agent-chosen fields."""
    lines: list[str] = []

    def walk(value):
        if isinstance(value, Mapping):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif type(value) is str:
            lines.append(value)
        elif type(value) in {int, float}:
            lines.append(str(value))

    walk(record.get("params", record) if isinstance(record, Mapping) and "action_key" in record else record)
    return "\n".join(lines)


def _changes(before: dict, after: dict, kind: RecordKind):
    if kind == "create":
        return [(after[key][0], {"record": after[key][1], "values_text": _values_text(after[key][1])})
                for key in after if key not in before]
    if kind == "delete":
        return [(before[key][0], {"before": before[key][1]}) for key in before if key not in after]
    changed = []
    for key, (identity, record) in after.items():
        if key not in before:
            continue
        old = before[key][1]
        if canonical_json(old) != canonical_json(record):
            fields = sorted(
                name for name in set(old) | set(record)
                if canonical_json(old.get(name)) != canonical_json(record.get(name))
            )
            changed.append((identity, {"record": record, "before": old, "changed_fields": fields,
                                       "values_text": _values_text(record)}))
    return changed


def capture_record_writes(source: Mapping, spec: RecordWriteSource) -> EffectEvidence:
    """Keep qualified write witnesses even when wider inventory accounting fails."""
    spec = RecordWriteSource.model_validate(spec.model_dump(mode="python", warnings=False))
    source_id, selector_id = _digest(source), _digest(spec.model_dump(mode="json"))
    facts: list[EffectFact] = []
    reasons: list[str] = []

    def result():
        return EffectEvidence(source_id, selector_id, tuple(facts), not reasons,
                              reasons[0] if reasons else "reconciled_record_write_inventory")

    try:
        if any(not isinstance(source.get(field), (list, tuple))
               for field in ("tool_execution_events", "state_write_receipts")):
            raise ValueError("record_writes_execution_inventory_missing")
        index = EffectIndex(world_transitions(dict(source)))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
        return result()
    for occurrence in index.occurrences:
        try:
            if (occurrence.origin != "tool_server" or occurrence.action is None
                    or occurrence.before_json is None or occurrence.after_json is None):
                raise ValueError("record_writes_capture_unavailable")
            before_world, after_world = index.world(occurrence.before_json), index.world(occurrence.after_json)
            name, _ = operation(occurrence.action)
            if outside_service(name, spec.service, before_world, after_world):
                continue
            before, after = _records(before_world, spec), _records(after_world, spec)
            changes = _changes(before, after, spec.kind)
            if canonical_json(sorted(before.items())) == canonical_json(sorted(after.items())):
                continue
            if (occurrence.evidence_status != "acknowledged"
                    or EffectIndex((occurrence,)).serial_chain().status != "qualified"):
                raise ValueError("record_writes_ack_or_revision_unavailable")
            if occurrence.action.status != "returned" or occurrence.action.error_json is not None:
                raise ValueError("record_writes_failed_call_changed_state")
            for identity, params in changes:
                facts.append(EffectFact(
                    _digest([spec.service, *spec.collection, identity]), occurrence.invocation_id, "tool_server",
                    spec.kind, canonical_json({**params, "record_id": identity, "operation": name}),
                    "qualified", "acknowledged_persisted_record_write",
                    occurrence.expected_revision, occurrence.applied_revision,
                ))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            reasons.append(str(error))
            facts.append(EffectFact(None, occurrence.invocation_id, "tool_server", spec.kind, None,
                                    "unavailable", str(error), occurrence.expected_revision,
                                    occurrence.applied_revision))
    try:
        task = source["task_evidence"]
        initial, final = task["initial"], task["final"]
        if task.get("complete") is not True:
            raise ValueError("record_writes_task_finalization_unavailable")
        expected = {item.invocation_id for item in index.occurrences if item.origin == "tool_server"}
        writes = source["state_write_receipts"]
        if len(writes) != len(expected) or {item["write_id"] for item in writes} != expected:
            raise ValueError("record_writes_ack_inventory_mismatch")
        if not index.occurrences:
            observed_final = final.get(spec.service) if isinstance(final, Mapping) else None
            if not public_service_matches(initial, spec.service, observed_final):
                raise ValueError("record_writes_unobserved_scope_change")
        else:
            chain = index.serial_chain()
            if chain.status != "qualified" or chain.revision_interval is None or chain.revision_interval[0] != 0:
                raise ValueError("record_writes_complete_revision_chain_unavailable")
            first, last = chain.ordered[0], chain.ordered[-1]
            if first.before_json is None or last.after_json is None:
                raise ValueError("record_writes_boundary_capture_unavailable")
            # The final service must be the last AFTER snapshot for the declared
            # collection; unrelated generated fields elsewhere are not compared.
            if (not public_service_matches(initial, spec.service, index.world(first.before_json).get(spec.service))
                    or canonical_json(_plain(_collection(final, spec)))
                    != canonical_json(_plain(_collection(index.world(last.after_json), spec)))):
                raise ValueError("record_writes_initial_terminal_scope_mismatch")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    return result()
