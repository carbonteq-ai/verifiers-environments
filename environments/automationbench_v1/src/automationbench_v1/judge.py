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
import re
from typing import Any, Literal

import verifiers.v1 as vf
from pydantic import Field, FiniteFloat

from .episode_prompt import (
    EPISODE_PROMPT_VERSION,
    EPISODE_RUBRICS,
    GENERAL_EPISODE_JUDGE_SYSTEM_PROMPT,
    MODEL_NATIVE_FRAME_REQUEST,
    MODEL_NATIVE_REVIEW_REQUEST,
    MODEL_NATIVE_VERDICT_REQUEST,
    EpisodeAssessmentFrame,
    EpisodeVocabularyProfile,
    WireEpisodeVerdict,
    build_episode_judge_messages,
    model_native_frame_request,
    normalize_wire_verdict,
    validate_episode_verdict,
)
from .limited_tools import selected_tool_definitions

CONTEXT_PROJECTION = "automationbench-judge-context@2"
MAX_RETAINED_ERROR_CHARACTERS = 500
_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]+\b"),
)


def _safe_error(error: Exception) -> dict[str, Any]:
    """Retain an actionable bounded diagnosis without persisting credentials."""

    message = " ".join(str(error).split()) or type(error).__name__
    for pattern in _SECRET_PATTERNS:
        message = pattern.sub(
            lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]",
            message,
        )
    detail: dict[str, Any] = {
        "type": type(error).__name__,
        "message": message[:MAX_RETAINED_ERROR_CHARACTERS],
    }
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int) and not isinstance(status_code, bool):
        detail["status_code"] = status_code
    return detail


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
    # The model-native frame preserves the fixed wire verdict but lets the
    # selected judge organize each episode in vocabulary it finds natural.
    # Direct mode remains the explicit compatibility contract for prior runs.
    assessment_protocol: Literal[
        "direct@1", "model-native-frame@1", "model-native-frame-review@1"
    ] = "direct@1"
    # A model's own explanation of the domain-general judging task. This is
    # prompt phrasing only; it cannot replace framework-owned semantics or the
    # machine-validatable verdict schema.
    vocabulary_profile: EpisodeVocabularyProfile | None = None
    assessment_frame_max_tokens: int = Field(default=2048, ge=256, le=4096)
    assessment_review_max_tokens: int = Field(default=4096, ge=256, le=8192)
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
            "assessment_protocol": self.config.assessment_protocol,
            "assessment_frame_max_tokens": self.config.assessment_frame_max_tokens,
            "assessment_frame_schema": EpisodeAssessmentFrame.model_json_schema(),
            "assessment_frame_request": MODEL_NATIVE_FRAME_REQUEST,
            "vocabulary_profile": (
                self.config.vocabulary_profile.model_dump(mode="json")
                if self.config.vocabulary_profile is not None
                else None
            ),
            "assessment_verdict_request": MODEL_NATIVE_VERDICT_REQUEST,
            "assessment_review_request": MODEL_NATIVE_REVIEW_REQUEST,
            "assessment_review_max_tokens": self.config.assessment_review_max_tokens,
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
                    verdict_messages = messages
                    if self.config.assessment_protocol in {
                        "model-native-frame@1",
                        "model-native-frame-review@1",
                    }:
                        frame_messages = messages + [
                            vf.UserMessage(
                                content=model_native_frame_request(self.config.vocabulary_profile)
                            )
                        ]
                        attempt["assessment_frame_messages"] = [
                            message.model_dump(mode="json", exclude_none=True)
                            for message in frame_messages
                        ]
                        frame_response = await self.complete(
                            frame_messages,
                            trace=trace,
                            schema=EpisodeAssessmentFrame,
                            max_tokens=self.config.assessment_frame_max_tokens,
                        )
                        attempt["assessment_frame_raw_response"] = frame_response.text
                        frame = EpisodeAssessmentFrame.model_validate_json(frame_response.text)
                        attempt["assessment_frame"] = frame.model_dump(mode="json")
                        verdict_messages = frame_messages + [
                            vf.AssistantMessage(content=frame_response.text),
                            vf.UserMessage(content=MODEL_NATIVE_VERDICT_REQUEST),
                        ]
                    response = await self.complete(
                        verdict_messages, trace=trace, schema=WireEpisodeVerdict
                    )
                    if self.config.assessment_protocol == "model-native-frame-review@1":
                        attempt["provisional_raw_response"] = response.text
                        # The provisional verdict is not admitted. Validating
                        # its shape only guarantees that the model reviews a
                        # complete machine-readable draft rather than free-form
                        # text.
                        WireEpisodeVerdict.model_validate_json(response.text)
                        review_messages = verdict_messages + [
                            vf.AssistantMessage(content=response.text),
                            vf.UserMessage(content=MODEL_NATIVE_REVIEW_REQUEST),
                        ]
                        attempt["assessment_review_messages"] = [
                            message.model_dump(mode="json", exclude_none=True)
                            for message in review_messages
                        ]
                        response = await self.complete(
                            review_messages,
                            trace=trace,
                            schema=WireEpisodeVerdict,
                            max_tokens=self.config.assessment_review_max_tokens,
                        )
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
                failure = _safe_error(error)
                attempt["error"] = failure
                # Compatibility for existing trace readers. New readers should
                # use the structured error record above.
                attempt["error_type"] = failure["type"]
                attempt["status"] = "invalid_output" if isinstance(error, ValueError) else "failed"
        last_error = attempts[-1].get("error", {})
        raise ValueError(
            "episode judge exhausted bounded attempts; no rewards admitted; "
            f"last_error={last_error.get('type', 'unknown')}: "
            f"{last_error.get('message', 'unavailable')}"
        )


__all__ = ["AutomationBenchEpisodeJudge", "EpisodeQualityConfig", "project_tool_observation"]
