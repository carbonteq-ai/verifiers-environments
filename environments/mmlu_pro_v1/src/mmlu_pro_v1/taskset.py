"""Deterministic MMLU-Pro evaluation tasks for Verifiers v1."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from typing import Any, ClassVar

import verifiers.v1 as vf
from datasets import Dataset, load_dataset
from pydantic import field_validator, model_validator

DATASET_REPO = "TIGER-Lab/MMLU-Pro"
DATASET_REVISION = "b189ec765aa7ed75c8acfea42df31fdae71f97be"
VALIDATION_SPLIT = "validation"
TEST_SPLIT = "test"
CATEGORIES = (
    "biology",
    "business",
    "chemistry",
    "computer science",
    "economics",
    "engineering",
    "health",
    "history",
    "law",
    "math",
    "other",
    "philosophy",
    "physics",
    "psychology",
)
CHOICES = tuple("ABCDEFGHIJ")
REQUIRED_COLUMNS = {
    "question_id",
    "question",
    "options",
    "answer",
    "answer_index",
    "cot_content",
    "category",
}


def _normalized_digest(row: dict[str, Any]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _options(row: dict[str, Any]) -> list[str]:
    """Apply the reference preprocessing: remove only literal ``N/A`` options."""

    return [str(option) for option in row["options"] if option != "N/A"]


def format_example(row: dict[str, Any], *, including_answer: bool) -> str:
    options = _options(row)
    lines = ["Question:", str(row["question"]), "Options:"]
    lines.extend(f"{CHOICES[index]}. {option}" for index, option in enumerate(options))
    if including_answer:
        cot = str(row.get("cot_content", ""))
        cot = cot.replace("A: Let's think step by step.", "Answer: Let's think step by step.")
        lines.extend([cot, ""])
    else:
        lines.append("Answer: Let's think step by step.")
    return "\n".join(lines)


def build_prompt(
    validation_rows: Sequence[dict[str, Any]],
    row: dict[str, Any],
    *,
    shots: int,
) -> tuple[str, tuple[int, ...]]:
    category = str(row["category"])
    demonstrations = [item for item in validation_rows if item["category"] == category][:shots]
    subject = (
        "The following are multiple choice questions (with answers) about {$}. "
        'Think step by step and then finish your answer with "the answer is (X)" where X is the correct letter choice.'
    ).replace("{$}", subject := category)
    prompt = subject + "\n"
    prompt += "\n".join(format_example(item, including_answer=True) for item in demonstrations)
    if demonstrations:
        prompt += "\n"
    prompt += format_example(row, including_answer=False)
    return prompt, tuple(int(item["question_id"]) for item in demonstrations)


def extract_answer(text: str) -> str | None:
    """Use the ordered parser from the pinned MMLU-Pro evaluator."""

    match = re.search(r"answer is \(?(?P<label>[A-J])\)?", text, flags=re.IGNORECASE)
    if match:
        return match.group("label").upper()
    match = re.search(r".*[aA]nswer:\s*(?P<label>[A-J])", text)
    if match:
        return match.group("label").upper()
    matches = re.findall(r"\b[A-J]\b(?!.*\b[A-J]\b)", text, flags=re.DOTALL)
    return matches[0] if matches else None


class MMLUProData(vf.TaskData):
    question_id: int
    category: str
    answer: str
    answer_index: int
    source_repo: str
    source_revision: str
    validation_demo_ids: tuple[int, ...]
    row_digest: str


class MMLUProTask(vf.Task[MMLUProData]):
    def _parsed_answer(self, trace: vf.Trace) -> str | None:
        return extract_answer(trace.last_reply)

    @vf.metric
    async def answer_parse_success(self, trace: vf.Trace) -> float:
        return float(self._parsed_answer(trace) is not None)

    @vf.reward(weight=1.0)
    async def answer_correct(self, trace: vf.Trace) -> float:
        return float(self._parsed_answer(trace) == self.data.answer)


class MMLUProConfig(vf.TasksetConfig):
    dataset_repo: str = DATASET_REPO
    dataset_revision: str = DATASET_REVISION
    validation_split: str = VALIDATION_SPLIT
    test_split: str = TEST_SPLIT
    categories: tuple[str, ...] = CATEGORIES
    shots: int = 5
    order_seed: int = 0
    balanced: bool = True
    limit_per_category: int = 100

    @field_validator("dataset_revision")
    @classmethod
    def _revision_is_immutable(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError("dataset_revision must be a full 40-character commit")
        return value

    @field_validator("categories")
    @classmethod
    def _categories_are_known(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("categories cannot be empty")
        unknown = sorted(set(value) - set(CATEGORIES))
        if unknown:
            raise ValueError(f"unknown MMLU-Pro categories: {unknown}")
        if len(set(value)) != len(value):
            raise ValueError("categories cannot contain duplicates")
        return value

    @field_validator("shots")
    @classmethod
    def _shots_are_valid(cls, value: int) -> int:
        if value < 0:
            raise ValueError("shots must be non-negative")
        if value > 5:
            raise ValueError(
                "the pinned validation split has at most five demonstrations per category"
            )
        return value

    @field_validator("limit_per_category")
    @classmethod
    def _limit_is_valid(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("limit_per_category must be positive")
        return value

    @model_validator(mode="after")
    def _balanced_limit(self) -> MMLUProConfig:
        if self.balanced and self.limit_per_category <= 0:
            raise ValueError("balanced tasksets require a positive category limit")
        return self


class MMLUProTaskset(vf.Taskset[MMLUProTask, MMLUProConfig]):
    """Load MMLU-Pro from two immutable Hub splits and produce stable tasks."""

    EXPECTED_ROWS: ClassVar[dict[str, int]] = {VALIDATION_SPLIT: 70, TEST_SPLIT: 12032}

    def _load_split(self, split: str) -> Dataset:
        loaded = load_dataset(
            self.config.dataset_repo,
            revision=self.config.dataset_revision,
            split=split,
        )
        if not isinstance(loaded, Dataset):
            raise TypeError(f"expected Dataset for split {split!r}, got {type(loaded).__name__}")
        missing = REQUIRED_COLUMNS - set(loaded.column_names)
        if missing:
            raise ValueError(f"MMLU-Pro split {split!r} is missing columns: {sorted(missing)}")
        if (
            self.config.dataset_repo == DATASET_REPO
            and self.config.dataset_revision == DATASET_REVISION
        ):
            expected = self.EXPECTED_ROWS[split]
            if len(loaded) != expected:
                raise ValueError(
                    f"expected {expected} rows in pinned {split} split, got {len(loaded)}"
                )
        return loaded

    def load(self) -> Iterable[MMLUProTask]:
        validation = self._load_split(self.config.validation_split)
        test = self._load_split(self.config.test_split)
        validation_rows = [dict(row) for row in validation]
        rows_by_category: dict[str, list[dict[str, Any]]] = {
            category: [] for category in self.config.categories
        }
        for row in test:
            normalized = dict(row)
            category = str(normalized["category"])
            if category in rows_by_category:
                rows_by_category[category].append(normalized)
        for category, rows in rows_by_category.items():
            rows.sort(
                key=lambda row: hashlib.sha256(
                    f"{self.config.order_seed}:{row['question_id']}".encode()
                ).hexdigest()
            )
            selected = rows[: self.config.limit_per_category] if self.config.balanced else rows
            for row in selected:
                prompt, demo_ids = build_prompt(validation_rows, row, shots=self.config.shots)
                answer = str(row["answer"]).upper()
                if answer not in CHOICES:
                    raise ValueError(
                        f"invalid answer label {answer!r} for row {row['question_id']}"
                    )
                data = MMLUProData(
                    idx=int(row["question_id"]),
                    name=f"mmlu-pro-{row['question_id']}",
                    prompt=prompt,
                    question_id=int(row["question_id"]),
                    category=category,
                    answer=answer,
                    answer_index=int(row["answer_index"]),
                    source_repo=self.config.dataset_repo,
                    source_revision=self.config.dataset_revision,
                    validation_demo_ids=demo_ids,
                    row_digest=_normalized_digest(row),
                )
                yield MMLUProTask(data, self.config.task)


__all__ = [
    "CATEGORIES",
    "DATASET_REPO",
    "DATASET_REVISION",
    "MMLUProConfig",
    "MMLUProData",
    "MMLUProTask",
    "MMLUProTaskset",
    "build_prompt",
    "extract_answer",
    "format_example",
]
