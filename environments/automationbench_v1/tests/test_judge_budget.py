"""The judge counts the exact served chat request before asking for a verdict."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import verifiers.v1 as vf

from automationbench_v1 import judge as judge_module
from automationbench_v1.episode_prompt import build_episode_judge_messages
from automationbench_v1.judge import AutomationBenchEpisodeJudge, EpisodeQualityConfig
from automationbench_v1.judge_budget import JudgeBudgetError, admitted_output_tokens


def _trace(content: str = "Do the task.") -> Any:
    return SimpleNamespace(
        id="trace",
        info={},
        branches=[SimpleNamespace(nodes=[SimpleNamespace(message=vf.UserMessage(content=content))])],
    )


def _judge(**overrides: Any) -> AutomationBenchEpisodeJudge:
    values = {
        "id": "automationbench-v1",
        "code_revision": "a" * 40,
        "model_revision": "b" * 40,
        "model": "google/gemma-4-12B-it",
        "base_url": "http://localhost:8123/v1",
        "api_key_var": "TEST_JUDGE_API_KEY",
        "input_budget_tokens": 12_288,
        "budget_tokenizer": "vllm-chat@1",
        "context_window_tokens": 32_768,
        "sampling": {"max_tokens": 16_384, "extra_body": {"chat_template_kwargs": {"enable_thinking": True}}},
        "attempts": 2,
    }
    values.update(overrides)
    return AutomationBenchEpisodeJudge(EpisodeQualityConfig(**values))


def _verdict() -> dict[str, Any]:
    names = (
        "problem_understanding_planning",
        "logical_correctness",
        "verification_self_correction",
        "progress_efficiency",
        "action_quality",
        "answer_quality",
    )
    return {
        "requirement_checks": [
            {
                "requirement": "Do the task",
                "outcome": "unknown",
                "explanation": "No observed completion.",
                "evidence": [0],
                "relevant_dimensions": [],
            }
        ],
        "assessments": {
            name: {"status": "valid", "score": 0.5, "reason": "Unverified.", "evidence": [0]}
            for name in names
        },
    }


def test_output_allowance_respects_measured_context() -> None:
    assert admitted_output_tokens(
        input_tokens=16_000,
        server_context_tokens=32_768,
        configured_context_tokens=32_768,
        requested_output_tokens=16_384,
        safety_margin_tokens=256,
        minimum_output_tokens=512,
    ) == 16_384
    assert admitted_output_tokens(
        input_tokens=20_000,
        server_context_tokens=32_768,
        configured_context_tokens=32_768,
        requested_output_tokens=16_384,
        safety_margin_tokens=256,
        minimum_output_tokens=512,
    ) == 12_512
    with pytest.raises(JudgeBudgetError, match="rendered judge input"):
        admitted_output_tokens(
            input_tokens=12_289,
            server_context_tokens=32_768,
            configured_context_tokens=32_768,
            requested_output_tokens=16_384,
            safety_margin_tokens=256,
            minimum_output_tokens=512,
            initial_input_budget_tokens=12_288,
        )


def test_compact_wire_payload_retains_every_evidence_field() -> None:
    messages, request, _ = build_episode_judge_messages(
        trace_id="trace",
        trajectory=[{"role": "tool", "content": "important observation", "message_id": "message-0"}],
        available_tools=[{"type": "function", "function": {"name": "lookup", "parameters": {}}}],
    )
    content = messages[1].content
    assert isinstance(content, str)
    assert json.loads(content) == request
    assert len(content) < len(json.dumps(request, ensure_ascii=False, sort_keys=True))


def test_vllm_tokenizer_receives_exact_chat_and_template_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    from automationbench_v1 import judge_budget

    recorded: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tokenize"
        assert request.headers["Authorization"] == "Bearer test"
        recorded.append(json.loads(request.content))
        return httpx.Response(200, json={"count": 8_000, "max_model_len": 32_768, "tokens": []})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        judge_budget.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    measured = asyncio.run(
        judge_budget.measure_vllm_chat_tokens(
            base_url="http://localhost:8123/v1",
            model="google/gemma-4-12B-it",
            messages=[{"role": "system", "content": "rubric"}, {"role": "user", "content": "episode"}],
            api_key="test",
            headers={},
            chat_template_kwargs={"enable_thinking": True},
        )
    )
    assert measured == (8_000, 32_768)
    assert recorded == [
        {
            "model": "google/gemma-4-12B-it",
            "messages": [{"role": "system", "content": "rubric"}, {"role": "user", "content": "episode"}],
            "add_generation_prompt": True,
            "chat_template_kwargs": {"enable_thinking": True},
        }
    ]


def test_oversized_episode_is_recorded_once_without_calling_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_JUDGE_API_KEY", "test")

    async def measured(**kwargs: Any) -> tuple[int, int]:
        return 16_385, 32_768

    judge = _judge()
    calls = 0

    async def complete(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return vf.JudgeResponse(text=json.dumps(_verdict()))

    monkeypatch.setattr(judge_module, "measure_vllm_chat_tokens", measured)
    monkeypatch.setattr(judge, "complete", complete)
    trace = _trace()
    with pytest.raises(ValueError, match="rendered judge input has 16385 tokens"):
        asyncio.run(judge.score(SimpleNamespace(zapier_tools=()), trace))  # pyright: ignore[reportArgumentType]
    assert calls == 0
    assert len(trace.info["posttrain_episode_reward_attempts"]) == 1
    assert trace.info["posttrain_episode_reward_attempts"][0]["status"] == "unjudgeable"
    assert "posttrain_episode_rewards" not in trace.info


def test_admitted_episode_uses_bounded_output_and_records_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_JUDGE_API_KEY", "test")

    async def measured(**kwargs: Any) -> tuple[int, int]:
        return 12_000, 28_000

    judge = _judge()
    outputs: list[int] = []

    async def complete(*args: Any, **kwargs: Any) -> Any:
        outputs.append(kwargs["max_tokens"])
        return vf.JudgeResponse(text=json.dumps(_verdict()))

    monkeypatch.setattr(judge_module, "measure_vllm_chat_tokens", measured)
    monkeypatch.setattr(judge, "complete", complete)
    trace = _trace()
    assert asyncio.run(judge.score(SimpleNamespace(zapier_tools=()), trace)) == {}  # pyright: ignore[reportArgumentType]
    assert outputs == [15_744]
    assert trace.info["posttrain_episode_reward_attempts"][0]["token_budget"] == [
        {"stage": "verdict", "input_tokens": 12_000, "output_tokens": 15_744, "server_context_tokens": 28_000}
    ]
