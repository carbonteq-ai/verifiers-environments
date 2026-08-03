"""Deterministic IFEval evaluation tasks for Verifiers v1."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar

import verifiers.v1 as vf
from datasets import Dataset
from pydantic import field_validator

from .instructions import SUPPORTED_INSTRUCTION_IDS, check_instruction, loose_responses

DATASET_REPO = "google/IFEval"
DATASET_REVISION = "966cd89545d6b6acfd7638bc708b98261ca58e84"
DATASET_SPLIT = "train"
LOGICAL_PURPOSE = "evaluation"
REQUIRED_COLUMNS = {"key", "prompt", "instruction_id_list", "kwargs"}


def _row_digest(row: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class IFEvalData(vf.TaskData):
    key: int
    instruction_id_list: tuple[str, ...]
    instruction_kwargs: tuple[dict[str, Any], ...]
    source_repo: str
    source_revision: str
    source_split: str
    logical_purpose: str
    row_digest: str


class IFEvalTask(vf.Task[IFEvalData]):
    def _scores(self, trace: vf.Trace) -> tuple[list[bool], list[bool]]:
        response = trace.last_reply
        strict = [
            bool(response.strip()) and check_instruction(instruction_id, response, kwargs)
            for instruction_id, kwargs in zip(
                self.data.instruction_id_list, self.data.instruction_kwargs, strict=True
            )
        ]
        variants = loose_responses(response)
        loose = [
            any(
                candidate.strip() and check_instruction(instruction_id, candidate, kwargs)
                for candidate in variants
            )
            for instruction_id, kwargs in zip(
                self.data.instruction_id_list, self.data.instruction_kwargs, strict=True
            )
        ]
        return strict, loose

    @vf.metric
    async def loose_instruction_accuracy(self, trace: vf.Trace) -> float:
        _, loose = self._scores(trace)
        return sum(loose) / len(loose) if loose else 0.0

    @vf.metric
    async def strict_instruction_accuracy(self, trace: vf.Trace) -> float:
        strict, _ = self._scores(trace)
        return sum(strict) / len(strict) if strict else 0.0

    @vf.metric
    async def loose_prompt_accuracy(self, trace: vf.Trace) -> float:
        _, loose = self._scores(trace)
        return float(all(loose))

    @vf.reward(weight=1.0)
    async def strict_prompt_accuracy(self, trace: vf.Trace) -> float:
        strict, _ = self._scores(trace)
        return float(all(strict))


class IFEvalConfig(vf.TasksetConfig):
    dataset_repo: str = DATASET_REPO
    dataset_revision: str = DATASET_REVISION
    split: str = DATASET_SPLIT
    logical_purpose: ClassVar[str] = LOGICAL_PURPOSE
    order_seed: int = 0

    @field_validator("dataset_revision")
    @classmethod
    def _revision_is_immutable(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError("dataset_revision must be a full 40-character commit")
        return value

    @field_validator("split")
    @classmethod
    def _evaluation_split_only(cls, value: str) -> str:
        if value != DATASET_SPLIT:
            raise ValueError(
                "IFEval v1 exposes its held-out dataset only as physical split 'train'"
            )
        return value


class IFEvalTaskset(vf.Taskset[IFEvalTask, IFEvalConfig]):
    EXPECTED_ROWS: ClassVar[int] = 541

    def _load(self) -> Dataset:
        from datasets import load_dataset

        loaded = load_dataset(
            self.config.dataset_repo,
            revision=self.config.dataset_revision,
            split=self.config.split,
        )
        if not isinstance(loaded, Dataset):
            raise TypeError(f"expected Dataset, got {type(loaded).__name__}")
        missing = REQUIRED_COLUMNS - set(loaded.column_names)
        if missing:
            raise ValueError(f"IFEval source is missing columns: {sorted(missing)}")
        if (
            self.config.dataset_repo == DATASET_REPO
            and self.config.dataset_revision == DATASET_REVISION
            and len(loaded) != self.EXPECTED_ROWS
        ):
            raise ValueError(f"expected {self.EXPECTED_ROWS} IFEval rows, got {len(loaded)}")
        return loaded

    def load(self) -> Iterable[IFEvalTask]:
        rows = [dict(row) for row in self._load()]
        keys: set[int] = set()
        rows.sort(key=lambda row: int(row["key"]) ^ self.config.order_seed)
        for row in rows:
            key = int(row["key"])
            if key in keys:
                raise ValueError(f"duplicate IFEval source key: {key}")
            keys.add(key)
            instruction_ids = tuple(str(item) for item in row["instruction_id_list"])
            kwargs = tuple(dict(item) for item in row["kwargs"])
            if len(instruction_ids) != len(kwargs):
                raise ValueError(f"IFEval key {key} has mismatched instruction and kwargs lengths")
            unknown = sorted(set(instruction_ids) - set(SUPPORTED_INSTRUCTION_IDS))
            if unknown:
                raise ValueError(f"IFEval key {key} has unregistered instructions: {unknown}")
            data = IFEvalData(
                idx=key,
                name=f"ifeval-{key}",
                prompt=str(row["prompt"]),
                key=key,
                instruction_id_list=instruction_ids,
                instruction_kwargs=kwargs,
                source_repo=self.config.dataset_repo,
                source_revision=self.config.dataset_revision,
                source_split=self.config.split,
                logical_purpose=LOGICAL_PURPOSE,
                row_digest=_row_digest(row),
            )
            yield IFEvalTask(data, self.config.task)


__all__ = [
    "DATASET_REPO",
    "DATASET_REVISION",
    "LOGICAL_PURPOSE",
    "IFEvalConfig",
    "IFEvalData",
    "IFEvalTask",
    "IFEvalTaskset",
]
