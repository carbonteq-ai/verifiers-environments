"""Reconcile sparse public initial service state with hydrated native snapshots.

Public task state is sparse while native snapshots are hydrated worlds, so an
exact comparison of the two always fails on real traces. The named service is
hydrated with the simulator's own schema and compared with the observed native
service only where public state is specific:

- Slack's own layout normalisation (messages nested under channels hoisted
  into the top-level list) is applied to public state first;
- Gmail's native ``emails`` alias is normalized to ``messages``; conflicting
  simultaneous inventories fail closed rather than silently discarding one;
- every public top-level key must survive hydration after known normalization;
- top-level keys public state omits must equal their hydrated defaults exactly;
- lists must have the same length and agree element by element (positional);
- inside records, every public field kept by the schema must equal the observed
  value after hydration; fields the schema drops were never part of the
  simulated world;
- fields public state omits are compared too (an omitted Gmail ``body_html``
  is ``None``, so invented observed HTML, labels or recipients do not
  reconcile). Only explicitly understood nondeterministic values are
  tolerated: a defaulted field whose ``default_factory`` is a generator (any
  callable other than an empty-container constructor, a model class, or a
  factory returning an empty container/None: ids, clocks), and any value that
  differs between two independent hydrations of the same public state
  (validator-generated identities). Values a validator derives
  deterministically from public input (Gmail ``internal_date`` from ``date``,
  HubSpot ``status`` stored as ``hs_pipeline_stage``) are compared.

No claim is made about other services.
"""

import copy
from collections.abc import Mapping
from functools import lru_cache

from ..capture import canonical_json


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


_EMPTY_FACTORIES = (list, dict, set, tuple, frozenset)


def _generator_factory(info) -> bool:
    """True when a field's default factory generates values (ids, clocks)."""
    from pydantic import BaseModel

    factory = info.default_factory
    if factory is None or factory in _EMPTY_FACTORIES:
        return False
    if isinstance(factory, type) and issubclass(factory, BaseModel):
        return False  # nested defaults are classified field by field
    if getattr(info, "default_factory_takes_validated_data", False):
        return False  # derived from validated input; two hydrations decide
    try:
        sample = factory()
    except Exception:  # noqa: BLE001 - an unclassifiable factory is a generator
        return True
    if isinstance(sample, BaseModel):
        return False
    return not (sample is None or (isinstance(sample, (list, dict, set, tuple, frozenset, str)) and not sample))


def _generated_defaults(value, path: tuple, out: set) -> None:
    from pydantic import BaseModel

    if isinstance(value, BaseModel):
        supplied = value.model_fields_set
        for name, info in type(value).model_fields.items():
            if name not in supplied and _generator_factory(info):
                out.add((*path, name))
                continue
            _generated_defaults(getattr(value, name, None), (*path, name), out)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _generated_defaults(item, (*path, index), out)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _generated_defaults(item, (*path, key), out)


def _differences(left, right, path: tuple, out: set) -> None:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        for key in set(left) | set(right):
            if key in left and key in right:
                _differences(left[key], right[key], (*path, key), out)
            else:
                out.add((*path, key))
    elif isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        for index, items in enumerate(zip(left, right, strict=True)):
            _differences(*items, (*path, index), out)
    elif canonical_json(left) != canonical_json(right):
        out.add(path)


@lru_cache(maxsize=64)
def _hydrate(service: str, public_json: str):
    """(hydrated dump, frozenset of tolerated nondeterministic paths) or None."""
    import json

    from automationbench.schema.world import WorldState

    try:
        first = WorldState.model_validate({service: json.loads(public_json)})
        second = WorldState.model_validate({service: json.loads(public_json)})
    except (ValueError, TypeError, KeyError):
        return None
    hydrated = first.model_dump(mode="json")[service]
    tolerated: set = set()
    _generated_defaults(getattr(first, service), (), tolerated)
    _differences(hydrated, second.model_dump(mode="json")[service], (), tolerated)
    return hydrated, frozenset(tolerated)


def _equal_except(hydrated, observed, path: tuple, tolerated: frozenset) -> bool:
    """Exact equality outside explicitly tolerated nondeterministic paths."""
    if path in tolerated:
        return True
    if isinstance(hydrated, Mapping):
        return (
            isinstance(observed, Mapping)
            and set(hydrated) == set(observed)
            and all(_equal_except(item, observed[key], (*path, key), tolerated) for key, item in hydrated.items())
        )
    if isinstance(hydrated, list):
        return (
            isinstance(observed, list)
            and len(hydrated) == len(observed)
            and all(
                _equal_except(item, other, (*path, index), tolerated)
                for index, (item, other) in enumerate(zip(hydrated, observed, strict=True))
            )
        )
    return canonical_json(hydrated) == canonical_json(observed)


def _agrees(public, hydrated, observed, path: tuple = (), tolerated: frozenset = frozenset()) -> bool:
    if isinstance(public, Mapping):
        if not isinstance(hydrated, Mapping) or not isinstance(observed, Mapping):
            return False
        if any(key not in hydrated for key in observed):
            return False  # observed content absent from the hydrated public state
        for key, value in public.items():
            if key not in hydrated:
                continue  # dropped by the schema: never part of the simulated world
            if key not in observed or not _agrees(value, hydrated[key], observed[key], (*path, key), tolerated):
                return False
        # Fields public state omits are deterministic defaults (or values
        # derived from public input) unless explicitly tolerated.
        return all(
            key in observed and _equal_except(item, observed[key], (*path, key), tolerated)
            for key, item in hydrated.items() if key not in public
        )
    if isinstance(public, (list, tuple)):
        return (
            isinstance(hydrated, (list, tuple))
            and isinstance(observed, (list, tuple))
            and len(public) == len(hydrated) == len(observed)
            and all(
                _agrees(*items, (*path, index), tolerated)
                for index, items in enumerate(zip(public, hydrated, observed, strict=True))
            )
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
    if service == "gmail" and "emails" in public:
        # Follow the native alias mapping without its silent conflict removal.
        # Both declarations must agree before any public content is removed.
        if not isinstance(public["emails"], list):
            return False
        if "messages" in public and canonical_json(public["messages"]) != canonical_json(public["emails"]):
            return False
        from automationbench.schema.gmail.base import GmailState

        public = _plain(GmailState.normalize_gmail_state_fields(copy.deepcopy(public)))
    if service == "slack":
        # Slack hoists messages nested under channels into the top-level list
        # (and renames direct_messages); compare public state in that layout.
        from automationbench.schema.slack.base import SlackState

        public = _plain(SlackState.normalize_slack_state_fields(copy.deepcopy(public)))
        if isinstance(public.get("channels"), list):
            public["channels"] = [
                {key: value for key, value in channel.items() if key != "messages"}
                if isinstance(channel, dict) else channel
                for channel in public["channels"]
            ]
    try:
        prepared = _hydrate(service, canonical_json(public))
    except (ValueError, TypeError):
        return False
    if prepared is None:
        return False
    hydrated, tolerated = prepared
    if any(key not in hydrated for key in public):
        return False
    if any(
        canonical_json(hydrated[key]) != canonical_json(observed.get(key))
        for key in hydrated if key not in public
    ):
        return False
    if not isinstance(public, Mapping):
        return False
    return all(
        key in observed and _agrees(value, hydrated[key], observed[key], (key,), tolerated)
        for key, value in public.items()
    )



def public_collection(world: Mapping, service: str, key: str):
    """``world[service][key]``; an omitted key (or service) is its schema default.

    Public initial state is sparse: a top-level key the public service mapping
    omits is hydrated to its schema default (an empty list for collections),
    exactly as ``public_service_matches`` requires. Native snapshots are fully
    hydrated, so they always carry the key and are returned unchanged. A key
    present with any value is returned as written (callers still validate it).
    None when the world or service is malformed or the schema has no empty-list
    default for the key.
    """
    from automationbench.schema.world import WorldState

    if not isinstance(world, Mapping):
        return None
    state = world.get(service, {})
    if not isinstance(state, Mapping):
        return None
    if key in state:
        return state[key]
    model = WorldState.model_fields.get(service)
    field = getattr(model.annotation, "model_fields", {}).get(key) if model is not None else None
    if field is None:
        return None
    value = field.get_default(call_default_factory=True)
    return [] if isinstance(value, list) and not value else None
