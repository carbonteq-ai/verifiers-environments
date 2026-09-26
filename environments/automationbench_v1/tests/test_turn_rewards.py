from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import verifiers.v1 as vf
from verifiers.v1.session import hook_boundary

from automationbench.schema.world import WorldState
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState
from automationbench_v1.turn_rewards import (
    PROGRESS_KEY,
    TURN_EVIDENCE_KEY,
    AutomationBenchTurnRewardConfig,
    record_progress,
    tool_result_failed,
    turn_evidence,
)


def test_tool_failures_are_recognized_in_every_reported_form() -> None:
    assert tool_result_failed(json.dumps({"error": "Worksheet 'ws_backlog' not found"}))
    assert tool_result_failed(json.dumps({"success": False, "message": "denied"}))
    assert tool_result_failed("Error executing tool gmail_send_email: missing to")
    assert tool_result_failed(
        "error: invalid JSON in tool arguments (x); resend the call with valid JSON"
    )
    assert tool_result_failed([{"type": "text", "text": '{"error": "boom"}'}])
    assert not tool_result_failed(json.dumps({"success": True, "worksheet": {"id": "ws_1"}}))
    assert not tool_result_failed("31 rows")


def test_turn_rewards_are_credit_changes_minus_failure_penalties() -> None:
    call = vf.ToolCall
    turns = [
        vf.AssistantMessage(
            tool_calls=[
                call(id="a", name="find", arguments="{}"),
                call(id="b", name="update", arguments="{}"),
            ]
        ),
        vf.AssistantMessage(tool_calls=[call(id="c", name="send", arguments="{}")]),
        vf.AssistantMessage(content="done"),
    ]
    progress = [
        {"after_turn": 0, "partial_credit": 0.0},
        {"after_turn": 1, "partial_credit": 0.5},
        {"after_turn": 2, "error": "AssertionError: odd state"},
        {"after_turn": 3, "partial_credit": 1.0},
    ]
    results = {"a": '{"error": "not found"}', "b": '{"success": true}', "c": '{"success": true}'}
    config = AutomationBenchTurnRewardConfig(tool_failure_penalty=0.1)

    evidence = turn_evidence(
        trace_id="t1", turns=turns, tool_results=results, progress=progress, config=config
    )

    assert evidence["projection_id"] == "assistant-turns@1"
    assert evidence["branch_id"] == "0"
    assert evidence["scorer_digest"] == config.scorer_digest
    rewards = {item["turn_id"]: item["components"][0]["value"] for item in evidence["assessments"]}
    # Turn 2's world could not be scored: it keeps the last credit, so turn 3 gets the change.
    assert rewards == {"assistant-0": 0.5 - 0.1, "assistant-1": 0.0, "assistant-2": 0.5}
    assert sum(rewards.values()) == 1.0 - 0.0 - 0.1


def test_progress_is_recorded_once_per_turn() -> None:
    info: dict[str, Any] = {}
    record_progress(info, 0, lambda: 0.0)
    record_progress(info, 0, lambda: 1.0)
    record_progress(info, 1, lambda: 0.5)
    assert info[PROGRESS_KEY] == [
        {"after_turn": 0, "partial_credit": 0.0},
        {"after_turn": 1, "partial_credit": 0.5},
    ]


def test_scorer_digest_names_the_scoring_rule() -> None:
    assert (
        AutomationBenchTurnRewardConfig().scorer_digest
        != AutomationBenchTurnRewardConfig(tool_failure_penalty=0.1).scorer_digest
    )
    assert len(AutomationBenchTurnRewardConfig().scorer_digest) == 64


def _episode(turn_rewards: AutomationBenchTurnRewardConfig | None) -> tuple[Any, Any]:
    config = AutomationBenchConfig(
        domains=["simple"], task=AutomationBenchTaskConfig(turn_rewards=turn_rewards)
    )
    task = next(iter(AutomationBenchTaskset(config).load()))
    trace = vf.Trace(
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type=type(task).__name__, data=task.data),
        state=AutomationBenchState(),
    )
    asyncio.run(task.setup(trace, None))  # type: ignore[arg-type]
    return task, trace


def _append(trace: vf.Trace, message: Any, *, sampled: bool) -> None:
    parent = len(trace.nodes) - 1 if trace.nodes else None
    trace.nodes.append(vf.MessageNode(parent=parent, message=message, sampled=sampled))


def test_live_episode_emits_posttrain_turn_evidence() -> None:
    config = AutomationBenchTurnRewardConfig(tool_failure_penalty=0.05)
    task, trace = _episode(config)
    _append(trace, vf.UserMessage(content="Update the contact's phone."), sampled=False)

    # The rollout runs Trace-boundary stop hooks before every model call.
    stops = {fn.__name__: fn for fn in task.hooks("stop")}
    assert hook_boundary(stops["record_turn_progress"], allow_trace=True) is vf.Trace
    asyncio.run(task.record_turn_progress(trace))  # before the first model call
    _append(
        trace,
        vf.AssistantMessage(
            tool_calls=[
                vf.ToolCall(id="c1", name="salesforce_contact_find", arguments="{}"),
                vf.ToolCall(id="c2", name="salesforce_contact_update", arguments="{}"),
            ]
        ),
        sampled=True,
    )
    _append(
        trace, vf.ToolMessage(tool_call_id="c1", content='{"error": "no match"}'), sampled=False
    )
    state = cast(AutomationBenchState, trace.state)
    world = WorldState.model_validate(state.world)
    world.salesforce.contacts[0].phone = "+1-555-0101"
    state.world = world.model_dump(mode="json")
    _append(trace, vf.ToolMessage(tool_call_id="c2", content='{"success": true}'), sampled=False)

    assert asyncio.run(task.record_turn_progress(trace)) is False  # before the second model call
    _append(trace, vf.AssistantMessage(content="Updated."), sampled=True)
    asyncio.run(task.finalize(trace, None))  # type: ignore[arg-type]

    assert [entry["after_turn"] for entry in trace.info[PROGRESS_KEY]] == [0, 1, 2]
    evidence = trace.info[TURN_EVIDENCE_KEY]
    assert evidence["trace_id"] == trace.id
    assert trace.info["posttrain_scorer_digests"][TURN_EVIDENCE_KEY] == config.scorer_digest
    rewards = [item["components"][0]["value"] for item in evidence["assessments"]]
    assert [item["turn_id"] for item in evidence["assessments"]] == ["assistant-0", "assistant-1"]
    assert rewards == [1.0 - 0.05, 0.0]


def test_turn_rewards_are_off_unless_selected() -> None:
    task, trace = _episode(None)
    asyncio.run(task.record_turn_progress(trace))
    _append(trace, vf.AssistantMessage(content="done"), sampled=True)
    asyncio.run(task.finalize(trace, None))  # type: ignore[arg-type]
    assert PROGRESS_KEY not in trace.info
    assert TURN_EVIDENCE_KEY not in trace.info
