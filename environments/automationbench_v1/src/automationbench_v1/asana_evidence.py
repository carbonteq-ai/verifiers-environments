"""Acknowledged Asana simulator action records, not external task state.

The maintained simulator records task creation and section placement separately.
A section record references the returned creation ID; no generic action record
proves provisioning or an actual external permission grant.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .effect_index import EffectIndex
from .notification_evidence import operation, result_payload


def action_records(world: Mapping, key: str) -> tuple[Mapping, ...]:
    service = world.get("asana", {})
    if not isinstance(service, Mapping) or not isinstance(service.get("actions", {}), Mapping):
        raise TypeError("asana_action_container_unresolved")
    records = service.get("actions", {}).get(key, ())
    if not isinstance(records, (list, tuple)) or any(
        not isinstance(row, Mapping) for row in records
    ):
        raise ValueError("asana_action_population_unresolved")
    identities = [row.get("id") for row in records]
    if any(not isinstance(identity, str) or not identity for identity in identities) or len(
        set(identities)
    ) != len(identities):
        raise ValueError("asana_action_identity_unresolved")
    if any(
        row.get("action_key") != key or not isinstance(row.get("params"), Mapping)
        for row in records
    ):
        raise ValueError("asana_action_record_schema_unresolved")
    return tuple(records)


# asana_create_task stores ``description`` as ``notes`` and ``due_on`` as ``dueDate``
# (``notes or description``, ``dueDate or due_on``); compare invocations in the stored names.
_ARGUMENT_ALIASES = {"create_task": {"description": "notes", "due_on": "dueDate"}}


def stored_arguments(kind: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    effective = {key: value for key, value in arguments.items() if value is not None and value != ""}
    for alias, stored in _ARGUMENT_ALIASES.get(kind, {}).items():
        if alias in effective:
            value = effective.pop(alias)
            effective.setdefault(stored, value)
    return effective


@dataclass(frozen=True)
class AsanaEffect:
    invocation_id: str
    expected_revision: int | None
    applied_revision: int | None
    kind: str
    status: Literal["qualified", "unavailable"]
    reason: str
    record_id: str | None = None
    params: Mapping[str, Any] | None = None


def asana_effects(index: EffectIndex) -> tuple[AsanaEffect, ...]:
    effects = []
    names = {"asana_create_task": "create_task", "asana_add_task_to_section": "add_task_to_section"}
    for item in index.occurrences:
        kind = "unknown"
        identity = None
        params = None
        try:
            args = {}
            if item.action is not None:
                name, args = operation(item.action)
                kind = names.get(name, "unknown")
            if item.before_json is None or item.after_json is None:
                raise ValueError("asana_capture_unavailable")
            before, after = index.world(item.before_json), index.world(item.after_json)
            if kind == "unknown":
                if before.get("asana", {}) == after.get("asana", {}):
                    continue
                raise ValueError("asana_operation_unqualified")
            previous, current = action_records(before, kind), action_records(after, kind)
            if (
                item.evidence_status != "acknowledged"
                or item.action is None
                or item.action.status != "returned"
                or item.action.error_json is not None
            ):
                raise ValueError("asana_acknowledgement_unavailable")
            result = result_payload(item.action)
            if (
                result is None
                or result.get("success") is not True
                or not isinstance(result.get("results"), (list, tuple))
                or len(result["results"]) != 1
            ):
                raise ValueError("asana_result_unqualified")
            returned = result["results"][0]
            if not isinstance(returned, Mapping):
                raise TypeError("asana_result_identity_unresolved")
            identity = returned.get("id")
            matches = [row for row in current if row["id"] == identity]
            if len(matches) != 1 or any(row["id"] == identity for row in previous):
                raise ValueError("asana_new_record_unresolved")
            record = matches[0]
            params = record["params"]
            effective = stored_arguments(kind, args)
            if any(params.get(key) != value for key, value in effective.items()):
                raise ValueError("asana_invocation_effect_disagreement")
            if any(returned.get(key) != value for key, value in params.items()):
                raise ValueError("asana_result_effect_disagreement")
            if len(current) != len(previous) + 1 or any(row not in current for row in previous):
                raise ValueError("asana_population_effect_unresolved")
            effects.append(
                AsanaEffect(
                    item.invocation_id,
                    item.expected_revision,
                    item.applied_revision,
                    kind,
                    "qualified",
                    "acknowledged_native_action_record",
                    identity,
                    params,
                )
            )
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            effects.append(
                AsanaEffect(
                    item.invocation_id,
                    item.expected_revision,
                    item.applied_revision,
                    kind,
                    "unavailable",
                    str(error),
                    identity,
                    params,
                )
            )
    return tuple(effects)
