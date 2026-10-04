"""Environment-local world evidence, separate from business success and rewards.

    The caller supplies a native validated, source-bound snapshot. These working
values are not a second persisted trace format or generated-token coordinates.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from .capture import CapturedAction


@dataclass(frozen=True)
class WorldTransition:
    origin: str
    invocation_id: str
    action: CapturedAction | None
    before_json: str | None
    after_json: str | None
    evidence_status: Literal["acknowledged", "unavailable"]
    reason: str
    expected_revision: int | None = None
    applied_revision: int | None = None

    @property
    def changed_services(self) -> tuple[str, ...]:
        """Observed differences; a service difference is not business success."""
        if self.before_json is None or self.after_json is None:
            return ()
        before, after = json.loads(self.before_json), json.loads(self.after_json)
        return tuple(
            sorted(
                key
                for key in set(before) | set(after)
                if key != "meta" and before.get(key) != after.get(key)
            )
        )


def world_transitions(source: dict) -> tuple[WorldTransition, ...]:
    """Retain every occurrence, including failed calls and unacknowledged deltas.

    Returned status and a persistence acknowledgement only establish captured
    world evidence. Domain adapters must inspect the business result, identities,
    policy and actual changes. Pending calls stay unavailable at their cutoff.
    Values remain scoped to this input trace and cutoff; tuple order does not
    prove a serial order of concurrent effects. An empty tuple does not prove
    complete observation coverage or that a guard passed.
    """
    writes = {}
    for write in source.get("state_write_receipts", []):
        identity = write["write_id"]
        if identity in writes:
            raise ValueError("duplicate_state_write_identity")
        writes[identity] = write
    observations = {}
    for event in source.get("tool_execution_events", []):
        origin = event["source"]
        receipt = json.loads(event["receipt_json"])
        key = (origin, receipt["invocation_id"])
        phase = receipt["phase"]
        previous = observations.get(key)
        if previous is not None and (previous["phase"] != "dispatch" or phase == "dispatch"):
            raise ValueError("duplicate_execution_lifecycle")
        observations[key] = receipt
    result = []
    for (origin, invocation), receipt in observations.items():
        reason = "acknowledged_world_evidence"
        ack = writes.get(invocation)
        if origin != "tool_server":
            reason = "unsupported_execution_origin"
        elif receipt["phase"] == "dispatch":
            reason = "pending_execution_at_cutoff"
        elif receipt["phase"] != "returned":
            reason = "execution_did_not_return"
        elif not ack:
            reason = "state_acknowledgement_missing"
        elif receipt.get("state_conflict") or ack.get("conflict"):
            reason = "state_write_conflict"
        elif receipt.get("state_persistence") != "applied":
            reason = "state_persistence_unqualified"
        elif any(
            type(value) is not int or value < 0
            for value in (
                ack.get("expected_revision"),
                ack.get("applied_revision"),
                receipt.get("state_read_revision"),
                receipt.get("state_write_revision"),
            )
        ):
            reason = "state_revision_unavailable"
        elif ack.get("expected_revision") != receipt.get("state_read_revision") or ack.get(
            "applied_revision"
        ) != receipt.get("state_write_revision"):
            reason = "state_revision_mismatch"
        envelopes = [json.loads(item) for item in receipt.get("evidence_json", [])]
        captures = [item for item in envelopes if item.get("kind") == "automationbench_raw_action"]
        if len(captures) > 1:
            raise ValueError("ambiguous_execution_capture")
        action = None
        worlds = [None, None]
        if captures:
            envelope = captures[0]
            action = CapturedAction.model_validate(envelope["action"])
            for index, digest in enumerate((action.before_digest, action.after_digest)):
                text = envelope["snapshots"][digest]
                if hashlib.sha256(text.encode()).hexdigest() != digest:
                    raise ValueError("snapshot_digest_mismatch")
                if not isinstance(json.loads(text), dict):
                    raise ValueError("world_snapshot_must_be_object")  # noqa: TRY004
                worlds[index] = text
        elif reason == "acknowledged_world_evidence":
            reason = "world_capture_missing"
        result.append(
            WorldTransition(
                origin,
                invocation,
                action,
                worlds[0],
                worlds[1],
                "acknowledged" if reason == "acknowledged_world_evidence" else "unavailable",
                reason,
                (ack or {}).get("expected_revision"),
                (ack or {}).get("applied_revision"),
            )
        )
    return tuple(result)


def _unpersisted(source: dict) -> set[tuple[str, str]]:
    """Terminal calls that provably persisted no world change.

    A tool-server call that raised before running (the runtime requires
    ``state_persistence: not_attempted`` and no write revision for raised
    receipts), or returned with ``not_attempted``/``unchanged`` persistence, and
    has no state-write acknowledgement consumed no revision. The remaining
    acknowledged calls must still form a revision- and world-linked chain, so
    an unpersisted call that changed the live world breaks that chain instead
    of hiding an effect.
    """
    acknowledged = {write["write_id"] for write in source.get("state_write_receipts", [])}
    terminal = {}
    for event in source.get("tool_execution_events", []):
        receipt = json.loads(event["receipt_json"])
        if receipt.get("phase") != "dispatch":
            terminal[event["source"], receipt["invocation_id"]] = receipt
    return {
        key for key, receipt in terminal.items()
        if key[0] == "tool_server" and key[1] not in acknowledged
        and receipt.get("phase") in ("raised", "returned")
        and receipt.get("state_persistence") in ("not_attempted", "unchanged")
        and receipt.get("state_write_revision") is None and not receipt.get("state_conflict")
    }


def persisted_transitions(source: dict) -> tuple[WorldTransition, ...]:
    """``world_transitions`` without calls that provably persisted nothing."""
    skipped = _unpersisted(source)
    return tuple(item for item in world_transitions(source) if (item.origin, item.invocation_id) not in skipped)


def observation_transitions(source: dict) -> tuple[WorldTransition, ...]:
    """Retain returned calls even when they persisted no state change.

    Reading is observable independently of mutation. A returned call without
    an acknowledgement must remain in the inventory so read adapters can
    report unavailable evidence, rather than certify an empty inventory.
    Only terminal raised calls proven not to have persisted anything are
    omitted, as they supplied no successful return.
    """
    unpersisted = _unpersisted(source)
    skipped = set()
    for event in source.get("tool_execution_events", []):
        receipt = json.loads(event["receipt_json"])
        key = event["source"], receipt["invocation_id"]
        if key in unpersisted and receipt.get("phase") == "raised":
            skipped.add(key)
    return tuple(item for item in world_transitions(source) if (item.origin, item.invocation_id) not in skipped)
