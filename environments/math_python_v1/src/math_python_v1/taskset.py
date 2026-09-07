"""Pinned MATH-lighteval taskset with boxed-answer verification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Literal, cast

import verifiers.v1 as vf
from datasets import load_dataset
from pydantic import Field, field_validator

from math_python_v1.servers import PythonState, PythonToolset, PythonToolsetConfig

MATH_REPOSITORY = "DigitalLearningGmbH/MATH-lighteval"
MATH_REVISION = "0530c78699ea5e8eb5530600900e1f328b48acad"
MATH_SYSTEM_PROMPT = (
    "Solve the problem with concise, essential reasoning. Keep the reasoning under 2,000 words. "
    "Use the Python tool within the first 1,000 words when it is useful. Once you have a candidate "
    "answer, verify it at most once, stop immediately, and put the final answer inside "
    "\\boxed{...}. Never repeat a completed derivation."
)


def _boxed_answer(solution: str) -> str:
    answer = vf.extract_boxed_answer(solution, strict=True).strip()
    if not answer:
        raise ValueError("MATH solution has no final boxed answer")
    return answer


class MathPythonData(vf.TaskData):
    answer: str
    solution: str
    level: str
    problem_type: str
    source_repository: str = MATH_REPOSITORY
    source_revision: str = MATH_REVISION
    row_digest: str


class MathPythonTaskConfig(vf.TaskConfig):
    verify_timeout_seconds: int = Field(default=5, ge=1, le=30)
    python_tool: PythonToolsetConfig = Field(default_factory=PythonToolsetConfig)


class MathPythonTask(vf.Task[MathPythonData, PythonState, MathPythonTaskConfig]):
    tools = (cast(type[vf.Toolset], PythonToolset),)

    @classmethod
    def toolsets(cls, config: MathPythonTaskConfig) -> list[vf.Toolset]:
        """Construct the task-scoped Python runtime through the native v0.3 API."""
        return cast(list[vf.Toolset], [PythonToolset(config.python_tool)])

    def _verification(self, trace: vf.Trace) -> float:
        task_config = cast(MathPythonTaskConfig, self.config)
        return vf.verify_boxed_math_answer(
            trace.last_reply,
            f"\\boxed{{{self.data.answer}}}",
            timeout_seconds=task_config.verify_timeout_seconds,
        )

    @vf.metric
    async def parse_success(self, trace: vf.Trace) -> float:
        return float(bool(vf.extract_boxed_answer(trace.last_reply, strict=True).strip()))

    @vf.metric
    async def symbolic_correctness(self, trace: vf.Trace) -> float:
        return self._verification(trace)

    @vf.reward
    async def math_reward(self, trace: vf.Trace) -> float:
        return self._verification(trace)


class MathPythonConfig(vf.TasksetConfig):
    repository: str = MATH_REPOSITORY
    revision: str = MATH_REVISION
    split: Literal["train", "test"] = "test"
    start_index: int = Field(default=0, ge=0)
    num_tasks: int = Field(default=100, ge=1, le=12_500)
    order_seed: int = Field(default=0, ge=0)
    balance_by_type: bool = False
    levels: tuple[str, ...] = ()
    problem_types: tuple[str, ...] = ()
    python_tool: PythonToolsetConfig = Field(default_factory=PythonToolsetConfig)

    @field_validator("levels", "problem_types")
    @classmethod
    def _unique_nonempty_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() for value in values):
            raise ValueError("filters must not contain empty values")
        if len(set(values)) != len(values):
            raise ValueError("filters must not contain duplicates")
        return values


# Verifiers' Taskset bound keeps State invariant even though runtime state specialization is valid.
class MathPythonTaskset(
    vf.Taskset[MathPythonTask, MathPythonConfig]  # pyright: ignore[reportInvalidTypeArguments]
):
    def load(self) -> Iterable[MathPythonTask]:
        if self.config.repository != MATH_REPOSITORY or self.config.revision != MATH_REVISION:
            raise ValueError(
                f"Math Python requires {MATH_REPOSITORY}@{MATH_REVISION}; "
                f"got {self.config.repository}@{self.config.revision}"
            )
        rows = load_dataset(
            self.config.repository,
            revision=self.config.revision,
            split=self.config.split,
        )
        indices: list[int] = []
        for idx, row in enumerate(rows):
            row_map = cast(Mapping[str, object], row)
            level_matches = (
                not self.config.levels or str(row_map.get("level", "")) in self.config.levels
            )
            type_matches = (
                not self.config.problem_types
                or str(row_map.get("type", "")) in self.config.problem_types
            )
            if not (level_matches and type_matches):
                continue
            # Selection is a reliability boundary: a source row without the
            # verifier's required terminal answer must never make an otherwise
            # valid long-running job fail when the row is reached later.
            try:
                _boxed_answer(str(row_map.get("solution", "")))
            except ValueError:
                continue
            indices.append(idx)
        if not indices:
            raise ValueError("MATH filters selected no rows")
        if self.config.balance_by_type:
            groups: dict[str, list[int]] = {}
            for idx in indices:
                row_map = cast(Mapping[str, object], rows[idx])
                groups.setdefault(str(row_map.get("type", "")), []).append(idx)
            for group in groups.values():
                group.sort(
                    key=lambda idx: hashlib.sha256(
                        f"{self.config.order_seed}:{idx}".encode()
                    ).hexdigest()
                )
            indices = [
                group[offset]
                for offset in range(max(map(len, groups.values()), default=0))
                for group in groups.values()
                if offset < len(group)
            ]
        end = min(self.config.start_index + self.config.num_tasks, len(indices))
        if self.config.start_index >= end:
            raise ValueError("start_index is outside the selected split")
        for idx in indices[self.config.start_index : end]:
            row = rows[idx]
            solution = str(row["solution"])
            answer = _boxed_answer(solution)
            problem = str(row["problem"])
            level = str(row.get("level", ""))
            problem_type = str(row.get("type", ""))
            payload = {
                "idx": idx,
                "problem": problem,
                "solution": solution,
                "level": level,
                "type": problem_type,
                "repository": self.config.repository,
                "revision": self.config.revision,
            }
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            data = MathPythonData(
                idx=idx,
                name=f"{self.config.split}:{idx}",
                prompt=problem,
                system_prompt=MATH_SYSTEM_PROMPT,
                answer=answer,
                solution=solution,
                level=level,
                problem_type=problem_type,
                row_digest=digest,
            )
            yield MathPythonTask(
                data,
                MathPythonTaskConfig(python_tool=self.config.python_tool),
            )


__all__ = [
    "MATH_REPOSITORY",
    "MATH_REVISION",
    "MATH_SYSTEM_PROMPT",
    "MathPythonConfig",
    "MathPythonData",
    "MathPythonTask",
    "MathPythonTaskConfig",
    "MathPythonTaskset",
]
