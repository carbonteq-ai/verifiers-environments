"""Authenticated tool-server execution order for effect joins.

State revisions order *state*: a read whose revision precedes an action's
proves the action ran on later state, not that the read's response had been
returned before the action was dispatched, nor whether two calls ran
concurrently. The native trace retains every tool-server lifecycle event in one
receipt sequence (``receipt_seq`` equals the event's index; the native source
is sealed and re-admitted before assessment). Each invocation has one
``dispatch`` event (``event_index`` 0) and, once it ends, one terminal event
(``event_index`` 1: ``returned``, ``raised`` or ``interrupted``).

Two relations are derived, and nothing else:

- ``returned_before_dispatch``: the joined invocation's ``returned`` event
  precedes the evaluated invocation's ``dispatch`` event. This is the
  server-boundary fact "the response had been returned before the action was
  requested". It says nothing about whether, or how, the model used the
  response (model conditioning is not evidenced by receipts), and nothing
  about the content returned (read adapters qualify content separately).
- ``overlapping``: both invocations ended and each was dispatched before the
  other's terminal event (their server execution intervals intersect). A
  serialising server yields disjoint intervals even when the model emitted the
  calls in one turn; model-level co-issuance is not evidenced here.

Missing, malformed or contradictory order evidence (gaps, duplicates, a
terminal without a dispatch, a pending invocation, a fact without a tool-server
invocation) is unknown, never a decided relation.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

ExecutionRelation = Literal["returned_before_dispatch", "overlapping"]


@dataclass(frozen=True)
class InvocationBounds:
    dispatch_seq: int
    terminal_seq: int | None
    terminal_phase: str | None


@dataclass(frozen=True)
class ExecutionOrder:
    bounds: Mapping[str, InvocationBounds]
    available: bool
    reason: str


def capture_execution_order(source: Mapping) -> ExecutionOrder:
    """Per-invocation dispatch/terminal receipt positions, or unavailable."""
    try:
        events = source["tool_execution_events"]
        if not isinstance(events, (list, tuple)):
            raise TypeError("execution_order_events_missing")
        dispatch: dict[str, int] = {}
        terminal: dict[str, tuple[int, str]] = {}
        for index, event in enumerate(events):
            if not isinstance(event, Mapping) or event.get("receipt_seq") != index:
                raise ValueError("execution_order_sequence_invalid")
            if event.get("source") != "tool_server":
                continue
            receipt = json.loads(event["receipt_json"])
            invocation, phase, ordinal = (
                event.get("invocation_id"),
                event.get("phase"),
                event.get("event_index"),
            )
            if (
                not isinstance(invocation, str)
                or not invocation
                or receipt.get("invocation_id") != invocation
                or receipt.get("phase") != phase
                or receipt.get("event_index") != ordinal
            ):
                raise ValueError("execution_order_receipt_identity_invalid")
            if phase == "dispatch" and ordinal == 0 and invocation not in dispatch:
                dispatch[invocation] = index
            elif (
                phase in ("returned", "raised", "interrupted")
                and ordinal == 1
                and invocation in dispatch
                and invocation not in terminal
            ):
                terminal[invocation] = (index, phase)
            else:
                raise ValueError("execution_order_lifecycle_invalid")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return ExecutionOrder({}, False, str(error))
    bounds = {
        invocation: InvocationBounds(seq, *terminal.get(invocation, (None, None)))
        for invocation, seq in dispatch.items()
    }
    return ExecutionOrder(bounds, True, "authenticated_receipt_sequence")


def execution_relation(
    relation: ExecutionRelation, order: ExecutionOrder | None, fact, other
) -> bool | None:
    """Decide ``relation`` between the evaluated ``fact`` and a joined ``other``.

    True/False only from authenticated receipt positions of two distinct
    tool-server invocations; anything undecidable is None.
    """
    if order is None or not order.available:
        return None
    if (
        getattr(fact, "origin", None) != "tool_server"
        or getattr(other, "origin", None) != "tool_server"
    ):
        return None
    own, joined = order.bounds.get(fact.invocation_id), order.bounds.get(other.invocation_id)
    if own is None or joined is None:
        return None
    if fact.invocation_id == other.invocation_id:
        return False  # one call neither precedes nor runs beside itself
    if relation == "returned_before_dispatch":
        # The sequence is gap-free up to the cutoff and contains the evaluated
        # dispatch, so a return not recorded before it did not happen before it
        # (a later or pending return, a raise or an interruption are all False).
        return (
            joined.terminal_seq is not None
            and joined.terminal_seq < own.dispatch_seq
            and joined.terminal_phase == "returned"
        )
    if own.terminal_seq is None or joined.terminal_seq is None:
        return None  # a pending interval has no observed end
    return own.dispatch_seq < joined.terminal_seq and joined.dispatch_seq < own.terminal_seq


class JoinInventory(dict):
    """Join evidence by alias plus the source's authenticated execution order."""

    execution_order: ExecutionOrder | None = None


def with_execution_order(join_effects: Mapping, source: Mapping, joins) -> Mapping:
    """Attach execution order only when some join declares an ordering relation."""
    if not any(getattr(item, "order", None) for item in joins):
        return join_effects
    inventory = JoinInventory(join_effects)
    inventory.execution_order = capture_execution_order(source)
    return inventory
