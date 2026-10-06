"""Deterministic simulated worlds: equal actions on equal worlds give equal results.

AutomationBench stamps records with the wall clock and mints identifiers from OS
randomness, so two attempts that make the same call see different tool results
(timestamps, message and record ids). SAMPO compares turns whose preceding
observations are identical; those volatile values made about one turn in five a
singleton with no comparable sibling (r5, collection 52: 57.7% singleton turns,
45.8% once timestamps and minted ids are masked).

With ``deterministic_world`` the simulator's clock, identifiers and random
choices (``automationbench.sim_runtime``) are fixed per call:

- the world clock starts at the task's own ``meta.current_time``, or at UTC
  midnight of the day the episode is set up when the task declares none, and
  advances one second per call that changed the world (reads do not advance it);
- each call's identifiers and random choices come from a generator seeded by the
  world before the call and the call itself (tool name and arguments).

Two attempts that reach the same world and make the same call therefore receive
byte-identical results, whatever reads they made on the way. A repeated create
sees a different world (the first record exists) and so mints a new identifier.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from automationbench import sim_runtime

from .capture import canonical_json

SIMULATION_VERSION = "deterministic-world@1"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def world_clock_base(initial_state: Mapping[str, Any], *, today: datetime | None = None) -> datetime:
    """The task's declared ``meta.current_time``, else UTC midnight of ``today``."""

    declared = (initial_state.get("meta") or {}).get("current_time")
    if declared:
        instant = datetime.fromisoformat(str(declared))
        return instant if instant.tzinfo else instant.replace(tzinfo=UTC)
    day = (today or datetime.now(UTC)).astimezone(UTC)
    return day.replace(hour=0, minute=0, second=0, microsecond=0)


@contextmanager
def simulated_setup(initial_state: Mapping[str, Any], clock: datetime) -> Iterator[None]:
    """World construction (schema defaults) at the world clock, seeded by the initial state."""

    seed = _digest([SIMULATION_VERSION, "setup", initial_state])
    with sim_runtime.simulated_call(seed, clock):
        yield


@contextmanager
def simulated_tool_call(state: Any, tool_name: str, arguments: Any) -> Iterator[None]:
    """One tool call at the world clock, seeded by the world before it and the call.

    A no-op unless the rollout selected ``deterministic_world``. The clock advances
    after the call only when the call changed the world.
    """

    if not getattr(state, "deterministic_world", False):
        yield
        return
    if state.world_clock is None:
        raise ValueError("deterministic world has no clock; setup did not pin it")
    before = state.world
    seed = _digest([SIMULATION_VERSION, _digest(before), tool_name, arguments])
    clock = datetime.fromisoformat(state.world_clock) + timedelta(seconds=state.world_revision)
    with sim_runtime.simulated_call(seed, clock):
        yield
    if state.world is not before and state.world != before:
        state.world_revision += 1


__all__ = [
    "SIMULATION_VERSION",
    "simulated_setup",
    "simulated_tool_call",
    "world_clock_base",
]
