"""Fresh terminal records of any typed service collection, for retained outcomes.

``objects.created_and_retained@1`` asks whether a *fresh* object (one whose
native identity was not in the initial state) exists in the terminal state and
satisfies ``retained_when``. HubSpot and Jira have dedicated adapters that
also carry action transitions for completion credit. This adapter is the
generic outcome-only counterpart for any service collection whose records have
a string ``id`` (for example Gmail ``drafts``):

- initial identities come from the public initial collection; they are
  complete only when every public record carries an explicit string ``id``
  (generated ids would make an old record look fresh) and, when the public
  service omits the collection, the simulator's own hydration of the public
  service leaves it empty (no alias fed it);
- terminal records come from ``task_evidence.final`` (the native terminal
  world); membership is closed only when every record has a unique string id;
- declared ``references`` resolve one hop inside the same terminal service:
  ``{"message": {"field": "message_id", "collection": "messages"}}`` publishes
  ``retained.message`` as the unique terminal ``messages`` record whose ``id``
  equals the draft's ``message_id``. A missing, non-string or ambiguous
  reference publishes nothing, so predicates reading it stay unknown.

The predicate view is ``retained.id``, ``retained.record.*`` (the raw
terminal record) and ``retained.<reference>.*``. It establishes a retained
outcome only. Which call created the object, and any action credit, are
separate questions (the completion credit policy rejects this adapter).
"""

import hashlib
from collections import Counter
from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

from pydantic import Field, StrictBool, StrictStr, field_serializer, model_validator

from ..capture import canonical_json
from .base import FrozenModel, Identifier
from .populations import _model


def _digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _identified(service: str, collection: str):
    model = _model(service, collection)
    field = model.model_fields.get("id")
    if field is None or field.annotation is not str:
        raise ValueError("created_record_native_identity_required")
    return model


class RecordReference(FrozenModel):
    field: Identifier
    collection: Identifier


class CreatedRecordSource(FrozenModel):
    adapter: Literal["final.created_records@1"] = "final.created_records@1"
    service: Identifier
    collection: Identifier
    references: dict[Identifier, RecordReference] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def schema(self):
        model = _identified(self.service, self.collection)
        if len(self.references) > 4 or {"id", "record"} & set(self.references):
            raise ValueError("created_record_reference_alias_invalid")
        for reference in self.references.values():
            field = model.model_fields.get(reference.field)
            if field is None or field.annotation not in (str, str | None):
                raise ValueError("created_record_reference_field_invalid")
            _identified(self.service, reference.collection)
        object.__setattr__(self, "references", MappingProxyType(dict(self.references)))
        return self

    @field_serializer("references")
    def serialize_references(self, value):
        return {key: item.model_dump(mode="json") for key, item in value.items()}


class CreatedRecordObject(FrozenModel):
    object_id: StrictStr
    object_json: StrictStr


class CreatedRecordInitial(FrozenModel):
    all_object_ids: tuple[StrictStr, ...]
    identities_complete: StrictBool


class CreatedRecordFinal(FrozenModel):
    all_object_ids: tuple[StrictStr, ...]
    objects: tuple[CreatedRecordObject, ...]
    closed: StrictBool


class CreatedRecordEvidence(FrozenModel):
    source_digest: StrictStr
    selector_digest: StrictStr
    initial: CreatedRecordInitial
    final: CreatedRecordFinal
    complete: StrictBool
    reason: StrictStr


def _initial(world, spec: CreatedRecordSource) -> CreatedRecordInitial:
    from automationbench.schema.world import WorldState

    state = world.get(spec.service, {}) if isinstance(world, Mapping) else None
    if not isinstance(state, Mapping):
        return CreatedRecordInitial(all_object_ids=(), identities_complete=False)
    if spec.collection not in state:
        # Omitted collection: decided by the simulator's own hydration (an alias
        # could feed it). Only a provably empty hydrated collection is complete;
        # hydrated records would carry generated ids.
        try:
            hydrated = WorldState.model_validate({spec.service: dict(state)}).model_dump(
                mode="json"
            )
        except (ValueError, TypeError):
            return CreatedRecordInitial(all_object_ids=(), identities_complete=False)
        return CreatedRecordInitial(
            all_object_ids=(), identities_complete=hydrated[spec.service][spec.collection] == []
        )
    records = state[spec.collection]
    if not isinstance(records, list):
        return CreatedRecordInitial(all_object_ids=(), identities_complete=False)
    ids = [record.get("id") if isinstance(record, Mapping) else None for record in records]
    explicit = tuple(item for item in ids if type(item) is str and item)
    return CreatedRecordInitial(
        all_object_ids=explicit, identities_complete=len(explicit) == len(ids)
    )


def _index(records):
    """id -> record for uniquely identified terminal records, plus closure."""
    if not isinstance(records, list):
        return {}, False
    ids = [record.get("id") if isinstance(record, Mapping) else None for record in records]
    counts = Counter(item for item in ids if type(item) is str and item)
    unique = {
        record["id"]: record
        for record, identity in zip(records, ids, strict=True)
        if type(identity) is str and identity and counts[identity] == 1
    }
    return unique, len(unique) == len(records)


def capture_created_records(source: Mapping, spec: CreatedRecordSource) -> CreatedRecordEvidence:
    spec = CreatedRecordSource.model_validate(spec.model_dump(mode="python", warnings=False))
    task = source.get("task_evidence") if isinstance(source, Mapping) else None
    task = task if isinstance(task, Mapping) else {}
    initial = _initial(task.get("initial"), spec)
    final_world = task.get("final")
    state = final_world.get(spec.service) if isinstance(final_world, Mapping) else None
    state = state if isinstance(state, Mapping) else {}
    primary, closed = _index(state.get(spec.collection))
    targets = {
        alias: _index(state.get(reference.collection))[0]
        for alias, reference in spec.references.items()
    }
    objects = []
    for object_id in sorted(primary):
        record = primary[object_id]
        view = {"id": object_id, "record": record}
        for alias, reference in spec.references.items():
            pointer = record.get(reference.field)
            if type(pointer) is str and pointer in targets[alias]:
                view[alias] = targets[alias][pointer]
        objects.append(CreatedRecordObject(object_id=object_id, object_json=canonical_json(view)))
    final = CreatedRecordFinal(
        all_object_ids=tuple(sorted(primary)),
        objects=tuple(objects),
        closed=closed and isinstance(state.get(spec.collection), list),
    )
    complete = final.closed and initial.identities_complete and task.get("complete") is True
    return CreatedRecordEvidence(
        source_digest=_digest(source),
        selector_digest=_digest(spec.model_dump(mode="json")),
        initial=initial,
        final=final,
        complete=complete,
        reason="created_records_identities_closed"
        if complete
        else "created_records_identity_scope_partial",
    )


def validate_created_records(
    evidence: CreatedRecordEvidence, source: Mapping, spec: CreatedRecordSource
) -> None:
    admitted = CreatedRecordEvidence.model_validate(
        evidence.model_dump(mode="python", warnings=False)
    )
    if canonical_json(admitted.model_dump(mode="json")) != canonical_json(
        capture_created_records(source, spec).model_dump(mode="json")
    ):
        raise ValueError("created_records_source_or_projection_mismatch")
