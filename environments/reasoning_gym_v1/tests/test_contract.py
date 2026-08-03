from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path

import verifiers.v1 as vf

from reasoning_gym_v1 import DEFAULT_GENERATORS, ReasoningGymConfig, ReasoningGymTaskset

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
