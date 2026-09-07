"""The task-owned judge never leaks future turns into prefix assessments."""

import asyncio
import hashlib
import json
from types import SimpleNamespace
from typing import Any

import pytest
import verifiers.v1 as vf

from automationbench_v1.judge import AutomationBenchTurnJudge, TurnQualityConfig, TurnRating


def _dimensions(score: float) -> dict[str, float]:
    return {
        "understanding_planning": score,
        "logical_correctness": score,
        "evidence_state_grounding": score,
        "verification_self_correction": score,
        "progress_efficiency": score,
    }


def test_quality_is_deterministic_mean_while_dimensions_remain_evidence():
    dimensions = {
        "understanding_planning": 1.0,
        "logical_correctness": 0.75,
        "evidence_state_grounding": 0.5,
        "verification_self_correction": 0.25,
        "progress_efficiency": 0.0,
    }
    rating = TurnRating.model_validate(
        {"turn_id": "assistant-0", "dimensions": dimensions, "erroneous": True, "reason": "mixed"}
    )
    assert rating.quality == 0.5
    assert rating.dimensions.model_dump() == dimensions


def _trace():
    return SimpleNamespace(
        id="trace",
        info={},
        branches=[
            SimpleNamespace(
                nodes=[
                    SimpleNamespace(
                        message=vf.AssistantMessage(content="First action"),
                        sampled=True,
                        mask=[True],
                    ),
                    SimpleNamespace(
                        message=vf.AssistantMessage(content="Later correction"),
                        sampled=True,
                        mask=[True],
                    ),
                ]
            )
        ],
    )


def _task(*tools):
    return SimpleNamespace(zapier_tools=tools)


def _episode_payload(assessments, *, checks=None):
    return {
        "requirement_checks": checks
        or [
            {
                "requirement": "Complete the requested task",
                "outcome": "satisfied",
                "explanation": "The action is supported.",
                "evidence": ["message-0"],
                "relevant_dimensions": ["action_quality"],
            }
        ],
        "assessments": assessments,
    }


def test_episode_dimensions_preserved_and_prompt_survives_json_reordering(monkeypatch):
    from automationbench_v1.judge import EPISODE_RUBRICS

    judge = _judge(assessment_scope="episode")
    trace = _trace()
    assessments = {
        name: {
            "status": "valid",
            "score": index / 8,
            "reason": "Evidence",
            "evidence": ["message-0"],
        }
        for index, name in enumerate(EPISODE_RUBRICS)
    }
    captured = []

    async def complete(messages, **kwargs):
        captured.append(messages)
        return vf.JudgeResponse(text=json.dumps(_episode_payload(assessments)))

    monkeypatch.setattr(judge, "complete", complete)
    assert asyncio.run(judge.score(_task(), trace)) == {}
    saved = json.loads(json.dumps(trace.info, sort_keys=True))
    attempt = saved["posttrain_episode_reward_attempts"][0]
    assert [message["role"] for message in attempt["messages"]] == ["system", "user"]
    assert len(captured[0]) == 2
    assert attempt["assessment_request"]["contract"] == "general-agent-episode@5"
    assert attempt["assessment_request"]["valid_message_ids"] == ["message-0", "message-1"]
    assert len(attempt["input_digest"]) == 64
    assert saved["posttrain_episode_rewards"]["assessments"] == assessments
    assert [saved[f"episode_reward/{name}"] for name in EPISODE_RUBRICS] == [
        index / 8 for index in range(7)
    ]
    assert "posttrain_turn_rewards" not in saved


@pytest.mark.parametrize("failure", ["missing", "unknown_evidence", "not_applicable"])
def test_episode_invalid_evidence_never_becomes_training_scores(monkeypatch, failure):
    from automationbench_v1.judge import EPISODE_RUBRICS

    judge = _judge(assessment_scope="episode")
    trace = _trace()
    assessments = {
        name: {"status": "valid", "score": 0.75, "reason": "Evidence", "evidence": ["message-0"]}
        for name in EPISODE_RUBRICS
    }
    first = next(iter(assessments))
    if failure == "missing":
        del assessments[first]
    elif failure == "unknown_evidence":
        assessments[first]["evidence"] = ["message-999"]
    else:
        assessments[first].update(status="not_applicable", score=None)

    async def complete(messages, **kwargs):
        return vf.JudgeResponse(text=json.dumps(_episode_payload(assessments)))

    monkeypatch.setattr(judge, "complete", complete)
    with pytest.raises(ValueError, match="no rewards admitted"):
        asyncio.run(judge.score(_task(), trace))
    assert not any(key.startswith("episode_reward/") for key in trace.info)
    attempts = trace.info["posttrain_episode_reward_attempts"]
    assert 1 <= len(attempts) <= judge.config.attempts
    assert all(attempt["status"] != "valid" for attempt in attempts)


def _judge(**kwargs) -> Any:
    return AutomationBenchTurnJudge(
        TurnQualityConfig(
            id="automationbench-v1",
            code_revision="a" * 40,
            model_revision="b" * 40,
            input_budget_tokens=22_528,
            **kwargs,
        )
    )


def test_episode_judge_allows_a_bounded_fifteen_minute_timeout() -> None:
    assert _judge(timeout_seconds=900).config.timeout_seconds == 900
    with pytest.raises(ValueError):
        _judge(timeout_seconds=901)


def test_prefix_assessment_has_no_future_context_and_exact_evidence_references(monkeypatch):
    judge = _judge(context_scope="prefix")
    trace = _trace()
    prompts = []

    async def complete(prompt, **kwargs):
        request = json.loads(prompt.split("ASSESSMENT REQUEST:\n")[1])
        prompts.append(request)
        return vf.JudgeResponse(
            text=json.dumps(
                {
                    "turns": [
                        {
                            "turn_id": request["target_turn_ids"][0],
                            "dimensions": _dimensions(len(prompts) / 2),
                            "erroneous": False,
                            "reason": "Supported by available context",
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr(judge, "complete", complete)
    assert asyncio.run(judge.score(None, trace)) == {}
    assert "Later correction" not in json.dumps(prompts[0])
    assert len(prompts[0]["trajectory"]) == 1
    assert len(prompts[1]["trajectory"]) == 2
    evidence = trace.info["posttrain_turn_rewards"]
    assert evidence["context_scope"] == "prefix"
    assert [entry["components"][0]["value"] for entry in evidence["assessments"]] == [0.5, 1.0]
    assert [entry["evidence_ref"] for entry in evidence["assessments"]] == [
        "info/posttrain_turn_rewards_attempts/0",
        "info/posttrain_turn_rewards_attempts/1",
    ]
    assert judge.scorer_digest != _judge().scorer_digest


@pytest.mark.parametrize("status", ["abstained", "inapplicable"])
def test_unavailable_assessment_is_retained_without_retry_or_manufactured_reward(
    monkeypatch, status
):
    judge = _judge()
    trace = _trace()

    async def complete(*args, **kwargs):
        return vf.JudgeResponse(
            text=json.dumps({"status": status, "reason": "Insufficient evidence", "turns": []})
        )

    monkeypatch.setattr(judge, "complete", complete)
    with pytest.raises(ValueError, match="no reward was manufactured"):
        asyncio.run(judge.score(None, trace))
    assert "posttrain_turn_rewards" not in trace.info
    assert [item["status"] for item in trace.info["posttrain_turn_rewards_attempts"]] == [status]


def test_timeouts_exhaust_only_declared_attempts_and_keep_diagnostic_status(monkeypatch):
    judge = _judge(attempts=2)
    trace = _trace()

    async def complete(*args, **kwargs):
        raise TimeoutError("unavailable")

    monkeypatch.setattr(judge, "complete", complete)
    with pytest.raises(ValueError, match="no reward was manufactured"):
        asyncio.run(judge.score(None, trace))
    assert [item["status"] for item in trace.info["posttrain_turn_rewards_attempts"]] == [
        "timeout",
        "timeout",
    ]
    assert "posttrain_turn_rewards" not in trace.info


def test_tool_observations_are_losslessly_compacted_with_digest(monkeypatch):
    source = json.dumps(
        [
            {
                "name": f"tool-{index}",
                "description": "x" * 2_000,
                "parameters": {"properties": {f"field-{item}": {} for item in range(100)}},
            }
            for index in range(20)
        ]
    )
    trace = SimpleNamespace(
        id="trace",
        info={},
        branches=[
            SimpleNamespace(
                nodes=[
                    SimpleNamespace(
                        message=vf.AssistantMessage(content="Search for the correct tool."),
                        sampled=True,
                        mask=[True],
                    ),
                    SimpleNamespace(
                        message=vf.ToolMessage(content=source, tool_call_id="search"),
                        sampled=False,
                        mask=[False],
                    ),
                ]
            )
        ],
    )
    projected = []

    async def complete(prompt, **kwargs):
        request = json.loads(prompt.split("ASSESSMENT REQUEST:\n")[1])
        projected.append(request["trajectory"][1]["content"])
        return vf.JudgeResponse(
            text=json.dumps(
                {
                    "turns": [
                        {
                            "turn_id": "assistant-0",
                            "dimensions": _dimensions(1.0),
                            "erroneous": False,
                            "reason": "The search was useful.",
                        }
                    ]
                }
            )
        )

    judge = _judge()
    monkeypatch.setattr(judge, "complete", complete)
    asyncio.run(judge.score(None, trace))
    [content] = projected
    view = json.loads(content)
    assert view["projection"] == "automationbench-judge-context@2"
    assert view["source_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert view["value"] == json.loads(source)
    assert trace.branches[0].nodes[1].message.content == source


def test_tool_projection_never_drops_late_or_conflicting_behavior_fields():
    from automationbench_v1.judge import project_tool_observation

    result: dict[str, Any] = {f"field_{index}": index for index in range(30)}
    result.update({"due_on": "2024-02-15", "dueDate": "2026-03-15"})
    source = json.dumps(result, indent=2)
    view = json.loads(project_tool_observation(source))
    assert view["value"] == result
    assert view["value"]["due_on"] == "2024-02-15"
    assert view["value"]["dueDate"] == "2026-03-15"


def test_episode_request_includes_exact_selected_tool_contract_but_not_hidden_oracles(
    monkeypatch,
):
    from automationbench_v1.judge import EPISODE_RUBRICS

    judge = _judge(assessment_scope="episode")
    trace = _trace()
    assessments = {
        name: {"status": "valid", "score": 0.75, "reason": "Evidence", "evidence": ["message-0"]}
        for name in EPISODE_RUBRICS
    }

    async def complete(messages, **kwargs):
        request = json.loads(messages[1].content)
        [tool] = request["available_tools"]
        assert tool["function"]["name"] == "google_calendar_create_detailed_event"
        properties = tool["function"]["parameters"]["properties"]
        assert properties["all_day"]["type"] == "boolean"
        assert "calendar_id" in properties
        serialized = json.dumps(request)
        assert "assertions" not in serialized
        assert "native_reward" not in serialized
        assert "end_state" not in serialized
        return vf.JudgeResponse(text=json.dumps(_episode_payload(assessments)))

    monkeypatch.setattr(judge, "complete", complete)
    asyncio.run(judge.score(_task("google_calendar_create_detailed_event"), trace))


def test_violated_requirement_cannot_hide_behind_perfect_relevant_score():
    from automationbench_v1.episode_prompt import (
        EPISODE_RUBRICS,
        EpisodeVerdict,
        validate_episode_verdict,
    )

    assessments = {
        name: {"status": "valid", "score": 1.0, "reason": "Evidence", "evidence": ["message-0"]}
        for name in EPISODE_RUBRICS
    }
    checks = [
        {
            "requirement": "Create an all-day event",
            "outcome": "violated_major",
            "explanation": "The action created a timed event.",
            "evidence": ["message-0"],
            "relevant_dimensions": ["action_quality", "answer_quality"],
        }
    ]
    verdict = EpisodeVerdict.model_validate(_episode_payload(assessments, checks=checks))
    with pytest.raises(ValueError, match="violated requirement"):
        validate_episode_verdict(verdict, {"message-0"})
