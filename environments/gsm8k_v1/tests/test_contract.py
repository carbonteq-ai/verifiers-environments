from __future__ import annotations

import asyncio
import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import pytest
import verifiers.v1 as vf

import gsm8k_v1.taskset as taskset_module
from gsm8k_v1 import (
    DEFAULT_DATASET_REVISION,
    GSM8KConfig,
    GSM8KTaskset,
    normalized_row_digest,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_distribution_metadata_is_standalone_and_pinned() -> None:
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((PACKAGE_ROOT / "uv.lock").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "gsm8k-v1"
    assert pyproject["project"]["requires-python"] == ">=3.12,<3.14"
    assert "datasets>=4,<5" in pyproject["project"]["dependencies"]
    assert not any("posttrain" in item for item in pyproject["project"]["dependencies"])
    verifiers = next(package for package in lock["package"] if package["name"] == "verifiers")
    assert verifiers["source"]["git"].endswith(
        "?rev=284a868d6a9022109b749710672a0460e8a996d4#284a868d6a9022109b749710672a0460e8a996d4"
    )


def test_config_requires_an_immutable_lowercase_revision() -> None:
    assert GSM8KConfig().dataset_revision == DEFAULT_DATASET_REVISION
    for revision in ("main", "a" * 39, "A" * 40):
        with pytest.raises(ValueError, match="full 40-character"):
            GSM8KConfig(dataset_revision=revision)


def test_taskset_passes_source_identity_and_row_digest_to_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "question": "How many apples?",
            "answer": "Two apples.\n#### 2",
            "extra": "preserve me",
        }
    ]
    captured: dict[str, Any] = {}

    def fake_load_dataset(*args: Any, **kwargs: Any) -> list[dict[str, str]]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return rows

    monkeypatch.setattr(taskset_module, "load_dataset", fake_load_dataset)
    revision = "a" * 40
    config = GSM8KConfig(
        id="gsm8k-v1",
        dataset_repo="fixture/gsm8k",
        dataset_revision=revision,
        dataset_config="main",
        split="train",
    )

    [task] = GSM8KTaskset(config).load()

    assert captured == {
        "args": ("fixture/gsm8k", "main"),
        "kwargs": {"split": "train", "revision": revision},
    }
    assert task.data.idx == 0
    assert (
        task.data.prompt
        == """Solve the grade-school math problem. Reason step by step, then give the final answer as a single number on the last line, prefixed with '#### ' (e.g. '#### 42').

How many apples?"""
    )
    assert task.data.answer == "2"
    assert task.data.dataset_repo == "fixture/gsm8k"
    assert task.data.dataset_revision == revision
    assert task.data.dataset_config == "main"
    assert task.data.split == "train"
    assert task.data.row_digest == normalized_row_digest(rows[0])

    canonical = json.dumps(rows[0], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert task.data.row_digest == hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class FakeProgramResult:
    exit_code: int
    stdout: str
    stderr: str = ""


class FakeRuntime:
    def __init__(self, stdout: str = "1.0\n") -> None:
        self.stdout = stdout
        self.calls: list[tuple[bytes, list[str]]] = []

    async def run_uv_script(self, script: bytes, args: list[str]) -> FakeProgramResult:
        self.calls.append((script, args))
        return FakeProgramResult(exit_code=0, stdout=self.stdout)


def test_reward_and_gold_validation_use_runtime_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        taskset_module,
        "load_dataset",
        lambda *args, **kwargs: [{"question": "What is 1+1?", "answer": "#### 2"}],
    )
    [task] = GSM8KTaskset(
        GSM8KConfig(dataset_repo="fixture/gsm8k", dataset_revision="a" * 40)
    ).load()
    trace = vf.Trace(task=vf.TraceTask(type=type(task).__name__, data=task.data))
    runtime = FakeRuntime()

    asyncio.run(task.score(trace, runtime=cast(vf.Runtime, runtime)))

    assert trace.rewards == {"correct": 1.0}
    assert asyncio.run(task.validate(cast(vf.Runtime, runtime)))
    assert len(runtime.calls) == 2
    assert runtime.calls[0][1] == ["2", ""]
    assert runtime.calls[1][1] == ["2", "#### 2"]


@pytest.mark.network
def test_default_dataset_loads_from_exact_revision() -> None:
    splits: tuple[tuple[Literal["train", "test"], int], ...] = (
        ("test", 1_319),
        ("train", 7_473),
    )
    for split, expected_count in splits:
        tasks = GSM8KTaskset(GSM8KConfig(split=split)).load()
        assert len(tasks) == expected_count
        assert tasks[0].data.dataset_repo == "openai/gsm8k"
        assert tasks[0].data.dataset_revision == DEFAULT_DATASET_REVISION
        assert tasks[0].data.dataset_config == "main"
        assert tasks[0].data.split == split
        assert len(tasks[0].data.row_digest) == 64
