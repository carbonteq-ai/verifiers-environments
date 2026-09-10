"""Optional whole-episode reasoning and action quality assessment.

No model runtime is loaded here. The composition host supplies the endpoint,
model identity, and authentication environment variable through native config.
The seven ratings remain independent annotations and do not add another native
AutomationBench task reward.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

import verifiers.v1 as vf
from pydantic import Field, FiniteFloat

from .episode_prompt import (
    EPISODE_PROMPT_VERSION,
    EPISODE_RUBRICS,
    GENERAL_EPISODE_JUDGE_SYSTEM_PROMPT,
    WireEpisodeVerdict,
    build_episode_judge_messages,
    normalize_wire_verdict,
    validate_episode_verdict,
)
from .limited_tools import selected_tool_definitions

CONTEXT_PROJECTION = "automationbench-judge-context@2"


def project_tool_observation(content: str) -> str:
    """Compact JSON syntax without removing any observed behavior."""

    source_digest = hashlib.sha256(content.encode()).hexdigest()
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        value = content
    payload = {
        "projection": CONTEXT_PROJECTION,
        "source_sha256": source_digest,
        "value": value,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class EpisodeQualityConfig(vf.JudgeConfig):
    code_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    # Hosted providers can expose immutable model versions that are not Git SHAs.
    model_revision: str = Field(min_length=1)
    rubric: str = Field(default=GENERAL_EPISODE_JUDGE_SYSTEM_PROMPT, min_length=1)
    attempts: int = Field(default=2, ge=1, le=3)
    timeout_seconds: float = Field(default=60.0, gt=0, le=900, allow_inf_nan=False)
    input_budget_tokens: int = Field(ge=1)
    # The output does not implicitly add another native trajectory reward.
    weight: FiniteFloat = 0.0


class AutomationBenchEpisodeJudge(vf.Judge[WireEpisodeVerdict, EpisodeQualityConfig]):
    """Assess one complete native episode with one versioned rubric contract."""

    schema = WireEpisodeVerdict

    @property
    def scorer_digest(self) -> str:
        identity = {
            "code_revision": self.config.code_revision,
            "model": self.config.model,
            "model_revision": self.config.model_revision,
            "rubric": self.config.rubric,
            "sampling": self.config.sampling.model_dump(mode="json"),
            "attempts": self.config.attempts,
            "timeout_seconds": self.config.timeout_seconds,
            "schema": WireEpisodeVerdict.model_json_schema(),
            "structured_output": True,
            "projection": EPISODE_PROMPT_VERSION,
            "context_projection": CONTEXT_PROJECTION,
            "input_budget_tokens": self.config.input_budget_tokens,
            "episode_rubrics": EPISODE_RUBRICS,
        }
        return hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    async def score(self, task: vf.TaskData, trace: vf.Trace) -> dict[str, float]:
        if len(trace.branches) != 1:
            raise ValueError("episode judge requires one complete single-agent trajectory")
        if "posttrain_episode_rewards" in trace.info:
            raise ValueError("episode already assessed; use fresh evidence for reassessment")
        trajectory: list[dict[str, Any]] = []
        for index, node in enumerate(trace.branches[0].nodes):
            entry = node.message.model_dump(mode="json", exclude_none=True)
            entry["message_id"] = f"message-{index}"
            if entry["role"] == "tool" and isinstance(entry.get("content"), str):
                entry["content"] = project_tool_observation(entry["content"])
            trajectory.append(entry)
        available_tools = selected_tool_definitions(
            tuple(str(name) for name in getattr(task, "zapier_tools", ()))
        )
        messages, request, input_digest = build_episode_judge_messages(
            trace_id=trace.id,
            trajectory=trajectory,
            available_tools=available_tools,
            system_prompt=self.config.rubric,
        )
        wire_messages = [message.model_dump(mode="json", exclude_none=True) for message in messages]
        attempts: list[dict[str, Any]] = []
        trace.info["posttrain_episode_reward_attempts"] = attempts
        message_ids = [item["message_id"] for item in trajectory]
        known = set(message_ids)
        for ordinal in range(self.config.attempts):
            attempt: dict[str, Any] = {
                "attempt": ordinal + 1,
                "messages": wire_messages,
                "assessment_request": request,
                "input_digest": input_digest,
                "status": "failed",
            }
            attempts.append(attempt)
            try:
                async with asyncio.timeout(self.config.timeout_seconds):
                    response = await self.complete(messages, trace=trace, schema=WireEpisodeVerdict)
                attempt["raw_response"] = response.text
                wire_verdict = WireEpisodeVerdict.model_validate_json(response.text)
                verdict = normalize_wire_verdict(wire_verdict, message_ids)
                validate_episode_verdict(verdict, known)
                attempt["status"] = "valid"
                digest = self.scorer_digest
                trace.info["posttrain_scorer_digest"] = digest
                trace.info["posttrain_episode_rewards"] = {
                    "trace_id": trace.id,
                    "scope": "episode",
                    "scorer_digest": digest,
                    **verdict.model_dump(mode="json"),
                }
                for name, rating in verdict.assessments.items():
                    trace.info[f"episode_reward/{name}"] = rating.score
                return {}
            except asyncio.CancelledError:
                attempt["status"] = "cancelled"
                raise
            except Exception as error:  # noqa: BLE001
                attempt["error_type"] = type(error).__name__
                attempt["status"] = "invalid_output" if isinstance(error, ValueError) else "failed"
        raise ValueError("episode judge exhausted bounded attempts; no rewards admitted")


__all__ = ["AutomationBenchEpisodeJudge", "EpisodeQualityConfig", "project_tool_observation"]
