"""Ephemeral indexes over source-qualified native world transitions.

Snapshot sharing is a storage optimization, never execution deduplication. A
qualified serial chain proves linkage among the supplied occurrences only. The
caller must independently establish the expected invocation inventory, initial
facts, finalization and task-specific effect semantics before proving compliance.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import pairwise
from types import MappingProxyType
from typing import Any, Literal

from .capture import canonical_json
from .effect_evidence import WorldTransition


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite_snapshot_constant:{value}")


@dataclass(frozen=True)
class SerialChain:
    status: Literal["qualified", "unavailable"]
    reason: str
    ordered: tuple[WorldTransition, ...] = ()

    @property
    def revision_interval(self) -> tuple[int, int] | None:
        if not self.ordered:
            return None
        start, end = self.ordered[0].expected_revision, self.ordered[-1].applied_revision
        assert start is not None and end is not None
        return start, end


@dataclass(frozen=True)
class ServiceObservation:
    origin: str
    invocation_id: str
    status: Literal["changed", "unchanged", "unavailable"]
    changed_services: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ServiceHistory:
    """Observed service differences, not inferred useful or harmful actions."""

    services: tuple[str, ...]
    chain: SerialChain
    observations: tuple[ServiceObservation, ...]

    @property
    def captured_scope_qualified(self) -> bool:
        """No claim of complete capture outside the supplied occurrences."""
        return self.chain.status == "qualified" and all(
            item.status != "unavailable" for item in self.observations
        )


class EffectIndex:
    """Decode each distinct world once and retain all execution identities.

    Input must come from a source-bound trace's ``world_transitions``. We check
    snapshot integrity again, but cannot authenticate a caller-created trace.
    Reads consume persistence revisions in the current simulator, so unchanged
    worlds remain distinct members of a serial chain. No local capture index or
    supplied tuple order establishes serialization. Returned worlds and records
    are recursively immutable; the index is local to one assessment invocation.
    """

    def __init__(self, transitions: Iterable[WorldTransition]) -> None:
        self.occurrences = tuple(transitions)
        identities = [(item.origin, item.invocation_id) for item in self.occurrences]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate_execution_identity")
        self._worlds: dict[str, Mapping[str, Any]] = {}
        self._texts: dict[str, str] = {}
        self._service_digests: dict[str, dict[str, str]] = {}
        self._digests: dict[tuple[str, str], tuple[str | None, str | None]] = {}
        for item in self.occurrences:
            before = self._retain(item.before_json)
            after = self._retain(item.after_json)
            if item.action is not None and (
                before != item.action.before_digest or after != item.action.after_digest
            ):
                raise ValueError("action_snapshot_digest_mismatch")
            self._digests[item.origin, item.invocation_id] = (before, after)
        self._chain = self._derive_chain()

    @property
    def snapshot_count(self) -> int:
        return len(self._worlds)

    def _retain(self, text: str | None) -> str | None:
        if text is None:
            return None
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest in self._worlds:
            if self._texts[digest] != text:
                raise ValueError("snapshot_digest_collision")
            return digest
        world = json.loads(text, parse_constant=_reject_constant)
        if not isinstance(world, dict):
            raise ValueError("world_snapshot_must_be_object")  # noqa: TRY004
        self._worlds[digest] = _freeze(world)
        self._texts[digest] = text
        self._service_digests[digest] = {
            key: hashlib.sha256(canonical_json(value).encode()).hexdigest()
            for key, value in world.items()
        }
        return digest

    def world(self, snapshot_json: str) -> Mapping[str, Any]:
        """Return a retained immutable world; do not silently admit new evidence."""
        digest = hashlib.sha256(snapshot_json.encode()).hexdigest()
        if digest not in self._worlds or self._texts[digest] != snapshot_json:
            raise ValueError("snapshot_not_in_evidence_index")
        return self._worlds[digest]

    def collection(
        self, snapshot_json: str, service: str, collection: str
    ) -> tuple[Mapping[str, Any], ...]:
        """Read an explicitly present record collection without inventing defaults."""
        world = self.world(snapshot_json)
        state = world.get(service)
        if not isinstance(state, Mapping) or collection not in state:
            raise ValueError("record_collection_unavailable")
        records = state[collection]
        if not isinstance(records, tuple) or any(not isinstance(item, Mapping) for item in records):
            raise ValueError("record_collection_schema_unresolved")
        return records

    def serial_chain(self) -> SerialChain:
        return self._chain

    def _derive_chain(self) -> SerialChain:
        if not self.occurrences:
            return SerialChain("unavailable", "empty_occurrence_inventory")
        for item in self.occurrences:
            if item.evidence_status != "acknowledged":
                return SerialChain("unavailable", "unqualified_occurrence")
            if item.before_json is None or item.after_json is None or item.action is None:
                return SerialChain("unavailable", "world_capture_missing")
            if (
                type(item.expected_revision) is not int
                or type(item.applied_revision) is not int
                or item.expected_revision < 0
                or item.applied_revision != item.expected_revision + 1
            ):
                return SerialChain("unavailable", "revision_transition_unqualified")
        ordered = tuple(sorted(self.occurrences, key=lambda item: item.expected_revision or 0))
        if len({item.expected_revision for item in ordered}) != len(ordered):
            return SerialChain("unavailable", "revision_branch")
        for previous, following in pairwise(ordered):
            if previous.applied_revision != following.expected_revision:
                return SerialChain("unavailable", "revision_gap")
            previous_after = self._digests[previous.origin, previous.invocation_id][1]
            following_before = self._digests[following.origin, following.invocation_id][0]
            if previous_after != following_before:
                return SerialChain("unavailable", "world_link_conflict")
        return SerialChain("qualified", "revision_and_world_linked", ordered)

    def service_history(self, services: Iterable[str]) -> ServiceHistory:
        """Classify deltas for named services without treating unknowns as unrelated.

        Even an unchanged service is only an observation of state equality. It
        does not exclude an attempted action, an external effect or a simulator
        abstraction that lacks an adequate effect model for the policy.
        """
        scope = tuple(services)
        if not scope or any(not isinstance(item, str) or not item for item in scope):
            raise ValueError("service_scope_must_be_explicit")
        selected = tuple(sorted(set(scope)))
        observations = []
        for item in self.occurrences:
            reason = item.reason
            changed: tuple[str, ...] = ()
            status: Literal["changed", "unchanged", "unavailable"] = "unavailable"
            if (
                item.evidence_status == "acknowledged"
                and item.before_json is not None
                and item.after_json is not None
            ):
                before, after = self.world(item.before_json), self.world(item.after_json)
                if any(
                    not isinstance(world.get(service), Mapping)
                    for world in (before, after)
                    for service in selected
                ):
                    reason = "scoped_service_schema_unavailable"
                else:
                    before_digest, after_digest = self._digests[item.origin, item.invocation_id]
                    assert before_digest is not None and after_digest is not None
                    changed = tuple(
                        service
                        for service in selected
                        if self._service_digests[before_digest][service]
                        != self._service_digests[after_digest][service]
                    )
                    status = "changed" if changed else "unchanged"
                    reason = "observed_scoped_service_delta"
            observations.append(
                ServiceObservation(item.origin, item.invocation_id, status, changed, reason)
            )
        return ServiceHistory(selected, self._chain, tuple(observations))
