"""Manifest findings as per-step credit inside Posttrain's turn evidence.

The episode reward stays the official partial credit. When a turn-reward
config selects manifest weights, each sampled assistant turn (one step: its
reasoning and its tool calls) additionally receives:

- goal credit: ``manifest_goal_share / R`` for every required manifest goal
  that passed (value 1) whose earliest witnessing tool invocation was issued by
  that turn, where ``R`` is the number of decided required goals in the episode
  (so an episode's goal credit is at most the share). Required goals are
  obligation findings marked required, witnessed by their earliest witness, and
  record goals, witnessed by the write their manifest credit names;
- harm debit: ``manifest_harm_penalty`` for every distinct (check, invocation)
  harm violation issued by that turn, applied in turn order until the episode's
  ``manifest_harm_cap`` is reached.

With ``manifest_goal_channel: group_relative`` neither is added to ``turn_reward``.
Each turn instead reports one ``manifest_goal/<goal key>`` component per goal it
first witnessed, valued ``manifest_goal_share / R``, and its capped
``manifest_harm_debit``; goal keys (``obligation:<check>:<instance>`` or
``record:<check>``) are equal across attempts at one task, so a trainer can weigh
each goal by how many of a group's attempts reached it.

Unknown or abstained findings contribute nothing. Tool invocations are mapped
to the turn that issued them: each tool-server dispatch names its parent harness
execution, whose event records the assistant node that made the call. Records
without that link fall back to matching each dispatch, in order, to the next
sampled tool call with the same name and arguments (transport retries map to the
same call). If any dispatch cannot be mapped, no manifest credit is applied to
the episode and every turn records ``manifest_mapped = 0``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts.credit import select_credit
from .contracts.engine import Evaluation
from .contracts.loader import load_contract
from .contracts.models import CheckSpec
from .manifest_assessments import OUTPUT_KIND as RECORD_OUTPUT
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


def _event_data(event: Any) -> dict[str, Any]:
    return event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)


def _issuing_turns(events: Sequence[Any], node_turns: Mapping[int, int]) -> dict[str, int] | None:
    """Map invocations through the harness execution that issued them, or None if any is unlinked.

    Each tool-server dispatch names its ``parent_execution_id``; the harness event of that
    execution records the ``node_index`` of the assistant message whose tool call it ran."""

    executions: dict[str, int] = {}
    dispatches: list[tuple[str, str | None]] = []
    for event in events:
        data = _event_data(event)
        if data.get("source") in {"harness", "interceptor"} and isinstance(data.get("node_index"), int):
            executions.setdefault(str(data.get("execution_id")), data["node_index"])
        elif data.get("source") == "tool_server" and data.get("phase") == "dispatch":
            receipt = json.loads(data["receipt_json"])
            dispatches.append((data["invocation_id"], receipt.get("parent_execution_id")))
    mapping: dict[str, int] = {}
    for invocation, parent in dispatches:
        turn = node_turns.get(executions.get(str(parent), -1)) if parent is not None else None
        if turn is None:
            return None
        mapping[invocation] = turn
    return mapping


def invocation_turns(
    turns: Sequence[Any], events: Sequence[Any], node_turns: Mapping[int, int] | None = None
) -> dict[str, int] | None:
    """Map tool-server invocation ids to assistant turn indexes, or None if ambiguous.

    With ``node_turns`` (trace node index -> turn index), every dispatch is mapped to the
    turn that issued it through its harness execution. Records without that link fall back
    to matching dispatches, in order, to sampled calls by tool name and arguments."""

    if node_turns is not None:
        issued = _issuing_turns(events, node_turns)
        if issued is not None:
            return issued
    calls = [
        (index, _name(call), _canonical(_arguments(call)))
        for index, message in enumerate(turns)
        for call in (getattr(message, "tool_calls", None) or [])
    ]
    dispatches = []
    for event in events:
        data = _event_data(event)
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


def _record_goals(trace: Any) -> tuple[list[tuple[str, str]], int]:
    """((goal key, credited write occurrence) of passed record goals, decided record goal count).

    Record goals (``record.fields_equal@1``) are unconditional. Each is decided when its
    latest complete evaluation is valid; a passed goal is witnessed by the write that
    ``select_credit`` credits, so step credit follows the manifest's own credit."""

    latest: dict[str, tuple[Evaluation, str]] = {}
    for batch in getattr(trace, "assessment_batches", ()) or ():
        if batch.run.status != "complete":
            continue
        for receipt in batch.run.execution_evidence:
            if getattr(receipt, "kind", None) != RECORD_OUTPUT:
                continue
            evaluation = Evaluation.model_validate_json(receipt.payload_json)
            contract = json.loads(batch.views[0].input_json)["contract"]
            for result in evaluation.results:
                latest[result.check_id] = evaluation, _canonical(contract)
    if not latest:
        return [], 0
    first, contract_json = next(iter(latest.values()))
    if any((item.contract_digest, item.source_digest, item.evidence_json, text)
           != (first.contract_digest, first.source_digest, first.evidence_json, contract_json)
           for item, text in latest.values()):
        return [], 0
    contract = load_contract(contract_json)
    goals = {item.check_id for item in contract.checks if isinstance(item, CheckSpec) and item.role == "goal"}
    results = tuple(next(r for r in evaluation.results if r.check_id == check_id)
                    for check_id, (evaluation, _) in latest.items())
    combined = Evaluation(contract_digest=first.contract_digest, source_digest=first.source_digest,
                          results=results, evidence_json=first.evidence_json)
    required = sum(result.check_id in goals and result.status == "valid" for result in results)
    occurrences = [(f"record:{check_id}", selection.occurrence)
                   for selection in select_credit(contract, combined)
                   for check_id in selection.check_ids if check_id in goals]
    return occurrences, required


def manifest_outcomes(trace: Any) -> tuple[list[str], int, list[tuple[str, str]]]:
    """(earliest goal witness occurrences, decided required goal count, harm (check, occurrence)).

    Required goals are obligation findings marked required and record goals."""

    goals, required, harms = keyed_manifest_outcomes(trace)
    return [occurrence for _, occurrence in goals], required, harms


def keyed_manifest_outcomes(trace: Any) -> tuple[list[tuple[str, str]], int, list[tuple[str, str]]]:
    """((goal key, earliest witness occurrence), decided required goal count, harm (check, occurrence))."""

    goal_occurrences, required = _record_goals(trace)
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
                key = f"obligation:{payload.get('check_id')}:{payload.get('instance_key')}"
                goal_occurrences.append((key, earliest["occurrence"]))
    harms = sorted({
        (payload["check_id"], payload["occurrence"])
        for payload in _latest_payloads(trace, GUARD_OUTPUT)
        if payload.get("kind") == "finding" and payload.get("status") == "valid"
        and payload.get("value") == 1 and payload.get("occurrence")
    })
    return goal_occurrences, required, harms


READ_BUCKETS = 3  # distinct successful reads are counted 0, 1, 2 and 3+


def _actions_by_invocation(events: Sequence[Any]) -> dict[str, dict[str, Any]]:
    """Captured raw actions (tool, arguments, world digests, status) keyed by invocation id."""

    actions: dict[str, dict[str, Any]] = {}
    for event in events:
        data = event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)
        if data.get("source") != "tool_server" or data.get("phase") not in ("returned", "raised"):
            continue
        receipt = json.loads(data["receipt_json"])
        for encoded in receipt.get("evidence_json") or ():
            envelope = json.loads(encoded)
            if isinstance(envelope, Mapping) and isinstance(envelope.get("action"), Mapping):
                actions[data["invocation_id"]] = dict(envelope["action"])
    return actions


def _failed(action: Mapping[str, Any]) -> bool:
    """Whether a captured action failed: raised, or returned an error result."""

    if action.get("status") != "returned":
        return True
    try:
        result = json.loads(action.get("result_json") or "null")
        if isinstance(result, str):
            text = result.strip()
            if text.startswith(("Error", "error")):
                return True
            result = json.loads(text) if text.startswith("{") else result
    except ValueError:
        return False
    return isinstance(result, Mapping) and result.get("success") is False


def turn_state_keys(
    turns: Sequence[Any],
    events: Sequence[Any],
    goal_keys_by_turn: Sequence[Sequence[str]],
    turn_ids: Sequence[str],
    node_turns: Mapping[int, int] | None = None,
) -> dict[str, str] | None:
    """Per turn: digest of (goals first achieved before it, world before it, bucketed reads).

    The world is the after-digest of the last captured action of an earlier turn (the
    initial world before any). A read is a distinct (tool, arguments) call that returned
    without changing the world. None when a dispatch cannot be mapped to a turn or an
    action was not captured."""

    mapping = invocation_turns(turns, events, node_turns)
    actions = _actions_by_invocation(events)
    if mapping is None or set(mapping) - set(actions):
        return None
    by_turn: dict[int, list[dict[str, Any]]] = {}
    for invocation, index in mapping.items():
        by_turn.setdefault(index, []).append(actions[invocation])
    ordered = sorted(actions.values(), key=lambda action: action.get("occurrence_index", 0))
    world = ordered[0]["before_digest"] if ordered else "initial"
    goals: set[str] = set()
    reads: set[tuple[str, str]] = set()
    keys: dict[str, str] = {}
    for index, turn_id in enumerate(turn_ids):
        identity = [sorted(goals), world, min(len(reads), READ_BUCKETS)]
        keys[turn_id] = hashlib.sha256(_canonical(identity).encode()).hexdigest()
        for action in sorted(by_turn.get(index, ()), key=lambda item: item.get("occurrence_index", 0)):
            world = action.get("after_digest") or world
            if action.get("before_digest") == action.get("after_digest") and not _failed(action):
                reads.add((str(action.get("tool_name")), _canonical(json.loads(action.get("arguments_json") or "{}"))))
        goals.update(goal_keys_by_turn[index] if index < len(goal_keys_by_turn) else ())
    return keys


def apply_manifest_step_credit(
    evidence: dict[str, Any],
    *,
    turns: Sequence[Any],
    events: Sequence[Any],
    trace: Any,
    config: AutomationBenchTurnRewardConfig,
    node_turns: Mapping[int, int] | None = None,
) -> dict[str, Any]:
    """Return turn evidence with manifest goal/harm components added to each turn."""

    assessments = evidence.get("assessments") or []
    goal_share = config.manifest_goal_share or 0.0
    harm_penalty = config.manifest_harm_penalty or 0.0
    keyed_goals, required, harms = keyed_manifest_outcomes(trace)
    goal_occurrences = [occurrence for _, occurrence in keyed_goals]
    separate = config.manifest_goal_channel == "group_relative"
    mapping = invocation_turns(turns, events, node_turns) if (goal_occurrences or harms) else {}
    mapped = mapping is not None
    goals_by_turn = [0] * len(assessments)
    goal_keys_by_turn: list[list[str]] = [[] for _ in assessments]
    harms_by_turn = [0] * len(assessments)
    if mapped:
        for key, occurrence in keyed_goals:
            index = mapping.get(occurrence)
            if index is not None and index < len(assessments):
                goals_by_turn[index] += 1
                goal_keys_by_turn[index].append(key)
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
        base_shift = (0.0 if previous.get("manifest_separate") == 1.0
                      else previous.get("manifest_goal_credit", 0.0) - previous.get("manifest_harm_debit", 0.0))
        components = []
        for component in assessment["components"]:
            if component["name"].startswith("manifest_"):
                continue
            if component["name"] == TURN_REWARD:
                base = component["value"] - base_shift
                shift = 0.0 if separate else goal_credit - harm_debit
                component = {**component, "value": base + shift}
            components.append(component)
        components += [
            {"name": "manifest_goals", "status": "valid", "value": float(goals_by_turn[index])},
            {"name": "manifest_harms", "status": "valid", "value": float(harms_by_turn[index])},
            {"name": "manifest_goal_credit", "status": "valid", "value": goal_credit},
            {"name": "manifest_harm_debit", "status": "valid", "value": harm_debit},
            {"name": "manifest_mapped", "status": "valid", "value": 1.0 if mapped else 0.0},
        ]
        if separate:
            components.append({"name": "manifest_separate", "status": "valid", "value": 1.0})
        if separate and mapped and required:
            weight = goal_share / required
            for key in sorted(set(goal_keys_by_turn[index])):
                components.append({"name": f"manifest_goal/{key}", "status": "valid",
                                   "value": weight * goal_keys_by_turn[index].count(key)})
        updated.append({**assessment, "components": components})
    result = {**evidence, "assessments": updated}
    result.pop("turn_state_keys", None)
    if config.anchor_state_keys:
        state_keys = turn_state_keys(
            turns, events, goal_keys_by_turn, [item["turn_id"] for item in assessments], node_turns
        )
        if state_keys is not None:
            result["turn_state_keys"] = state_keys
    return result


__all__ = [
    "apply_manifest_step_credit",
    "invocation_turns",
    "keyed_manifest_outcomes",
    "manifest_outcomes",
    "turn_state_keys",
]
