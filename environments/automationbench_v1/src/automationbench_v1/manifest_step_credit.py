"""Manifest findings as per-step credit inside Posttrain's turn evidence.

The episode reward stays the official partial credit. When a turn-reward
config selects manifest weights, each sampled assistant turn (one step: its
reasoning and its tool calls) additionally receives:

- goal credit: ``manifest_goal_share / R`` for every required manifest goal
  finding that passed (value 1) whose earliest witnessing tool invocation was
  issued by that turn, where ``R`` is the number of decided required goal
  findings in the episode (so an episode's goal credit is at most the share);
- harm debit: ``manifest_harm_penalty`` for every distinct (check, invocation)
  harm violation issued by that turn, applied in turn order until the episode's
  ``manifest_harm_cap`` is reached.

Unknown or abstained findings contribute nothing. Tool invocations are mapped
to turns by matching each tool-server dispatch, in order, to the next sampled
tool call with the same name and arguments (transport retries map to the same
call). If any dispatch cannot be matched, no manifest credit is applied to the
episode and every turn records ``manifest_mapped = 0``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .manifest_guard_assessments import GUARD_OUTPUT
from .manifest_obligation_assessments import OBLIGATION_OUTPUT
from .turn_rewards import TURN_REWARD, AutomationBenchTurnRewardConfig


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _arguments(call: Any) -> Any:
    raw = getattr(call, "arguments", None)
    if raw is None and isinstance(call, Mapping):
        raw = call.get("arguments")
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except ValueError:
            return raw
    return raw if raw is not None else {}


def _name(call: Any) -> str:
    name = getattr(call, "name", None)
    if name is None and isinstance(call, Mapping):
        name = call.get("name") or (call.get("function") or {}).get("name")
    return str(name or "")


def invocation_turns(turns: Sequence[Any], events: Sequence[Any]) -> dict[str, int] | None:
    """Map tool-server invocation ids to assistant turn indexes, or None if ambiguous."""

    calls = [
        (index, _name(call), _canonical(_arguments(call)))
        for index, message in enumerate(turns)
        for call in (getattr(message, "tool_calls", None) or [])
    ]
    dispatches = []
    for event in events:
        data = event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)
        if data.get("source") != "tool_server" or data.get("phase") != "dispatch":
            continue
        receipt = json.loads(data["receipt_json"])
        arguments = json.loads(receipt.get("arguments_json") or "{}")
        kwargs = arguments.get("kwargs", arguments) if isinstance(arguments, Mapping) else arguments
        dispatches.append((data.get("receipt_seq", 0), data["invocation_id"], receipt.get("tool_name", ""),
                           _canonical(kwargs), receipt.get("transport_attempt_index") or 0))
    dispatches.sort(key=lambda item: item[0])
    mapping: dict[str, int] = {}
    position = 0
    last: tuple[str, str, int] | None = None
    for _, invocation, tool, arguments, attempt in dispatches:
        if attempt and last is not None and last[:2] == (tool, arguments):
            mapping[invocation] = last[2]  # a transport retry of the previous call
            continue
        while position < len(calls):
            index, name, called = calls[position]
            position += 1
            if (name == tool or name.endswith(("__" + tool, "." + tool))) and called == arguments:
                mapping[invocation] = index
                last = (tool, arguments, index)
                break
        else:
            return None
    return mapping


def _latest_payloads(trace: Any, kind: str) -> list[dict[str, Any]]:
    """Distinct payloads of one receipt kind across complete assessment batches.

    A producer emits one complete batch per check; rescoring repeats identical
    receipts, which are de-duplicated."""

    payloads, seen = [], set()
    for batch in getattr(trace, "assessment_batches", ()) or ():
        if batch.run.status != "complete":
            continue
        for receipt in batch.run.execution_evidence:
            if getattr(receipt, "kind", None) != kind:
                continue
            payload = json.loads(receipt.payload_json)
            key = _canonical(payload)
            if key not in seen:
                seen.add(key)
                payloads.append(payload)
    return payloads


def manifest_outcomes(trace: Any) -> tuple[list[str], int, list[tuple[str, str]]]:
    """(earliest goal witness occurrences, decided required goal count, harm (check, occurrence))."""

    goal_occurrences, required = [], 0
    for payload in _latest_payloads(trace, OBLIGATION_OUTPUT):
        if payload.get("kind") != "finding" or payload.get("required") is not True:
            continue
        if payload.get("status") != "valid":
            continue
        required += 1
        if payload.get("value") == 1:
            witnesses = payload.get("witnesses") or []
            if witnesses:
                earliest = min(witnesses, key=lambda item: (item.get("applied_revision", 0), item["occurrence"]))
                goal_occurrences.append(earliest["occurrence"])
    harms = sorted({
        (payload["check_id"], payload["occurrence"])
        for payload in _latest_payloads(trace, GUARD_OUTPUT)
        if payload.get("kind") == "finding" and payload.get("status") == "valid"
        and payload.get("value") == 1 and payload.get("occurrence")
    })
    return goal_occurrences, required, harms


def apply_manifest_step_credit(
    evidence: dict[str, Any],
    *,
    turns: Sequence[Any],
    events: Sequence[Any],
    trace: Any,
    config: AutomationBenchTurnRewardConfig,
) -> dict[str, Any]:
    """Return turn evidence with manifest goal/harm components added to each turn."""

    assessments = evidence.get("assessments") or []
    goal_share = config.manifest_goal_share or 0.0
    harm_penalty = config.manifest_harm_penalty or 0.0
    goal_occurrences, required, harms = manifest_outcomes(trace)
    mapping = invocation_turns(turns, events) if (goal_occurrences or harms) else {}
    mapped = mapping is not None
    goals_by_turn = [0] * len(assessments)
    harms_by_turn = [0] * len(assessments)
    if mapped:
        for occurrence in goal_occurrences:
            index = mapping.get(occurrence)
            if index is not None and index < len(assessments):
                goals_by_turn[index] += 1
        for _, occurrence in harms:
            index = mapping.get(occurrence)
            if index is not None and index < len(assessments):
                harms_by_turn[index] += 1
    remaining = config.manifest_harm_cap
    updated = []
    for index, assessment in enumerate(assessments):
        goal_credit = goal_share * goals_by_turn[index] / required if (mapped and required) else 0.0
        harm_debit = min(remaining, harm_penalty * harms_by_turn[index]) if mapped else 0.0
        remaining -= harm_debit
        previous = {c["name"]: c["value"] for c in assessment["components"]}
        # Rescoring re-derives manifest credit from the turn's base reward.
        base_shift = previous.get("manifest_goal_credit", 0.0) - previous.get("manifest_harm_debit", 0.0)
        components = []
        for component in assessment["components"]:
            if component["name"].startswith("manifest_"):
                continue
            if component["name"] == TURN_REWARD:
                base = component["value"] - base_shift
                component = {**component, "value": base + goal_credit - harm_debit}
            components.append(component)
        components += [
            {"name": "manifest_goals", "status": "valid", "value": float(goals_by_turn[index])},
            {"name": "manifest_harms", "status": "valid", "value": float(harms_by_turn[index])},
            {"name": "manifest_goal_credit", "status": "valid", "value": goal_credit},
            {"name": "manifest_harm_debit", "status": "valid", "value": harm_debit},
            {"name": "manifest_mapped", "status": "valid", "value": 1.0 if mapped else 0.0},
        ]
        updated.append({**assessment, "components": components})
    return {**evidence, "assessments": updated}


__all__ = ["apply_manifest_step_credit", "invocation_turns", "manifest_outcomes"]
