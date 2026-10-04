"""Closed populations published to ``exists`` predicates of a check.

``{"op": "exists", "population": <source>, "where": ...}`` asks whether some
row of a declared initial population satisfies ``where`` (which also reads the
current effect and candidate context). Only a closed, enumerated population is
published; anything else stays absent so the predicate is unknown, never a
silent false.
"""

import json
from collections.abc import Mapping

from .predicates import EXISTS_CONTEXT, exists_populations


def exists_names(check) -> frozenset[str]:
    """Every population an ``exists`` predicate of ``check`` reads."""
    return frozenset(exists_populations(check.model_dump(mode="json")))


def exists_context(names, populations: Mapping) -> dict:
    if not names:
        return {}
    members = {}
    for name in sorted(names):
        population = populations[name]
        if population.closed and population.enumerated:
            members[name] = tuple(json.loads(row.cells_json) for row in population.rows)
    return {EXISTS_CONTEXT: members}


def exists_size(context: Mapping) -> int:
    return sum(len(rows) for rows in context.get(EXISTS_CONTEXT, {}).values())
