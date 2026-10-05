"""Manifest goal credit and harm debit on the step that issued the tool call."""

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from test_manifest_guard_assessments import native_fixture
from test_manifest_guard_populations import rename, vip_contract, world
from test_manifest_obligation_alternatives import contract as goal_contract
from test_manifest_obligation_alternatives import email
from test_manifest_obligation_alternatives import world as goal_world
from test_notification_evidence import run_operations
from test_record_update_evidence import CONTRACTS as RECORD_TASKS
from test_manifest_assessments import recorded

from automationbench_v1 import manifest_assessments
from automationbench_v1.contracts import load_contract, load_task_contract
from automationbench_v1.manifest_step_credit import apply_manifest_step_credit, invocation_turns, manifest_outcomes
from automationbench_v1.turn_rewards import AutomationBenchTurnRewardConfig, turn_evidence

CONFIG = AutomationBenchTurnRewardConfig(
    tool_failure_penalty=0.02, manifest_goal_share=0.5, manifest_harm_penalty=0.1, manifest_harm_cap=0.15)


def dispatch(invocation, seq, tool, kwargs, attempt=None):
    receipt = {"invocation_id": invocation, "event_index": 0, "phase": "dispatch", "tool_name": tool,
               "arguments_json": json.dumps({"args": [], "kwargs": kwargs})}
    if attempt is not None:
        receipt["transport_attempt_index"] = attempt
    return {"source": "tool_server", "phase": "dispatch", "invocation_id": invocation, "receipt_seq": seq,
            "receipt_json": json.dumps(receipt)}


def turn(*calls):
    return SimpleNamespace(tool_calls=[SimpleNamespace(id=f"call-{n}-{i}", name=n, arguments=json.dumps(a))
                                       for i, (n, a) in enumerate(calls)])


def test_invocations_map_to_turns_in_order_with_prefixed_names_and_retries():
    turns = [turn(("search_tools", {"q": "a"})), turn(("mcp__ab__gmail_send_email", {"to": "x"}),
                                                     ("gmail_send_email", {"to": "y"}))]
    events = [dispatch("e0", 0, "search_tools", {"q": "a"}), dispatch("e1", 2, "gmail_send_email", {"to": "x"}),
              dispatch("e1r", 3, "gmail_send_email", {"to": "x"}, attempt=1),
              dispatch("e2", 4, "gmail_send_email", {"to": "y"})]
    assert invocation_turns(turns, events) == {"e0": 0, "e1": 1, "e1r": 1, "e2": 1}
    assert invocation_turns(turns, [dispatch("e9", 0, "gmail_send_email", {"to": "z"})]) is None


def scored_trace(monkeypatch, declared, calls, initial):
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, _, trace = native_fixture(run_operations(initial, calls))
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    return trace


def evidence(trace, turns):
    return turn_evidence(trace_id=trace.id, turns=turns, tool_results={},
                         progress=[{"after_turn": 0, "partial_credit": 0.0}], config=CONFIG)


def components(result):
    return [{c["name"]: c["value"] for c in item["components"]} for item in result["assessments"]]


def turns_for(trace):
    """One synthetic sampled turn per tool-server dispatch, matching name and arguments."""
    out = []
    for event in trace.tool_execution_events:
        data = event.model_dump(mode="json")
        if data.get("source") == "tool_server" and data["phase"] == "dispatch":
            receipt = json.loads(data["receipt_json"])
            out.append(turn((receipt["tool_name"], json.loads(receipt["arguments_json"])["kwargs"])))
    return out


def test_harm_is_debited_on_the_issuing_step(monkeypatch):
    trace = scored_trace(monkeypatch, vip_contract(), [rename("hc2", "Bo B"), rename("hc1", "Ada L")], world())
    turns = [SimpleNamespace(tool_calls=[])] + turns_for(trace)
    result = components(apply_manifest_step_credit(evidence(trace, turns), turns=turns,
                                                   events=trace.tool_execution_events, trace=trace, config=CONFIG))
    assert [c["manifest_harms"] for c in result] == [0, 0, 1]
    assert result[2]["manifest_harm_debit"] == pytest.approx(0.1)
    assert result[2]["turn_reward"] == pytest.approx(-0.1)
    assert all(c["manifest_mapped"] == 1 for c in result)


def test_goal_credit_is_a_share_on_the_witnessing_step(monkeypatch):
    trace = scored_trace(monkeypatch, goal_contract(), [email(to="other@example.com"), email()], goal_world())
    turns = turns_for(trace)
    result = components(apply_manifest_step_credit(evidence(trace, turns), turns=turns,
                                                   events=trace.tool_execution_events, trace=trace, config=CONFIG))
    assert [c["manifest_goals"] for c in result] == [0, 1]
    assert result[1]["manifest_goal_credit"] == pytest.approx(0.5)  # one required goal, fully passed
    assert result[0]["turn_reward"] == pytest.approx(0.0)


def recorded_trace(monkeypatch, previous, change=None):
    """Luna's recorded episode of a record-update task, scored with its (optionally changed) manifest."""
    declaration = load_task_contract(previous.task_name).model_dump(mode="json")
    if change:
        change(declaration)
    contract = load_contract(json.dumps(declaration))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    task, _, trace, _, _ = recorded(previous)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    return trace


def record_credit(trace):
    turns = turns_for(trace)
    return components(apply_manifest_step_credit(evidence(trace, turns), turns=turns,
                                                 events=trace.tool_execution_events, trace=trace, config=CONFIG))


@pytest.mark.parametrize("previous", RECORD_TASKS, ids=lambda item: item.task_name)
def test_record_goal_is_credited_to_the_write_native_credit_names(monkeypatch, previous):
    trace = recorded_trace(monkeypatch, previous)
    credited = [contribution.recipient.execution.invocation_id
                for assignment in trace.credit_assignments if assignment.status == "complete"
                for contribution in assignment.contributions]
    occurrences, required, _ = manifest_outcomes(trace)
    assert required == 1 and occurrences == credited and len(credited) == 1
    result = record_credit(trace)
    assert sum(c["manifest_goals"] for c in result) == 1
    assert sum(c["manifest_goal_credit"] for c in result) == pytest.approx(0.5)


def test_joint_record_goals_count_each_goal_on_their_shared_write(monkeypatch):
    def joint(declaration):
        second = copy.deepcopy(declaration["checks"][0])
        second["check_id"] = "second-obligation"
        declaration["checks"].append(second)
        declaration["credit"] = [{"policy": "joint_verified_transition_once@1",
                                  "checks": ["requested-state", "second-obligation"], "channel": "goal"}]

    occurrences, required, _ = manifest_outcomes(recorded_trace(monkeypatch, RECORD_TASKS[0], joint))
    assert required == 2 and len(occurrences) == 2 and len(set(occurrences)) == 1


def test_failed_record_goal_is_decided_without_a_witness(monkeypatch):
    def unreachable(declaration):
        declaration["bindings"] = []
        declaration["checks"][0]["expected"][0]["value"] = "a value no episode writes"

    trace = recorded_trace(monkeypatch, RECORD_TASKS[0], unreachable)
    assert manifest_outcomes(trace)[:2] == ([], 1)
    assert all(c["manifest_goal_credit"] == 0 for c in record_credit(trace))


def test_unmapped_episode_gets_no_manifest_credit(monkeypatch):
    trace = scored_trace(monkeypatch, vip_contract(), [rename("hc1", "Ada L")], world())
    turns = [turn(("helpcrunch_update_customer", {"customer_id": "someone-else"}))]
    result = components(apply_manifest_step_credit(evidence(trace, turns), turns=turns,
                                                   events=trace.tool_execution_events, trace=trace, config=CONFIG))
    assert result[0]["manifest_mapped"] == 0 and result[0]["manifest_harm_debit"] == 0


def test_harm_debit_is_capped_per_episode(monkeypatch):
    trace = scored_trace(monkeypatch, vip_contract(),
                         [rename("hc1", "A1"), rename("hc1", "A2"), rename("hc1", "A3")], world())
    turns = turns_for(trace)
    result = components(apply_manifest_step_credit(evidence(trace, turns), turns=turns,
                                                   events=trace.tool_execution_events, trace=trace, config=CONFIG))
    assert [round(c["manifest_harm_debit"], 6) for c in result] == [0.1, 0.05, 0.0]


def test_manifest_weights_change_the_scorer_identity_only_when_selected():
    plain = AutomationBenchTurnRewardConfig(tool_failure_penalty=0.02)
    assert plain.scorer_digest == "fe9c7af7edca6ac82980809b95cf572cf45dcd809522cb01d88e90992b3c2b87"
    assert CONFIG.scorer_digest != plain.scorer_digest
    with pytest.raises(ValueError):
        AutomationBenchTurnRewardConfig(manifest_goal_share=0.5)


def test_reapplying_after_rescore_is_idempotent(monkeypatch):
    trace = scored_trace(monkeypatch, vip_contract(), [rename("hc1", "Ada L")], world())
    turns = turns_for(trace)
    once = apply_manifest_step_credit(evidence(trace, turns), turns=turns, events=trace.tool_execution_events,
                                      trace=trace, config=CONFIG)
    twice = apply_manifest_step_credit(once, turns=turns, events=trace.tool_execution_events,
                                       trace=trace, config=CONFIG)
    assert components(twice) == components(once)
