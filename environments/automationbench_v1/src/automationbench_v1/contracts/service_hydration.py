"""Reconcile sparse public initial service state with hydrated native snapshots.

Public task state is sparse while native snapshots are hydrated worlds, so an
exact comparison of the two always fails on real traces. The named service is
hydrated with the simulator's own schema and compared with the observed native
service only where public state is specific:

- every public top-level key must survive hydration (the schema silently drops
  some aliases, e.g. Gmail ``emails`` beside ``messages``);
- top-level keys public state omits must equal their hydrated defaults exactly;
- lists must have the same length and agree element by element (positional);
- inside records, every public field kept by the schema must equal the observed
  value after hydration; fields public state omits are generated defaults
  (uuid/now()) and are not compared; fields the schema drops were never part of
  the simulated world.

No claim is made about other services.
"""

import copy
from collections.abc import Mapping

from ..capture import canonical_json


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _agrees(public, hydrated, observed) -> bool:
    if isinstance(public, Mapping):
        if not isinstance(hydrated, Mapping) or not isinstance(observed, Mapping):
            return False
        for key, value in public.items():
            if key not in hydrated:
                continue  # dropped by the schema: never part of the simulated world
            if key not in observed or not _agrees(value, hydrated[key], observed[key]):
                return False
        return True
    if isinstance(public, (list, tuple)):
        return (
            isinstance(hydrated, (list, tuple))
            and isinstance(observed, (list, tuple))
            and len(public) == len(hydrated) == len(observed)
            and all(_agrees(*items) for items in zip(public, hydrated, observed, strict=True))
        )
    return canonical_json(hydrated) == canonical_json(observed)


def public_service_matches(initial: Mapping, service: str, observed) -> bool:
    """True when public ``initial[service]`` is the observed native service."""
    from automationbench.schema.world import WorldState

    if not isinstance(initial, Mapping) or service not in WorldState.model_fields:
        return False
    # A service absent from public state starts at its schema defaults, exactly
    # as the simulator hydrates it.
    public, observed = _plain(initial.get(service, {})), _plain(observed)
    if canonical_json(public) == canonical_json(observed):
        return True
    if not isinstance(public, Mapping) or not isinstance(observed, Mapping):
        return False
    try:
        hydrated = WorldState.model_validate({service: copy.deepcopy(public)}).model_dump(mode="json")[service]
    except (ValueError, TypeError, KeyError):
        return False
    if any(key not in hydrated for key in public):
        return False
    if any(
        canonical_json(hydrated[key]) != canonical_json(observed.get(key))
        for key in hydrated if key not in public
    ):
        return False
    return _agrees(public, hydrated, observed)
