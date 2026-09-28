"""Round-trip AutomationBench's world through JSON without losing private state.

The adapter keeps the world as JSON in the Verifiers state and rebuilds it for
every tool call and for scoring. Upstream AutomationBench keeps one live
``WorldState`` per episode, and Google Sheets records which rows a tool
updated on a private attribute (``_updated_row_keys``) that
``google_sheets_row_updated`` / ``google_sheets_row_not_updated`` assertions
read. A plain ``model_dump``/``model_validate`` round trip drops it, so those
assertions saw no updates at all. The record travels under one reserved key.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from automationbench.schema.world import WorldState

PRIVATE_KEY = "_automationbench_v1_private"
_SHEETS_UPDATED_ROWS = "google_sheets_updated_row_keys"


def load_world(data: Mapping[str, Any]) -> WorldState:
    """Rebuild a world, restoring the private state `dump_world` carried."""

    values = dict(data)
    private = values.pop(PRIVATE_KEY, None) or {}
    world = WorldState.model_validate(values)
    updated = private.get(_SHEETS_UPDATED_ROWS)
    if updated:
        object.__setattr__(world.google_sheets, "_updated_row_keys", set(updated))
    return world


def dump_world(world: WorldState) -> dict[str, Any]:
    """Serialize a world as JSON, keeping the private state scoring needs."""

    data = world.model_dump(mode="json")
    data.pop("_updated_row_keys", None)
    updated = getattr(world.google_sheets, "_updated_row_keys", None)
    if updated:
        data[PRIVATE_KEY] = {_SHEETS_UPDATED_ROWS: sorted(updated)}
    return data


__all__ = ["PRIVATE_KEY", "dump_world", "load_world"]
