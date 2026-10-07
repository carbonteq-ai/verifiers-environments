"""Links from an evaluated effect to effects of another declared effect source.

Shared by occurrence obligations and guards ("generated-object relationships":
an update must target the record the agent created; an action must follow a
read). Join outcomes are data: ``join.<alias>`` is ``matched``/``none`` and
``joined.<alias>`` the linked effect's params; anything undecidable is absent.
"""

import json
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import FrozenModel, Identifier
from .execution_order import ExecutionRelation, execution_relation
from .predicates import Predicate, evaluate_predicate, parse_predicate
from .predicates import context_paths as _fields


class EffectJoin(FrozenModel):
    """Link a matched effect to an earlier effect of another declared source.

    For each effect evaluated by ``effect_match``, qualified facts of
    ``source`` committed before the effect started (``before``), no later than
    it committed (``not_after``), strictly after it committed (``after``: a
    later correction or restoration) or at any time (``any``) are tested with
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
    timing: Literal["before", "not_after", "after", "any"] = "not_after"
    match: Literal["unique", "any"] = "unique"

    @field_validator("where", mode="before")
    @classmethod
    def predicate(cls, value):
        return parse_predicate(value)

    # Execution-order relation (contracts/execution_order.py), separate from the
    # state-revision ``timing``: ``returned_before_dispatch`` (the joined call's
    # response was returned before this call was dispatched) or ``overlapping``
    # (both calls' server execution intervals intersect). Requires
    # ``timing: "any"`` so revision order and receipt order are never mixed.
    order: ExecutionRelation | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def order_uses_receipts_only(self):
        if self.order is not None and self.timing != "any":
            raise ValueError("join_order_requires_timing_any")
        return self


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


def _in_timing_window(timing, fact, applied_revision):
    """Whether a joined effect committed at ``applied_revision`` is eligible.

    ``before``: committed no later than the evaluated effect started;
    ``not_after``: no later than it committed; ``after``: strictly after it
    committed; ``any``: always.
    """
    if timing == "before":
        return applied_revision <= fact.expected_revision
    if timing == "not_after":
        return applied_revision <= fact.applied_revision
    if timing == "after":
        return applied_revision > fact.applied_revision
    return True


def join_context(joins, fact, params, context, join_effects):
    extra: dict = {}
    for join in joins:
        evidence = join_effects[join.alias]
        matched, unknown = [], not evidence.complete
        for other in evidence.effects:
            ordered = execution_relation(join.order, getattr(join_effects, "execution_order", None),
                                         fact, other) if join.order else True
            if ordered is False:
                continue
            if type(other.applied_revision) is not int:
                unknown = True
                continue
            if not _in_timing_window(join.timing, fact, other.applied_revision):
                continue
            if other.status != "qualified" or other.params_json is None:
                unknown = True
                continue
            other_params = json.loads(other.params_json)
            result = evaluate_predicate(join.where, context | {"effect": params, "joined": other_params})
            if result.value is None:
                unknown = True
            elif result.value and ordered is None:
                unknown = True  # matches ``where`` but its execution order is undecidable
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


