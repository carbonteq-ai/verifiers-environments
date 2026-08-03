from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path

import verifiers.v1 as vf

from automationbench_v1.taskset import AutomationBenchConfig, AutomationBenchTaskset
from automationbench_v1.tools import AutomationBenchState

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_distribution_metadata_is_standalone_and_pinned() -> None:
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((PACKAGE_ROOT / "uv.lock").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "automationbench-v1"
    assert pyproject["project"]["requires-python"] == ">=3.12,<3.14"
    assert not any("posttrain" in item for item in pyproject["project"]["dependencies"])
    assert not any(
        "carbonteq-automation-bench" in item for item in pyproject["project"]["dependencies"]
    )
    assert (PACKAGE_ROOT / "src/automationbench/schema/world.py").is_file()
    assert (PACKAGE_ROOT / "src/automationbench/tools/zapier/meta.py").is_file()
    assert not any(package["name"] == "carbonteq-automation-bench" for package in lock["package"])
    verifiers = next(package for package in lock["package"] if package["name"] == "verifiers")
    assert verifiers["source"]["git"].endswith(
        "?rev=284a868d6a9022109b749710672a0460e8a996d4#284a868d6a9022109b749710672a0460e8a996d4"
    )


def test_declarative_env_config_discovers_loads_and_scores_real_task() -> None:
    config = vf.EnvConfig.model_validate(
        {
            "taskset": {"id": "automationbench-v1", "domains": ["simple"]},
            "harness": {"id": "null", "runtime": {"type": "subprocess"}},
        }
    )
    environment = vf.Environment(config)
    assert isinstance(environment.taskset, AutomationBenchTaskset)
    assert isinstance(environment.taskset.config, AutomationBenchConfig)

    [task] = environment.taskset.select(1)
    assert task.data.name == "simple.email_sf_contact_phone_update"

    trace = vf.Trace(
        task=vf.TraceTask(type=type(task).__name__, data=task.data),
        state=AutomationBenchState(),
    )
    asyncio.run(task.setup(trace, None))  # type: ignore[arg-type]
    asyncio.run(task.score(trace))
    assert trace.rewards == {"partial_credit": 0.0}
    assert trace.metrics["task_completed_correctly"] == 0.0
