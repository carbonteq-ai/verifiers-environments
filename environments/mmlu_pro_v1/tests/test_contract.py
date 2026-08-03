from __future__ import annotations

import asyncio
import os
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import verifiers.v1 as vf

from mmlu_pro_v1 import (
    DATASET_REVISION,
    MMLUProConfig,
    MMLUProData,
    MMLUProTask,
    MMLUProTaskset,
    build_prompt,
    extract_answer,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_distribution_metadata_is_standalone_and_pinned() -> None:
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((PACKAGE_ROOT / "uv.lock").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "mmlu-pro-v1"
    assert pyproject["project"]["requires-python"] == ">=3.12,<3.14"
    assert "datasets>=4,<5" in pyproject["project"]["dependencies"]
    assert not any("posttrain" in item for item in pyproject["project"]["dependencies"])
    verifiers = next(package for package in lock["package"] if package["name"] == "verifiers")
    assert verifiers["source"]["git"].endswith(
        "?rev=284a868d6a9022109b749710672a0460e8a996d4#284a868d6a9022109b749710672a0460e8a996d4"
    )


def test_parser_matches_ordered_reference_patterns_and_strict_zero() -> None:
    assert extract_answer("Reasoning. The answer is (C).") == "C"
    assert extract_answer("Answer: H") == "H"
    assert extract_answer("The only remaining choice is J") == "J"
    assert extract_answer("No valid response was produced") is None

    data = MMLUProData(
        idx=7,
        name="synthetic",
        prompt="Question",
        question_id=7,
        category="math",
        answer="C",
        answer_index=2,
        source_repo="synthetic",
        source_revision=DATASET_REVISION,
        validation_demo_ids=(1, 2, 3, 4, 5),
        row_digest="0" * 64,
    )
    task = MMLUProTask(data)
    assert (
        asyncio.run(
            task.answer_correct(cast(vf.Trace, SimpleNamespace(last_reply="The answer is (C).")))
        )
        == 1.0
    )
    assert (
        asyncio.run(task.answer_correct(cast(vf.Trace, SimpleNamespace(last_reply="No answer."))))
        == 0.0
    )


def test_prompt_removes_only_literal_na_and_keeps_demo_ids() -> None:
    validation = [
        {
            "question_id": 1,
            "question": "Demo?",
            "options": ["one", "N/A", "three"],
            "answer": "A",
            "answer_index": 0,
            "cot_content": "A: Let's think step by step. demo",
            "category": "math",
        },
    ]
    prompt, demo_ids = build_prompt(
        validation,
        {
            "question_id": 9,
            "question": "Target?",
            "options": ["x", "y"],
            "answer": "B",
            "answer_index": 1,
            "cot_content": "",
            "category": "math",
        },
        shots=1,
    )
    assert demo_ids == (1,)
    assert "A. one" in prompt and "B. three" in prompt
    assert "N/A" not in prompt
    assert prompt.endswith("Answer: Let's think step by step.")


def test_declarative_env_config_resolves_without_loading_network_data() -> None:
    config = vf.EnvConfig.model_validate(
        {
            "taskset": {"id": "mmlu-pro-v1"},
            "harness": {"id": "null", "runtime": {"type": "subprocess"}},
        }
    )
    environment = vf.Environment(config)
    assert isinstance(environment.taskset, MMLUProTaskset)
    assert isinstance(environment.taskset.config, MMLUProConfig)


@pytest.mark.network
def test_pinned_hub_splits_have_reference_row_counts() -> None:
    if os.environ.get("RUN_ENVIRONMENT_NETWORK_TESTS") != "1":
        pytest.skip("set RUN_ENVIRONMENT_NETWORK_TESTS=1 for the pinned Hub gate")
    taskset = MMLUProTaskset(MMLUProConfig())
    tasks = taskset.select(1)
    assert len(tasks) == 1
    assert len(list(taskset._load_split("validation"))) == 70
    assert len(list(taskset._load_split("test"))) == 12032
