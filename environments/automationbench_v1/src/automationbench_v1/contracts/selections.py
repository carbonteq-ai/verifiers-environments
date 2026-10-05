"""Candidate-relative selections and alternative effect channels.

Shared by obligations and guards; see ``SelectionAlias`` and ``AlternativeEffect``.
"""

import json
from fractions import Fraction
from typing import Literal

from pydantic import Field, StrictInt, field_validator, model_validator

from .base import FrozenModel, Identifier
from .predicates import FieldValue, Predicate, evaluate_predicate, parse_predicate, resolve_operand
from .values import ValueExpression, evaluate_value, parse_value


class OrderKey(FrozenModel):
    source_position: Literal["source_path_index"] | None = Field(default=None, exclude_if=lambda value: value is None)
    value: ValueExpression | None = Field(default=None, exclude_if=lambda value: value is None)
    text: FieldValue | None = Field(default=None, exclude_if=lambda value: value is None)
    collation: Literal["ascii_casefold", "unicode_codepoint"] | None = Field(
        default=None, exclude_if=lambda value: value is None)
    direction: Literal["asc", "desc"]

    @field_validator("value", mode="before")
    @classmethod
    def expression(cls, value):
        return None if value is None else parse_value(value)

    @model_validator(mode="after")
    def key_shape(self):
        if sum(item is not None for item in (self.value, self.text, self.source_position)) != 1:
            raise ValueError("selection_order_requires_exactly_one_value_or_text")
        if (self.text is not None) != (self.collation is not None):
            raise ValueError("selection_text_order_requires_explicit_collation")
        if self.text is not None and self.text.domain != "string":
            raise ValueError("selection_text_order_requires_string_domain")
        return self


class AlternativeEffect(FrozenModel):
    """Another channel that can satisfy the obligation (e.g. Slack instead of Gmail).

    A qualified effect of ``source`` matching ``effect_match`` witnesses the
    obligation exactly like the primary source. A known zero requires every
    listed source's inventory to be complete.
    """

    alias: Identifier
    source: Identifier
    effect_match: Predicate

    @field_validator("effect_match", mode="before")
    @classmethod
    def predicate(cls, value):
        return parse_predicate(value)


class SelectionAlias(FrozenModel):
    """Eligibility-first choice of one member, relative to the current candidate.

    ``where`` reads ``member.*`` plus the candidate context (``request``,
    lookups, ``lookup``) and earlier selections (``selected``/``selection``).
    The best member under ``order_by`` (lexicographic) is published as
    ``selected.<alias>`` with ``selection.<alias> == "selected"``; no eligible
    member publishes ``selection.<alias> == "none"``. Unknown eligibility, an
    unavailable or mixed-type ordering key, a tie, or an open/duplicate
    population leave both absent, so dependent predicates are unknown.
    Cross-candidate capacity (one member per candidate) is not modelled here.
    """

    alias: Identifier
    population: Identifier
    where: Predicate
    order_by: tuple[OrderKey, ...] = Field(min_length=1, max_length=4)
    ties: Literal["unavailable"] = "unavailable"
    max_members: StrictInt = Field(default=4096, ge=1, le=65536)

    @field_validator("where", mode="before")
    @classmethod
    def predicate(cls, value):
        return parse_predicate(value)


def _order_key(results):
    key = []
    for result in results:
        if result.status != "qualified" or result.kind not in {"decimal", "calendar_date", "day_count"}:
            return None
        value = result.canonical_value
        key.append((result.kind, Fraction(str(value)) if result.kind == "decimal" else value))
    return tuple(key)


def _selection_key(orders, context, source_path=()):
    key = []
    for order in orders:
        if order.source_position is not None:
            if not source_path or type(source_path[-1]) is not int or source_path[-1] < 0:
                return None
            key.append(("source_position", Fraction(source_path[-1])))
            continue
        if order.text is None:
            numeric = _order_key([evaluate_value(order.value, context)])
            if numeric is None:
                return None
            key.extend(numeric)
            continue
        known, value, _ = resolve_operand(order.text, context)
        # No implicit locale, whitespace trimming or fallback from unread text.
        if (not known or type(value) is not str or not value or len(value) > 1024
                or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            return None
        if order.collation == "ascii_casefold":
            if not value.isascii():
                return None
            value = value.casefold()
        key.append(("text:" + order.collation, value))
    return tuple(key)


def _select(selection, outer, population):
    """Return ("selected", cells) / ("none", None), or None when undecidable."""
    rows = population.rows
    if (not population.closed or not population.enumerated or len(rows) > selection.max_members
            or len({row.identity for row in rows}) != len(rows)):
        return None
    # Positions are comparable only within one captured collection. Never
    # substitute row IDs, cell values or iteration order for provenance.
    if (any(order.source_position is not None for order in selection.order_by)
            and len({row.source_path[:-1] for row in rows}) > 1):
        return None
    ranked = []
    for row in rows:
        member = json.loads(row.cells_json)
        context = {**outer, "member": member}
        eligible = evaluate_predicate(selection.where, context).value
        if eligible is None:
            return None
        if not eligible:
            continue
        key = _selection_key(selection.order_by, context, row.source_path)
        if key is None:
            return None
        ranked.append((key, member))
    if not ranked:
        return "none", None
    if len({tuple(kind for kind, _ in key) for key, _ in ranked}) != 1:
        return None  # mixed key types cannot be ordered
    best_key, best_member, count = ranked[0][0], ranked[0][1], 1
    for key, member in ranked[1:]:
        comparison = _better(key, best_key, selection.order_by)
        if comparison > 0:
            best_key, best_member, count = key, member, 1
        elif comparison == 0:
            count += 1
    return None if count > 1 else ("selected", best_member)


def _better(left, right, order_by):
    for (_, a), (_, b), order in zip(left, right, order_by, strict=True):
        if a != b:
            greater = a > b
            return 1 if greater == (order.direction == "desc") else -1
    return 0


def publish_selections(selections, context, populations):
    """Add ``selection.<alias>`` / ``selected.<alias>`` for decided selections."""
    for selection in selections:
        outcome = _select(selection, context, populations[selection.population])
        if outcome is not None:
            status, member = outcome
            context.setdefault("selection", {})[selection.alias] = status
            if member is not None:
                context.setdefault("selected", {})[selection.alias] = member
    return context
