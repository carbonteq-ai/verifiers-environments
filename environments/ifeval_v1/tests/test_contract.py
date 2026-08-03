from __future__ import annotations

import asyncio
import os
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import verifiers.v1 as vf

from ifeval_v1 import (
    CHECKERS,
    DATASET_REVISION,
    SUPPORTED_INSTRUCTION_IDS,
    IFEvalConfig,
    IFEvalData,
    IFEvalTask,
    IFEvalTaskset,
    check_instruction,
    loose_responses,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_distribution_metadata_is_standalone_and_pinned() -> None:
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((PACKAGE_ROOT / "uv.lock").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "ifeval-v1"
    assert pyproject["project"]["requires-python"] == ">=3.12,<3.14"
    assert "datasets>=4,<5" in pyproject["project"]["dependencies"]
    assert "langdetect>=1.0.9,<2" in pyproject["project"]["dependencies"]
    assert not any("posttrain" in item for item in pyproject["project"]["dependencies"])
    verifiers = next(package for package in lock["package"] if package["name"] == "verifiers")
    assert verifiers["source"]["git"].endswith(
        "?rev=284a868d6a9022109b749710672a0460e8a996d4#284a868d6a9022109b749710672a0460e8a996d4"
    )


def test_registry_covers_all_pinned_source_instruction_ids() -> None:
    assert set(CHECKERS) == set(SUPPORTED_INSTRUCTION_IDS)
    assert check_instruction(
        "keywords:existence", "The answer has a token.", {"keywords": ["token"]}
    )
    assert not check_instruction("punctuation:no_comma", "No, comma", {})
    assert check_instruction("detectable_format:json_format", '{"ok": true}', {})
    assert not check_instruction("detectable_format:json_format", "not json", {})
    assert check_instruction("startend:quotation", '"quoted"', {})
    assert not check_instruction("startend:quotation", "unquoted", {})


def test_strict_and_loose_metrics_are_named_and_deterministic() -> None:
    data = IFEvalData(
        idx=1,
        name="synthetic",
        prompt="Reply with token",
        key=1,
        instruction_id_list=("keywords:existence", "punctuation:no_comma"),
        instruction_kwargs=(
            {"keywords": ["token"]},
            {},
        ),
        source_repo="synthetic",
        source_revision=DATASET_REVISION,
        source_split="train",
        logical_purpose="evaluation",
        row_digest="0" * 64,
    )
    task = IFEvalTask(data)
    trace = cast(vf.Trace, SimpleNamespace(last_reply="token"))
    assert asyncio.run(task.strict_prompt_accuracy(trace)) == 1.0
    assert asyncio.run(task.strict_instruction_accuracy(trace)) == 1.0
    assert asyncio.run(task.loose_prompt_accuracy(trace)) == 1.0
    assert asyncio.run(task.loose_instruction_accuracy(trace)) == 1.0
    assert loose_responses("a\nb") == ("a\nb", "a\nb", "b", "a", "", "b", "a", "")


def test_declarative_env_config_resolves_without_loading_network_data() -> None:
    config = vf.EnvConfig.model_validate(
        {
            "taskset": {"id": "ifeval-v1"},
            "harness": {"id": "null", "runtime": {"type": "subprocess"}},
        }
    )
    environment = vf.Environment(config)
    assert isinstance(environment.taskset, IFEvalTaskset)
    assert isinstance(environment.taskset.config, IFEvalConfig)
    assert environment.taskset.config.logical_purpose == "evaluation"


def test_config_rejects_training_split() -> None:
    with pytest.raises(ValueError, match="physical split 'train'"):
        IFEvalConfig(split="test")


@pytest.mark.network
def test_pinned_hub_split_has_541_unique_rows_and_all_checkers() -> None:
    if os.environ.get("RUN_ENVIRONMENT_NETWORK_TESTS") != "1":
        pytest.skip("set RUN_ENVIRONMENT_NETWORK_TESTS=1 for the pinned Hub gate")
    tasks = IFEvalTaskset(IFEvalConfig()).select()
    assert len(tasks) == 541
    assert len({task.data.key for task in tasks}) == 541
    assert {instruction for task in tasks for instruction in task.data.instruction_id_list} == set(
        CHECKERS
    )
