from __future__ import annotations

import asyncio
import hashlib
import json
import tomllib
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
        "?rev=cdd2ec7614131545df66484f9de11250daf16065#cdd2ec7614131545df66484f9de11250daf16065"
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


def test_reward_and_gold_validation_score_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        taskset_module,
        "load_dataset",
        lambda *args, **kwargs: [{"question": "What is 1+1?", "answer": "#### 2"}],
    )
    [task] = GSM8KTaskset(
        GSM8KConfig(dataset_repo="fixture/gsm8k", dataset_revision="a" * 40)
    ).load()
    trace = vf.Trace(
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type=type(task).__name__, data=task.data),
    )

    asyncio.run(task.score(trace, runtime=cast(vf.Runtime, object())))

    # An empty reply scores zero; the gold answer validates without any runtime work.
    reward = trace.rewards["correct"]
    assert reward is not None
    assert reward.score == 0.0
    assert reward.weight == 1.0
    assert asyncio.run(task.validate(cast(vf.Runtime, object())))


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("1 + 1 is two.\n#### 2", 1.0),
        ("#### 2.0", 1.0),
        ("First #### 3, corrected: #### 2", 1.0),
        ("#### 3", 0.0),
        ("<think>#### 2</think>So the answer is\n#### 5", 0.0),
        ("<think>still thinking #### 2", 0.0),
        ("2", 1.0),
        ("", 0.0),
    ],
)
def test_score_answer_uses_the_final_answer_after_reasoning(reply: str, expected: float) -> None:
    assert taskset_module.score_answer(reply, "2") == expected


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
