from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import verifiers.v1 as vf

from reasoning_gym_v1 import (
    COLDSTART_CANDIDATE_GENERATORS,
    DEFAULT_GENERATORS,
    REASONING_GYM_BOXED_SYSTEM_PROMPT,
    REASONING_GYM_SYSTEM_PROMPT,
    ReasoningGymConfig,
    ReasoningGymTaskset,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_distribution_metadata_is_standalone_and_pinned() -> None:
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((PACKAGE_ROOT / "uv.lock").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "reasoning-gym-v1"
    assert pyproject["project"]["requires-python"] == ">=3.12,<3.14"
    assert not any("posttrain" in item for item in pyproject["project"]["dependencies"])
    assert not any(
        item.startswith("reasoning-gym @ ") for item in pyproject["project"]["dependencies"]
    )
    assert (PACKAGE_ROOT / "src/reasoning_gym/factory.py").is_file()
    verifiers = next(package for package in lock["package"] if package["name"] == "verifiers")
    assert verifiers["source"]["git"].endswith(
        "?rev=284a868d6a9022109b749710672a0460e8a996d4#284a868d6a9022109b749710672a0460e8a996d4"
    )


def test_declarative_env_config_discovers_balanced_tasks_and_native_scores() -> None:
    config = vf.EnvConfig.model_validate(
        {
            "taskset": {
                "id": "reasoning-gym-v1",
                "split": "eval",
                "examples_per_generator": 1,
            },
            "harness": {"id": "null", "runtime": {"type": "subprocess"}},
        }
    )
    environment = vf.Environment(config)
    assert isinstance(environment.taskset, ReasoningGymTaskset)
    assert isinstance(environment.taskset.config, ReasoningGymConfig)

    tasks = environment.taskset.select(len(DEFAULT_GENERATORS))
    assert [task.data.generator for task in tasks] == list(DEFAULT_GENERATORS)
    assert all(
        task.data.source_commit == "49b07130b3fcd12f2d064bba7c43869543a0e7e7" for task in tasks
    )
    assert len({task.data.row_digest for task in tasks}) == len(tasks)
    assert all(task.data.system_prompt == REASONING_GYM_SYSTEM_PROMPT for task in tasks)
    assert "verify it at most once" in REASONING_GYM_SYSTEM_PROMPT
    assert "Never repeat" in REASONING_GYM_SYSTEM_PROMPT

    task = tasks[0]
    trace = vf.Trace(task=vf.TraceTask(type=type(task).__name__, data=task.data))
    asyncio.run(task.score(trace))
    assert trace.rewards["native_reward"] == 0.0
    assert trace.metrics["native_score"] == 0.0


def test_train_and_eval_seed_namespaces_are_disjoint() -> None:
    train = ReasoningGymConfig(split="train", examples_per_generator=1)
    evaluation = ReasoningGymConfig(split="eval", examples_per_generator=1)
    assert train.seed_start == 0
    assert evaluation.seed_start == 1_000_000


def test_structured_answer_task_uses_native_scorer_without_text_oracle() -> None:
    taskset = ReasoningGymTaskset(
        ReasoningGymConfig(split="train", generators=("graph_color",), examples_per_generator=1)
    )
    task = taskset.select(1)[0]
    valid_answer = json.dumps(task.data.metadata["possible_answer"])

    valid_trace = cast(vf.Trace, SimpleNamespace(last_reply=valid_answer))
    invalid_trace = cast(vf.Trace, SimpleNamespace(last_reply="not-json"))

    assert asyncio.run(task.native_score(valid_trace)) == 1.0
    assert asyncio.run(task.native_reward(valid_trace)) == 1.0
    assert asyncio.run(task.native_score(invalid_trace)) == 0.0


def test_syllogism_scores_only_the_terminal_yes_no_decision() -> None:
    taskset = ReasoningGymTaskset(
        ReasoningGymConfig(split="train", generators=("syllogism",), examples_per_generator=1)
    )
    task = taskset.select(1)[0]
    expected = task.data.answer
    assert expected in {"Yes", "No"}
    incorrect = "No" if expected == "Yes" else "Yes"

    correct = cast(
        vf.Trace, SimpleNamespace(last_reply=f"A concise derivation. Answer: {expected}")
    )
    boxed = cast(
        vf.Trace, SimpleNamespace(last_reply=f"A concise derivation. \\boxed{{{expected}}}")
    )
    contradictory = cast(vf.Trace, SimpleNamespace(last_reply=f"{expected} {incorrect}"))
    no_decision = cast(vf.Trace, SimpleNamespace(last_reply="The possibilities are Yes and No"))

    assert asyncio.run(task.native_reward(correct)) == 1.0
    assert asyncio.run(task.native_reward(boxed)) == 1.0
    assert asyncio.run(task.native_reward(contradictory)) == 0.0
    assert asyncio.run(task.native_reward(no_decision)) == 0.0


def test_boxed_exact_mode_requires_one_exact_final_answer() -> None:
    taskset = ReasoningGymTaskset(
        ReasoningGymConfig(
            split="train",
            generators=("chain_sum",),
            examples_per_generator=1,
            reward_mode="boxed_exact",
        )
    )
    task = taskset.select(1)[0]
    expected = task.data.answer
    assert isinstance(expected, str)
    assert "chain_sum" in COLDSTART_CANDIDATE_GENERATORS
    assert task.data.system_prompt == REASONING_GYM_BOXED_SYSTEM_PROMPT

    boxed = cast(vf.Trace, SimpleNamespace(last_reply=f"Brief derivation. \\boxed{{{expected}}}"))
    unboxed = cast(vf.Trace, SimpleNamespace(last_reply=expected))
    wrong = cast(vf.Trace, SimpleNamespace(last_reply="\\boxed{not-the-answer}"))

    assert asyncio.run(task.native_reward(boxed)) == 1.0
    assert asyncio.run(task.native_reward(unboxed)) == 0.0
    assert asyncio.run(task.native_reward(wrong)) == 0.0


def test_coldstart_candidate_bank_is_deterministic_and_boxed() -> None:
    config = ReasoningGymConfig(
        split="train",
        generators=COLDSTART_CANDIDATE_GENERATORS,
        examples_per_generator=1,
        reward_mode="boxed_exact",
    )
    tasks = ReasoningGymTaskset(config).select(len(COLDSTART_CANDIDATE_GENERATORS))

    assert tuple(task.data.generator for task in tasks) == COLDSTART_CANDIDATE_GENERATORS
    assert len({task.data.row_digest for task in tasks}) == len(tasks)
    assert all(task.data.system_prompt == REASONING_GYM_BOXED_SYSTEM_PROMPT for task in tasks)
