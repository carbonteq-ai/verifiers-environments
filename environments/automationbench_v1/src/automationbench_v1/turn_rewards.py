"""Per-turn AutomationBench rewards for SAMPO, measured on the live world.

Record IDs are generated with ``uuid4``, so replaying a finished episode's tool
calls does not rebuild its world: a later call that names an ID created earlier
would fail. Progress is therefore measured during the rollout. Before every
model call the task scores the live world and appends the result to
``trace.info[PROGRESS_KEY]``; ``finalize`` adds the final state and turns the
record into Posttrain's turn evidence (projection ``assistant-turns@1``).

The reward for assistant turn *k* is the change in partial credit its tool calls
caused, minus ``tool_failure_penalty`` for each of its tool calls that failed.
Summed over an episode it equals the final partial credit minus the partial
credit of the untouched world, minus the penalties.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PROGRESS_KEY = "automationbench_turn_progress"
TURN_EVIDENCE_KEY = "posttrain_turn_rewards"
TURN_PROJECTION = "assistant-turns@1"
TURN_REWARD = "turn_reward"


class AutomationBenchTurnRewardConfig(BaseModel):
    """Selects per-turn rewards; the digest identifies the scoring rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_failure_penalty: float = Field(default=0.05, ge=0.0, le=1.0)

    @property
    def scorer_digest(self) -> str:
        identity = {
            "scorer": "automationbench-turn-progress",
            "version": 1,
            "tool_failure_penalty": self.tool_failure_penalty,
        }
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


def record_progress(
    info: dict[str, Any],
    after_turn: int,
    measure: Callable[[], float],
) -> None:
    """Append the live world's partial credit after ``after_turn`` turns, once."""

    progress = info.setdefault(PROGRESS_KEY, [])
    if progress and progress[-1]["after_turn"] >= after_turn:
        return
    try:
        entry: dict[str, Any] = {"after_turn": after_turn, "partial_credit": float(measure())}
    except Exception as error:  # noqa: BLE001 - strict assertions can reject an odd mid-episode world
        entry = {"after_turn": after_turn, "error": f"{type(error).__name__}: {error}"[:500]}
    progress.append(entry)


def tool_result_failed(content: object) -> bool:
    """Whether a tool result reports a failure (tool error, raised call, harness error)."""

    text = _text(content).strip()
    if text.startswith(("error:", "Error executing tool")):
        return True
    try:
        payload = json.loads(text)
    except ValueError:
        return False
    return isinstance(payload, Mapping) and (
        bool(payload.get("error")) or payload.get("success") is False
    )


def turn_evidence(
    *,
    trace_id: str,
    turns: Sequence[Any],
    tool_results: Mapping[str, object],
    progress: Sequence[Mapping[str, Any]],
    config: AutomationBenchTurnRewardConfig,
) -> dict[str, Any]:
    """Build Posttrain's ``assistant-turns@1`` evidence for the sampled assistant turns.

    ``turns`` are the sampled assistant messages of the trained branch, in order;
    their IDs ``assistant-<index>`` match Posttrain's native turn map.
    A turn whose world could not be scored keeps the last scored credit, so its
    progress counts as zero rather than inventing a value.
    """

    credit_after: dict[int, float] = {}
    last = 0.0
    for entry in sorted(progress, key=lambda item: item["after_turn"]):
        if "partial_credit" in entry:
            last = float(entry["partial_credit"])
        credit_after[int(entry["after_turn"])] = last
    assessments = []
    previous = credit_after.get(0, 0.0)
    for index, message in enumerate(turns):
        current = credit_after.get(index + 1, previous)
        calls = getattr(message, "tool_calls", None) or []
        failures = sum(
            1
            for call in calls
            if call.id in tool_results and tool_result_failed(tool_results[call.id])
        )
        progress_value = current - previous
        reward = progress_value - config.tool_failure_penalty * failures
        assessments.append(
            {
                "turn_id": f"assistant-{index}",
                "components": [
                    {"name": TURN_REWARD, "status": "valid", "value": reward},
                    {"name": "assertion_progress", "status": "valid", "value": progress_value},
                    {"name": "tool_failures", "status": "valid", "value": float(failures)},
                ],
                "evidence_ref": f"{trace_id}#{PROGRESS_KEY}/{index + 1}",
            }
        )
        previous = current
    return {
        "trace_id": trace_id,
        "branch_id": "0",
        "projection_id": TURN_PROJECTION,
        "scorer_digest": config.scorer_digest,
        "assessments": assessments,
    }


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        parts = []
        for part in content:
            text = part.get("text") if isinstance(part, Mapping) else getattr(part, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return ""


__all__ = [
    "PROGRESS_KEY",
    "TURN_EVIDENCE_KEY",
    "TURN_PROJECTION",
    "TURN_REWARD",
    "AutomationBenchTurnRewardConfig",
    "record_progress",
    "tool_result_failed",
    "turn_evidence",
]
