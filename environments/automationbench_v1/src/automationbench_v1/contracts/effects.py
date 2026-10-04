"""Bounded Asana simulator occurrence evidence, without task policy or credit.

The inventory describes acknowledged persisted action records, not external
permissions or every possible Asana operation. A qualified native append can
create its first dynamic bucket. Only explicit collections establish inventory
emptiness; that occurrence capability does not close a missing initial scope.
"""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..asana_evidence import action_records, asana_effects
from ..capture import canonical_json
from ..effect_evidence import world_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation
from .handler_scope import outside_service


class EffectSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    adapter: Literal["asana.actions@1"]
    kind: Literal["create_task", "add_task_to_section"]


@dataclass(frozen=True)
class EffectFact:
    effect_id: str | None
    invocation_id: str
    origin: Literal["tool_server"]
    kind: str
    params_json: str | None
    status: Literal["qualified", "unavailable"]
    reason: str
    expected_revision: int | None = None
    applied_revision: int | None = None


@dataclass(frozen=True)
class EffectEvidence:
    source_digest: str
    selector_digest: str
    effects: tuple[EffectFact, ...]
    complete: bool
    reason: str


_OPERATIONS = {
    "asana_create_task": "create_task",
    "asana_add_task_to_section": "add_task_to_section",
}


def _digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _collection(
    world: Mapping, kind: str, *, allow_native_append: bool = False,
) -> tuple[Mapping, ...]:
    service = world.get("asana")
    if not isinstance(service, Mapping):
        raise TypeError("asana_service_missing_or_invalid")
    actions = service.get("actions")
    if not isinstance(actions, Mapping):
        raise TypeError("asana_actions_missing_or_invalid")
    if kind not in actions:
        if allow_native_append:
            # AsanaState.record_action uses actions.setdefault(kind, []).append.
            # The two supported native handlers call it directly. This branch
            # is only for their before-state; return/result/ACK/append agreement
            # is still required below, and service/actions must exist explicitly.
            return ()
        raise ValueError("asana_selected_collection_missing")
    return action_records(world, kind)


def capture_effects(source: dict, spec: EffectSource) -> EffectEvidence:
    """Capture positive witnesses independently of whole-inventory completeness.

Input is an already source-bound native view. We reconcile its declared receipt
inventory; this does not authenticate caller-created traces. This narrow adapter
closes scope only over the two installed action-record operations. Unsupported
API/foreign operations and missing capture cannot establish an absence result.
"""
    spec = EffectSource.model_validate(spec.model_dump(mode="json"))
    source_id, selector_id = _digest(source), _digest(spec.model_dump(mode="json"))
    facts: list[EffectFact] = []
    reasons: list[str] = []

    def result() -> EffectEvidence:
        return EffectEvidence(
            source_id, selector_id, tuple(facts), not reasons,
            reasons[0] if reasons else "reconciled_asana_simulator_occurrence_inventory",
        )

    try:
        # Missing arrays are not interchangeable with a declared empty inventory.
        for field in ("tool_execution_events", "state_write_receipts"):
            if not isinstance(source.get(field), (tuple, list)):
                raise TypeError("execution_inventory_missing")
        index = EffectIndex(world_transitions(source))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
        return result()

    # Validate individual occurrences even when the serial chain or terminal
    # capture is incomplete. A later deletion cannot erase an earlier witness.
    for occurrence in index.occurrences:
        if occurrence.origin != "tool_server":
            reasons.append("unsupported_execution_origin")
            continue
        try:
            if occurrence.before_json is None or occurrence.after_json is None:
                raise ValueError("asana_capture_unavailable")
            if occurrence.action is not None and outside_service(
                operation(occurrence.action)[0], "asana",
                index.world(occurrence.before_json), index.world(occurrence.after_json),
            ):
                continue
            before, after = index.world(occurrence.before_json), index.world(occurrence.after_json)
            if occurrence.evidence_status != "acknowledged" or occurrence.action is None:
                raise ValueError(occurrence.reason)
            name, _ = operation(occurrence.action)
            if name not in _OPERATIONS:
                raise ValueError("asana_operation_scope_unsupported")
            previous = _collection(
                before, spec.kind, allow_native_append=_OPERATIONS[name] == spec.kind,
            )
            current = _collection(after, spec.kind)
            occurrence_index = EffectIndex((occurrence,))
            if occurrence_index.serial_chain().status != "qualified":
                raise ValueError("asana_occurrence_revision_unqualified")
            observed = asana_effects(occurrence_index)
            if len(observed) != 1 or observed[0].status != "qualified":
                raise ValueError(observed[0].reason if observed else "asana_effect_unresolved")
            effect = observed[0]
            if effect.kind != spec.kind:
                # Qualified section placement is not task creation, and vice
                # versa. Prove the selected collection was actually unchanged.
                if previous != current:
                    raise ValueError("asana_other_operation_changed_selected_collection")
                continue
            if effect.record_id is None or effect.params is None:
                raise ValueError("asana_effect_identity_missing")
            facts.append(EffectFact(
                effect.record_id, occurrence.invocation_id, "tool_server", effect.kind,
                canonical_json(_plain(effect.params)), "qualified", effect.reason,
                occurrence.expected_revision, occurrence.applied_revision,
            ))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            reasons.append(str(error))
            facts.append(EffectFact(
                None, occurrence.invocation_id, "tool_server", spec.kind, None,
                "unavailable", str(error), occurrence.expected_revision, occurrence.applied_revision,
            ))

    try:
        task = source["task_evidence"]
        initial, final = task["initial"], task["final"]
        _collection(initial, spec.kind)
        _collection(final, spec.kind)
        if task.get("complete") is not True:
            raise ValueError("task_finalization_unavailable")
        chain = index.serial_chain()
        if chain.status != "qualified":
            raise ValueError("effect_history_" + chain.reason)
        if chain.revision_interval is None or chain.revision_interval[0] != 0:
            raise ValueError("effect_initial_revision_unavailable")
        writes = source["state_write_receipts"]
        expected = {item.invocation_id for item in index.occurrences if item.origin == "tool_server"}
        if {item["write_id"] for item in writes} != expected or len(writes) != len(expected):
            raise ValueError("effect_invocation_ack_inventory_mismatch")
        if (
            chain.ordered[0].before_json != canonical_json(initial)
            or chain.ordered[-1].after_json != canonical_json(final)
        ):
            raise ValueError("effect_initial_terminal_reconciliation_failed")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    return result()
