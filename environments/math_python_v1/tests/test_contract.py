from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest
import verifiers.v1 as vf
from verifiers.v1.state import state_cls
from verifiers.v1.utils.loaders import load_environment, resolve_env_config

from math_python_v1 import (
    MathPythonConfig,
    MathPythonTaskset,
    PythonState,
    PythonToolset,
    PythonToolsetConfig,
)
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
        "?rev=b2e4e8157783b2c0dffc7821044c87f29f1c3ccf#b2e4e8157783b2c0dffc7821044c87f29f1c3ccf"
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
    config = resolve_env_config(
        {
            "taskset": {"id": "math-python-v1", "num_tasks": 1},
            "agent": {"harness": {"id": "null"}, "runtime": {"type": "subprocess"}},
        }
    )
    environment = load_environment(config)
    assert isinstance(environment.taskset, MathPythonTaskset)
    assert isinstance(environment.taskset.config, MathPythonConfig)

    [task] = list(environment.taskset.load())
    assert task.data.answer == "4"
    assert task.data.system_prompt is not None
    assert "\\boxed{...}" in task.data.system_prompt
    assert "under 2,000 words" in task.data.system_prompt
    assert "verify it at most once" in task.data.system_prompt
    assert "Never repeat" in task.data.system_prompt
    assert task.data.source_revision == "0530c78699ea5e8eb5530600900e1f328b48acad"
    assert task.tools == (PythonToolset,)
    assert state_cls(type(task)) is PythonState
    [tool_server] = task.toolsets(task.config)
    assert isinstance(tool_server, PythonToolset)

    trace = vf.Trace(
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type=type(task).__name__, data=task.data),
    )
    trace.nodes = [
        vf.MessageNode(
            parent=None,
            message=vf.AssistantMessage(content="\\boxed{4}"),
            sampled=True,
        )
    ]
    asyncio.run(task.score(trace))
    assert trace.reward == 1.0
    reward = trace.rewards["math_reward"]
    assert reward is not None
    assert reward.score == 1.0
    assert reward.weight == 1.0
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


def test_python_tool_server_module_reports_its_port(tmp_path: Path) -> None:
    port_file = tmp_path / "mcp-port"
    env = {
        **os.environ,
        "MCP_PORT_FILE": str(port_file),
        "VF_CONFIG": PythonToolsetConfig().model_dump_json(),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "math_python_v1.servers.python"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not port_file.is_file() and process.poll() is None:
            time.sleep(0.05)
        assert process.poll() is None, process.stderr.read() if process.stderr is not None else ""
        assert port_file.read_text(encoding="utf-8").strip().isdigit()
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_balanced_order_is_deterministic_and_type_round_robin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    assert [task.data.problem_type for task in first] == [
        "Algebra",
        "Geometry",
        "Algebra",
        "Geometry",
    ]
    assert (PACKAGE_ROOT / "images" / "math-python" / "Containerfile").is_file()


def test_level_and_type_filters_apply_before_balanced_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "problem": f"p{idx}",
            "solution": f"\\boxed{{{idx}}}",
            "level": level,
            "type": kind,
        }
        for idx, (level, kind) in enumerate(
            (
                ("Level 1", "Algebra"),
                ("Level 2", "Algebra"),
                ("Level 3", "Geometry"),
                ("Level 4", "Algebra"),
                ("Level 5", "Geometry"),
            )
        )
    ]
    monkeypatch.setattr("math_python_v1.taskset.load_dataset", lambda *args, **kwargs: rows)

    tasks = list(
        MathPythonTaskset(
            MathPythonConfig(
                num_tasks=3,
                levels=("Level 2", "Level 3", "Level 4"),
                problem_types=("Algebra", "Geometry"),
                balance_by_type=True,
                order_seed=7,
            )
        ).load()
    )

    assert {task.data.level for task in tasks} == {"Level 2", "Level 3", "Level 4"}
    assert [task.data.problem_type for task in tasks] == ["Algebra", "Geometry", "Algebra"]
    assert {task.data.idx for task in tasks} == {1, 2, 3}


def test_selection_excludes_rows_without_a_boxed_ground_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "problem": "invalid",
            "solution": "no terminal answer",
            "level": "Level 2",
            "type": "Algebra",
        },
        {"problem": "valid", "solution": "\\boxed{2}", "level": "Level 2", "type": "Algebra"},
    ]
    monkeypatch.setattr("math_python_v1.taskset.load_dataset", lambda *args, **kwargs: rows)

    [task] = list(
        MathPythonTaskset(
            MathPythonConfig(num_tasks=1, levels=("Level 2",)),
        ).load()
    )

    assert task.data.idx == 1
    assert task.data.answer == "2"
