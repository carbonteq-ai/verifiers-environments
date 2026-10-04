"""Links from an evaluated effect to effects of another declared effect source.

Shared by occurrence obligations and guards ("generated-object relationships":
an update must target the record the agent created; an action must follow a
read). Join outcomes are data: ``join.<alias>`` is ``matched``/``none`` and
``joined.<alias>`` the linked effect's params; anything undecidable is absent.
"""

import json
from typing import Literal

from pydantic import field_validator

from .base import FrozenModel, Identifier
from .predicates import Predicate, evaluate_predicate, parse_predicate
from .predicates import context_paths as _fields


class EffectJoin(FrozenModel):
    """Link a matched effect to an earlier effect of another declared source.

    For each effect evaluated by ``effect_match``, qualified facts of
    ``source`` committed before the effect started (``before``), no later than
    it committed (``not_after``) or at any time (``any``) are tested with
    ``where`` (reading ``effect.*``, ``joined.*`` and the candidate context).

    ``match: "unique"``: exactly one match over a complete inventory publishes
    ``join.<alias> == "matched"`` and ``joined.<alias>.*``. ``match: "any"``:
    at least one proven match publishes ``matched`` with the earliest match,
    even if other facts are unknown. Either mode publishes ``"none"`` only when
    nothing matches over a complete inventory; anything else is unknown.
    """

    alias: Identifier
    source: Identifier
    where: Predicate
    timing: Literal["before", "not_after", "any"] = "not_after"
    match: Literal["unique", "any"] = "unique"

    @field_validator("where", mode="before")
    @classmethod
    def predicate(cls, value):
        return parse_predicate(value)


def validate_join_paths(joins, aliases, chosen=()):
    """Join aliases are unique/unreserved and ``where`` reads only known context."""
    names = [item.alias for item in joins]
    reserved = {"request", "effect", "candidate", "aggregate", "lookup", "member", "selected",
                "selection", "joined", "join"}
    if len(set(names)) != len(names) or set(names) & reserved:
        raise ValueError("join_alias_conflict")
    for item in joins:
        for path in _fields(item.where.model_dump(mode="json")):
            if path[0] == "lookup":
                if len(path) != 2 or path[1] not in aliases:
                    raise ValueError("obligation_lookup_status_reference_unknown")
            elif path[0] in {"selected", "selection"}:
                if len(path) < 2 or path[1] not in chosen or path[0] == "selection" and len(path) != 2:
                    raise ValueError("obligation_selection_reference_unknown")
            elif len(path) < 2 or path[0] not in {"effect", "joined", "request", "candidate", *aliases}:
                raise ValueError("obligation_join_context_unknown")


def join_context(joins, fact, params, context, join_effects):
    extra: dict = {}
    for join in joins:
        evidence = join_effects[join.alias]
        limit = {"before": fact.expected_revision, "not_after": fact.applied_revision}.get(join.timing)
        matched, unknown = [], not evidence.complete
        for other in evidence.effects:
            if type(other.applied_revision) is not int:
                unknown = True
                continue
            if limit is not None and other.applied_revision > limit:
                continue
            if other.status != "qualified" or other.params_json is None:
                unknown = True
                continue
            other_params = json.loads(other.params_json)
            result = evaluate_predicate(join.where, context | {"effect": params, "joined": other_params})
            if result.value is None:
                unknown = True
            elif result.value:
                matched.append((other.applied_revision, other_params))
        if join.match == "any" and matched:
            unknown = False
            matched = [min(matched, key=lambda item: item[0])]
        if unknown or len(matched) > 1:
            continue
        extra.setdefault("join", {})[join.alias] = "matched" if matched else "none"
        if matched:
            extra.setdefault("joined", {})[join.alias] = matched[0][1]
    return extra


