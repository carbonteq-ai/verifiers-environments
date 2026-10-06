"""Clock, identifiers and randomness for simulated service calls.

Outside :func:`simulated_call` every function here behaves exactly like the
standard library call it replaces: the real clock, OS-random UUIDs and the
global ``random`` generator. Inside it, a host can make one service call
deterministic: the clock reads a fixed instant that advances by one
microsecond per reading, and identifiers and random choices come from a
generator seeded for that call. Two simulations that make the same call
against the same world then return byte-identical results.
"""

from __future__ import annotations

import contextvars
import random as _random
import uuid as _uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo


@dataclass
class _Call:
    clock: datetime
    rng: _random.Random
    readings: int = field(default=0)


_CALL: contextvars.ContextVar[_Call | None] = contextvars.ContextVar(
    "automationbench_simulated_call", default=None
)


@contextmanager
def simulated_call(seed: str, clock: datetime) -> Iterator[None]:
    """Make clock, identifier and random reads in this context deterministic.

    ``clock`` is the instant of the call; an aware value is converted to UTC and
    a naive one is taken as UTC.
    """

    instant = clock.astimezone(timezone.utc) if clock.tzinfo else clock.replace(tzinfo=timezone.utc)
    token = _CALL.set(_Call(instant, _random.Random(seed)))
    try:
        yield
    finally:
        _CALL.reset(token)


def active() -> bool:
    """Whether the current context is a deterministic simulated call."""

    return _CALL.get() is not None


def _reading(call: _Call) -> datetime:
    call.readings += 1
    return call.clock + timedelta(microseconds=call.readings)


def now(tz: tzinfo | None = None) -> datetime:
    """``datetime.now(tz)``; naive readings are UTC wall time."""

    call = _CALL.get()
    if call is None:
        return datetime.now(tz)
    instant = _reading(call)
    return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)


def utcnow() -> datetime:
    """``datetime.utcnow()``."""

    call = _CALL.get()
    if call is None:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    return _reading(call).replace(tzinfo=None)


def today() -> date:
    """``date.today()``."""

    return now().date()


def time() -> float:
    """``time.time()``."""

    return now(timezone.utc).timestamp()


def uuid4() -> _uuid.UUID:
    """``uuid.uuid4()``."""

    call = _CALL.get()
    if call is None:
        return _uuid.uuid4()
    return _uuid.UUID(int=call.rng.getrandbits(128), version=4)


def rng() -> _random.Random:
    """The generator behind ``random.<function>`` calls (the module's global one outside a call)."""

    call = _CALL.get()
    return call.rng if call is not None else _random._inst  # type: ignore[attr-defined]


__all__ = ["active", "now", "rng", "simulated_call", "time", "today", "utcnow", "uuid4"]
