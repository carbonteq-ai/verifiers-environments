"""Pinned MATH-lighteval taskset with boxed-answer verification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Literal, cast

import verifiers.v1 as vf
from datasets import load_dataset
from pydantic import Field

from math_python_v1.servers import PythonToolset, PythonToolsetConfig

MATH_REPOSITORY = "DigitalLearningGmbH/MATH-lighteval"
MATH_REVISION = "0530c78699ea5e8eb5530600900e1f328b48acad"


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


class MathPythonTask(vf.Task[MathPythonData, vf.State, vf.TaskConfig]):
    tools = (cast(type[vf.Toolset], PythonToolset),)

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
    python_tool: PythonToolsetConfig = Field(default_factory=PythonToolsetConfig)


class MathPythonTaskset(vf.Taskset[MathPythonTask, MathPythonConfig]):
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
        end = min(self.config.start_index + self.config.num_tasks, len(rows))
        if self.config.start_index >= end:
            raise ValueError("start_index is outside the selected split")
        for idx in range(self.config.start_index, end):
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
    "MathPythonConfig",
    "MathPythonData",
    "MathPythonTask",
    "MathPythonTaskConfig",
    "MathPythonTaskset",
]
