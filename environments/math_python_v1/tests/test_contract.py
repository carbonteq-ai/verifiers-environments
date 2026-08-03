from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path

import pytest
import verifiers.v1 as vf

from math_python_v1 import MathPythonConfig, MathPythonTaskset, PythonToolset, PythonToolsetConfig
from math_python_v1.servers.python import _run_cells

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_distribution_metadata_is_standalone_and_pinned() -> None:
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((PACKAGE_ROOT / "uv.lock").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "math-python-v1"
    assert pyproject["project"]["requires-python"] == ">=3.12,<3.14"
    assert not any("posttrain" in item for item in pyproject["project"]["dependencies"])
    verifiers = next(package for package in lock["package"] if package["name"] == "verifiers")
    assert verifiers["source"]["git"].endswith(
        "?rev=284a868d6a9022109b749710672a0460e8a996d4#284a868d6a9022109b749710672a0460e8a996d4"
    )


def test_boxed_math_verification_and_task_scoped_toolset(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "problem": "Compute 2+2.",
            "solution": "The answer is $\\boxed{4}$.",
            "level": "Level 1",
            "type": "Algebra",
        }
    ]
    monkeypatch.setattr("math_python_v1.taskset.load_dataset", lambda *args, **kwargs: rows)
    config = vf.EnvConfig.model_validate(
        {
            "taskset": {"id": "math-python-v1", "num_tasks": 1},
            "harness": {"id": "null", "runtime": {"type": "subprocess"}},
        }
    )
    environment = vf.Environment(config)
    assert isinstance(environment.taskset, MathPythonTaskset)
    assert isinstance(environment.taskset.config, MathPythonConfig)

    [task] = environment.taskset.select(1)
    assert task.data.answer == "4"
    assert task.data.source_revision == "0530c78699ea5e8eb5530600900e1f328b48acad"
    assert task.tools == (PythonToolset,)
    [tool_server] = task.tool_servers()
    assert isinstance(tool_server, PythonToolset)

    trace = vf.Trace(task=vf.TraceTask(type=type(task).__name__, data=task.data))
    trace.nodes = [
        vf.MessageNode(
            parent=None,
            message=vf.AssistantMessage(content="\\boxed{4}"),
            sampled=True,
        )
    ]
    asyncio.run(task.score(trace))
    assert trace.rewards["math_reward"] == 1.0
    assert trace.metrics["parse_success"] == 1.0
    assert trace.metrics["symbolic_correctness"] == 1.0


def test_python_tool_replays_cells_and_isolates_state() -> None:
    tool = PythonToolset(PythonToolsetConfig())
    assert asyncio.run(tool.python("value = 2")) == ""
    assert asyncio.run(tool.python("value + 2")) == "4"
    assert tool.state.cells == ["value = 2", "value + 2"]
    isolated = PythonToolset(PythonToolsetConfig())
    assert asyncio.run(isolated.python("value")).startswith("error:")


def test_python_tool_error_does_not_commit_state() -> None:
    tool = PythonToolset(PythonToolsetConfig())

    assert asyncio.run(tool.python("raise ValueError('bad cell')")).startswith("error:")
    assert tool.state.cells == []
    assert len(tool.state.errors) == 1


def test_python_child_timeout_is_bounded() -> None:
    ok, output = _run_cells(["while True: pass"], timeout_seconds=0.05)

    assert not ok
    assert output == "timed out after 0.05s"


def test_python_child_exit_is_reported_without_leaking_state() -> None:
    ok, output = _run_cells(["__import__('os')._exit(17)"], timeout_seconds=1)

    assert not ok
    assert output == "child exited with status 17"


def test_python_child_receives_only_safe_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATH_PYTHON_TEST_SECRET", "must-not-cross-boundary")

    ok, output = _run_cells(
        ["print(__import__('os').environ.get('MATH_PYTHON_TEST_SECRET', 'absent'))"],
        timeout_seconds=1,
    )

    assert ok
    assert output == "absent\nNone"


def test_balanced_order_is_deterministic_and_type_round_robin(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {"problem": f"p{idx}", "solution": f"\\boxed{{{idx}}}", "level": "1", "type": kind}
        for idx, kind in enumerate(("Algebra", "Geometry", "Algebra", "Geometry"))
    ]
    monkeypatch.setattr("math_python_v1.taskset.load_dataset", lambda *args, **kwargs: rows)
    first = list(
        MathPythonTaskset(
            MathPythonConfig(num_tasks=4, balance_by_type=True, order_seed=19),
        ).load()
    )
    second = list(
        MathPythonTaskset(
            MathPythonConfig(num_tasks=4, balance_by_type=True, order_seed=19),
        ).load()
    )
    assert [task.data.idx for task in first] == [task.data.idx for task in second]
    assert [task.data.problem_type for task in first] == ["Algebra", "Geometry", "Algebra", "Geometry"]
    assert (PACKAGE_ROOT / "images" / "math-python" / "Containerfile").is_file()
