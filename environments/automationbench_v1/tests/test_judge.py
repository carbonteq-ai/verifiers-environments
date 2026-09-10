"""Whole-episode judge contract and evidence normalization."""

import asyncio
import hashlib
import json
from types import SimpleNamespace
from typing import Any

import pytest
import verifiers.v1 as vf

from automationbench_v1.episode_prompt import EPISODE_RUBRICS, EpisodeVerdict
from automationbench_v1.judge import AutomationBenchEpisodeJudge, EpisodeQualityConfig


def _trace(*messages: vf.Message) -> Any:
    return SimpleNamespace(
        id="trace",
        info={},
        branches=[
            SimpleNamespace(
                nodes=[
                    SimpleNamespace(
                        message=message, sampled=message.role == "assistant", mask=[True]
                    )
                    for message in messages
                ]
            )
        ],
    )


def _task(*tools: str) -> Any:
    return SimpleNamespace(zapier_tools=tools)


def _judge(**kwargs: Any) -> AutomationBenchEpisodeJudge:
    return AutomationBenchEpisodeJudge(
        EpisodeQualityConfig(
            id="automationbench-v1",
            code_revision="a" * 40,
            model_revision="b" * 40,
            input_budget_tokens=12_288,
            **kwargs,
        )
    )


def _wire_payload(score: float = 0.75, evidence: list[int] | None = None) -> dict[str, Any]:
    refs = [0] if evidence is None else evidence
    return {
        "requirement_checks": [
            {
                "requirement": "Complete the requested task",
                "outcome": "satisfied",
                "explanation": "The observed action completed it.",
                "evidence": refs,
                "relevant_dimensions": [],
            }
        ],
        "assessments": {
            name: {
                "status": "valid",
                "score": score,
                "reason": "Supported by the cited messages.",
                "evidence": refs,
            }
            for name in EPISODE_RUBRICS
        },
    }


def test_episode_judge_uses_one_episode_rubric_and_normalizes_wire_evidence(monkeypatch):
    judge = _judge()
    trace = _trace(
        vf.UserMessage(content="Do the task."),
        vf.AssistantMessage(content="Done."),
    )
    captured: list[tuple[list[vf.Message], type[Any]]] = []

    async def complete(messages, **kwargs):
        captured.append((messages, kwargs["schema"]))
        return vf.JudgeResponse(text=json.dumps(_wire_payload(evidence=[0, 1])))

    monkeypatch.setattr(judge, "complete", complete)
    assert asyncio.run(judge.score(_task(), trace)) == {}
    [(messages, schema)] = captured
    system_prompt = messages[0].content
    assert isinstance(system_prompt, str)
    assert system_prompt.startswith(
        "You are an exacting, domain-general evaluator of one agent episode."
    )
    assert "turns list" not in system_prompt
    assert schema.__name__ == "WireEpisodeVerdict"
    attempt = trace.info["posttrain_episode_reward_attempts"][0]
    assert attempt["assessment_request"]["contract"] == "general-agent-episode@6"
    assert attempt["assessment_request"]["valid_message_ids"] == ["message-0", "message-1"]
    saved = trace.info["posttrain_episode_rewards"]
    assert saved["scope"] == "episode"
    assert saved["requirement_checks"][0]["evidence"] == ["message-0", "message-1"]
    assert saved["assessments"]["action_quality"]["evidence"] == ["message-0", "message-1"]
    assert all(trace.info[f"episode_reward/{name}"] == 0.75 for name in EPISODE_RUBRICS)


def test_legacy_turn_scope_is_not_part_of_the_config_contract() -> None:
    assert "assessment_scope" not in EpisodeQualityConfig.model_fields
    assert "context_scope" not in EpisodeQualityConfig.model_fields
    assert "annotation_key" not in EpisodeQualityConfig.model_fields


@pytest.mark.parametrize("evidence", [[99], [0, 0]])
def test_invalid_wire_evidence_never_becomes_training_reward(monkeypatch, evidence):
    judge = _judge(attempts=1)
    trace = _trace(vf.UserMessage(content="Do the task."))

    async def complete(*args, **kwargs):
        return vf.JudgeResponse(text=json.dumps(_wire_payload(evidence=evidence)))

    monkeypatch.setattr(judge, "complete", complete)
    with pytest.raises(ValueError, match="no rewards admitted"):
        asyncio.run(judge.score(_task(), trace))
    assert not any(key.startswith("episode_reward/") for key in trace.info)
    assert trace.info["posttrain_episode_reward_attempts"][0]["status"] == "invalid_output"


def test_episode_judge_retries_only_its_bounded_attempts(monkeypatch):
    judge = _judge(attempts=2)
    trace = _trace(vf.UserMessage(content="Do the task."))

    async def complete(*args, **kwargs):
        raise TimeoutError("unavailable")

    monkeypatch.setattr(judge, "complete", complete)
    with pytest.raises(ValueError, match="no rewards admitted"):
        asyncio.run(judge.score(_task(), trace))
    assert [item["status"] for item in trace.info["posttrain_episode_reward_attempts"]] == [
        "failed",
        "failed",
    ]


def test_tool_observations_are_losslessly_compacted_with_digest(monkeypatch):
    source = json.dumps({f"field_{index}": index for index in range(30)}, indent=2)
    trace = _trace(
        vf.UserMessage(content="Inspect it."),
        vf.ToolMessage(content=source, tool_call_id="search"),
    )
    projected: list[str] = []

    async def complete(messages, **kwargs):
        request = json.loads(messages[1].content)
        projected.append(request["trajectory"][1]["content"])
        return vf.JudgeResponse(text=json.dumps(_wire_payload()))

    judge = _judge()
    monkeypatch.setattr(judge, "complete", complete)
    asyncio.run(judge.score(_task(), trace))
    view = json.loads(projected[0])
    assert view["projection"] == "automationbench-judge-context@2"
    assert view["source_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert view["value"] == json.loads(source)


def test_episode_request_includes_selected_tool_contract_without_hidden_oracles(monkeypatch):
    trace = _trace(vf.UserMessage(content="Create an event."))

    async def complete(messages, **kwargs):
        request = json.loads(messages[1].content)
        [tool] = request["available_tools"]
        assert tool["function"]["name"] == "google_calendar_create_detailed_event"
        serialized = json.dumps(request)
        assert "assertions" not in serialized
        assert "native_reward" not in serialized
        return vf.JudgeResponse(text=json.dumps(_wire_payload()))

    judge = _judge()
    monkeypatch.setattr(judge, "complete", complete)
    asyncio.run(judge.score(_task("google_calendar_create_detailed_event"), trace))


def test_violated_requirement_cannot_hide_behind_perfect_relevant_score():
    from automationbench_v1.episode_prompt import validate_episode_verdict

    payload = {
        "requirement_checks": [
            {
                "requirement": "Create an all-day event",
                "outcome": "violated_major",
                "explanation": "The action created a timed event.",
                "evidence": ["message-0"],
                "relevant_dimensions": ["action_quality"],
            }
        ],
        "assessments": {
            name: {
                "status": "valid",
                "score": 1.0,
                "reason": "Evidence",
                "evidence": ["message-0"],
            }
            for name in EPISODE_RUBRICS
        },
    }
    verdict = EpisodeVerdict.model_validate(payload)
    with pytest.raises(ValueError, match="violated requirement"):
        validate_episode_verdict(verdict, {"message-0"})
