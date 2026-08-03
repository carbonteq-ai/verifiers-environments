"""GSM8K grade-school math tasks for the Verifiers v1 runtime.

The task data keeps the immutable Hugging Face source identity alongside the row.
That makes a native Verifiers trace replayable without making the framework own the
dataset or its cache. Answer verification remains an in-runtime ``math-verify``
script, matching the upstream Verifiers environment's trust boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast

import verifiers.v1 as vf
from datasets import load_dataset
from pydantic import field_validator

DEFAULT_DATASET_REPO = "openai/gsm8k"
DEFAULT_DATASET_REVISION = "740312add88f781978c0658806c59bc2815b9866"
DEFAULT_DATASET_CONFIG = "main"
DEFAULT_SPLIT: Literal["train", "test"] = "test"
EXPECTED_ROW_COUNTS: dict[str, int] = {"train": 7_473, "test": 1_319}

SYSTEM = (
    "Solve the grade-school math problem. Reason step by step, then give the final "
    "answer as a single number on the last line, prefixed with '#### ' (e.g. '#### 42')."
)
VERIFY = (Path(__file__).parent / "verify.py").read_bytes()


def normalized_row_digest(row: Mapping[str, Any]) -> str:
    """Return the SHA-256 of a row's canonical JSON representation.

    GSM8K currently has two string columns, but hashing every source column means an
    upstream row correction cannot silently retain the old task identity. Compact,
    sorted-key JSON and UTF-8 make the digest independent of Python dict ordering.
    """

    normalized = json.dumps(
        dict(row),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _require_revision(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("dataset_revision must be a full 40-character lowercase Git SHA")
    return value


class GSM8KData(vf.TaskData):
    """One GSM8K row plus the source identity needed to replay it."""

    answer: str
    dataset_repo: str
    dataset_revision: str
    dataset_config: str
    split: Literal["train", "test"]
    row_digest: str


class GSM8KTask(vf.Task[GSM8KData]):
    @vf.reward(weight=1.0)
    async def correct(self, trace: vf.Trace, runtime: vf.Runtime) -> float:
        """Score the model's final answer inside the rollout runtime."""

        result = await runtime.run_uv_script(
            VERIFY,
            args=[self.data.answer, trace.last_reply or ""],
        )
        if result.exit_code != 0:
            raise RuntimeError(f"verify.py failed: {result.stderr.strip()[-500:]}")
        lines = result.stdout.strip().splitlines()
        return float(lines[-1]) if lines else 0.0

    async def validate(self, runtime: vf.Runtime) -> bool:
        """Check that this task's gold answer is accepted by the verifier."""

        result = await runtime.run_uv_script(
            VERIFY,
            args=[self.data.answer, f"#### {self.data.answer}"],
        )
        if result.exit_code != 0:
            raise RuntimeError(f"verify.py failed: {result.stderr.strip()[-500:]}")
        lines = result.stdout.strip().splitlines()
        return bool(lines) and float(lines[-1]) == 1.0


class GSM8KConfig(vf.TasksetConfig):
    dataset_repo: str = DEFAULT_DATASET_REPO
    dataset_revision: str = DEFAULT_DATASET_REVISION
    dataset_config: str = DEFAULT_DATASET_CONFIG
    split: Literal["train", "test"] = DEFAULT_SPLIT

    _validate_dataset_revision = field_validator("dataset_revision")(_require_revision)


class GSM8KTaskset(vf.Taskset[GSM8KTask, GSM8KConfig]):
    def load(self) -> list[GSM8KTask]:
        rows = list(
            cast(
                list[Mapping[str, Any]],
                load_dataset(
                    self.config.dataset_repo,
                    self.config.dataset_config,
                    split=self.config.split,
                    revision=self.config.dataset_revision,
                ),
            )
        )
        if (
            self.config.dataset_repo == DEFAULT_DATASET_REPO
            and self.config.dataset_revision == DEFAULT_DATASET_REVISION
            and self.config.dataset_config == DEFAULT_DATASET_CONFIG
        ):
            expected = EXPECTED_ROW_COUNTS[self.config.split]
            if len(rows) != expected:
                raise RuntimeError(
                    f"{self.config.dataset_repo}@{self.config.dataset_revision} "
                    f"{self.config.split} has {len(rows)} rows; expected {expected}"
                )

        return [
            GSM8KTask(
                GSM8KData(
                    idx=i,
                    prompt=f"{SYSTEM}\n\n{row['question']}",
                    answer=str(row["answer"]).split("####")[-1].strip(),
                    dataset_repo=self.config.dataset_repo,
                    dataset_revision=self.config.dataset_revision,
                    dataset_config=self.config.dataset_config,
                    split=self.config.split,
                    row_digest=normalized_row_digest(row),
                ),
                self.config.task,
            )
            for i, row in enumerate(rows)
        ]


__all__ = [
    "DEFAULT_DATASET_CONFIG",
    "DEFAULT_DATASET_REPO",
    "DEFAULT_DATASET_REVISION",
    "DEFAULT_SPLIT",
    "EXPECTED_ROW_COUNTS",
    "GSM8KConfig",
    "GSM8KData",
    "GSM8KTask",
    "GSM8KTaskset",
    "normalized_row_digest",
]
