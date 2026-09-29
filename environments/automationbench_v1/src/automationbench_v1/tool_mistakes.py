"""Tool results the model could have avoided, told apart from empty searches.

A tool result "fails" whenever it reports an error, but not every failure is a
mistake. A search that finds nothing tells the model something; calling a tool
that does not exist, sending arguments the tool rejects, or asking for a record
by an ID that was never returned are mistakes. Training can penalize the second
kind without teaching the model to stop searching.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

INVALID_ARGUMENTS = "invalid_arguments"
MISSING_ARGUMENTS = "missing_arguments"
UNKNOWN_TOOL = "unknown_tool"
UNKNOWN_ID = "unknown_id"
EMPTY_RESULT = "empty_result"
OTHER_FAILURE = "other_failure"

# Kinds the model controls; each costs the episode when a penalty is selected.
MISTAKES = frozenset({INVALID_ARGUMENTS, MISSING_ARGUMENTS, UNKNOWN_TOOL, UNKNOWN_ID})

# Tools that look things up by criteria; "not found" from them is an answer.
_SEARCH_WORDS = re.compile(r"(^|_)(find|search|list|lookup|query)(_|$)")
_NOT_FOUND = re.compile(r"\b(not found|does not exist|no such)\b", re.IGNORECASE)
_NO_MATCH = re.compile(r"\bno (matching|results?|records?|items?)\b", re.IGNORECASE)


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text", "")) if isinstance(part, Mapping) else str(part)
            for part in content
        )
    return "" if content is None else str(content)


def classify_tool_result(tool_name: str | None, content: object) -> str | None:
    """The kind of failure a tool result reports, or ``None`` when it succeeded."""

    text = _text(content).strip()
    if text.startswith("error: unknown tool") or "is not enabled for this task" in text:
        return UNKNOWN_TOOL
    if text.startswith("Error executing tool"):
        if "unknown AutomationBench tool" in text:
            return UNKNOWN_TOOL
        if "validation error" in text:
            if "type=missing" in text or "Field required" in text:
                return MISSING_ARGUMENTS
            return INVALID_ARGUMENTS
        return OTHER_FAILURE
    if text.startswith("error:"):
        return OTHER_FAILURE
    try:
        payload: Any = json.loads(text)
    except ValueError:
        return None
    if not isinstance(payload, Mapping) or not (
        payload.get("error") or payload.get("success") is False
    ):
        return None
    message = str(payload.get("error") or payload.get("message") or "")
    searching = bool(tool_name and _SEARCH_WORDS.search(tool_name))
    if _NO_MATCH.search(message) or (searching and _NOT_FOUND.search(message)):
        return EMPTY_RESULT
    if _NOT_FOUND.search(message):
        return UNKNOWN_ID
    return OTHER_FAILURE


def is_mistake(kind: str | None) -> bool:
    return kind in MISTAKES


class AutomationBenchMistakePenaltyConfig(BaseModel):
    """Selects an episode penalty for tool mistakes: ``per_mistake`` each, at most ``cap``.

    The cap keeps the penalty below typical partial-credit differences between
    attempts at one task, so finishing the task stays the larger reward.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    per_mistake: float = Field(default=0.02, ge=0.0, le=1.0)
    cap: float = Field(default=0.1, ge=0.0, le=1.0)

    def penalty(self, mistakes: int) -> float:
        return min(self.cap, self.per_mistake * mistakes)


__all__ = [
    "EMPTY_RESULT",
    "INVALID_ARGUMENTS",
    "MISSING_ARGUMENTS",
    "MISTAKES",
    "OTHER_FAILURE",
    "UNKNOWN_ID",
    "UNKNOWN_TOOL",
    "AutomationBenchMistakePenaltyConfig",
    "classify_tool_result",
    "is_mistake",
]
