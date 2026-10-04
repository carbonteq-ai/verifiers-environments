"""Inspect retained invocation evidence without inferring turn or token causality."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import verifiers.v1 as vf

from ..capture import CapturedAction, canonical_json


@dataclass(frozen=True)
class ActionEvidence:
    trace_id: str
    invocation_id: str
    evidence_index: int
    action: CapturedAction
    snapshots: dict[str, str]
    persistence: str
    conflict: bool | None
    # This is an authenticated server invocation, not a sampled native call ID.


@dataclass(frozen=True)
class CaptureInspection:
    actions: tuple[ActionEvidence, ...]
    observed_invocations: int
    unavailable_reasons: tuple[str, ...]

    @property
    def observed_invocations_complete(self) -> bool:
        """Only observed dispatch coverage, never proof every agent call was captured."""
        return self.observed_invocations > 0 and not self.unavailable_reasons


def inspect_capture(episode: vf.WireEpisode) -> CaptureInspection:
    """Use independent receipts; final synchronized-state indexes are not authority.

    Missing evidence is unavailable. Corrupt evidence raises rather than becoming
    a zero reward. Final world/score remains a separate native episode concern.
    """
    actions = []
    reasons = []
    observed = 0
    for trace in episode.traces:
        invocations: dict[str, list[dict]] = {}
        for event in trace.tool_execution_events:
            if event.source == "tool_server":
                record = event.model_dump(mode="json")
                receipt = json.loads(record["receipt_json"])
                invocations.setdefault(record["invocation_id"], []).append(receipt)
        for invocation_id, receipts in invocations.items():
            observed += 1
            prefix = f"{trace.id}:{invocation_id}"
            dispatch = [item for item in receipts if item["phase"] == "dispatch"]
            terminal = [item for item in receipts if item["phase"] != "dispatch"]
            if len(dispatch) != 1 or len(terminal) != 1:
                reasons.append(f"{prefix}:incomplete_receipt_pair")
                continue
            receipt = terminal[0]
            found = False
            for index, encoded in enumerate(receipt["evidence_json"]):
                raw = json.loads(encoded)
                if not isinstance(raw, dict) or raw.get("kind") != "automationbench_raw_action":
                    continue
                found = True
                if set(raw) != {"kind", "action", "snapshots"}:
                    raise ValueError("raw action evidence has unexpected fields")
                action = CapturedAction.model_validate(raw["action"])
                snapshots = raw["snapshots"]
                if not isinstance(snapshots, dict) or set(snapshots) != {
                    action.before_digest,
                    action.after_digest,
                }:
                    raise ValueError("raw action evidence lacks its referenced snapshots")
                for digest, snapshot in snapshots.items():
                    if not isinstance(snapshot, str) or (
                        hashlib.sha256(snapshot.encode()).hexdigest() != digest
                        or canonical_json(json.loads(snapshot)) != snapshot
                    ):
                        raise ValueError("raw action snapshot bytes are corrupt or noncanonical")
                if canonical_json(json.loads(action.arguments_json)) != action.arguments_json:
                    raise ValueError("raw action arguments are noncanonical")
                actions.append(
                    ActionEvidence(
                        trace.id,
                        invocation_id,
                        index,
                        action,
                        snapshots,
                        receipt["state_persistence"],
                        receipt["state_conflict"],
                    )
                )
            if not found:
                reasons.append(f"{prefix}:raw_action_evidence_missing")
    if observed == 0:
        reasons.append("no_observed_tool_server_invocations")
    return CaptureInspection(tuple(actions), observed, tuple(reasons))
