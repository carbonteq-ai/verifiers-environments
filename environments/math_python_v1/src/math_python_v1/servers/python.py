"""Bounded task-scoped Python MCP tool.

The evaluator never executes model code directly. Each call is replayed in a fresh
child interpreter, with only a minimal environment and bounded output returned to the
model. The Verifiers state channel keeps accepted cells isolated per rollout.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import textwrap

import verifiers.v1 as vf
from pydantic import Field


class PythonState(vf.State):
    cells: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PythonToolsetConfig(vf.ToolsetConfig):
    timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    max_cells: int = Field(default=8, ge=1, le=64)
    max_output_chars: int = Field(default=8_000, ge=256, le=100_000)


_CHILD_RUNNER = textwrap.dedent(
    """
    import ast
    import contextlib
    import io
    import json
    import sys

    cells = json.loads(sys.stdin.read())
    namespace = {"__name__": "__vf_math_python__"}
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        for source in cells:
            tree = ast.parse(source, mode="exec")
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                expression = tree.body[-1].value
                tree.body[-1] = ast.Assign(
                    targets=[ast.Name(id="__vf_last_value", ctx=ast.Store())],
                    value=expression,
                )
                ast.fix_missing_locations(tree)
            exec(compile(tree, "<model-cell>", "exec"), namespace, namespace)
            if "__vf_last_value" in namespace:
                print(repr(namespace.pop("__vf_last_value")))
    print(output.getvalue(), end="")
    """
).strip()


def _safe_environment() -> dict[str, str]:
    allowed = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "PYTHONHASHSEED"}
    return {key: value for key, value in os.environ.items() if key in allowed}


def _run_cells(cells: list[str], timeout_seconds: float) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-S", "-c", _CHILD_RUNNER],
            input=__import__("json").dumps(cells),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env=_safe_environment(),
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout_seconds:g}s"
    output = (completed.stdout + completed.stderr).strip()
    if completed.returncode:
        return False, output or f"child exited with status {completed.returncode}"
    return True, output


class PythonToolset(vf.Toolset[PythonToolsetConfig, PythonState]):
    TOOL_PREFIX = None

    @vf.tool
    async def python(self, code: str) -> str:
        """Execute one Python cell and return stdout, the last expression, or an error."""

        if not code.strip():
            return "error: code cell is empty"
        if len(code) > 50_000:
            return "error: code cell exceeds 50000 characters"
        if len(self.state.cells) >= self.config.max_cells:
            return f"error: maximum of {self.config.max_cells} cells reached"

        cells = [*self.state.cells, code]
        ok, output = await asyncio.to_thread(_run_cells, cells, self.config.timeout_seconds)
        if not ok:
            self.state.errors.append(output)
            return f"error: {output}"[: self.config.max_output_chars]
        self.state.cells.append(code)
        return output[: self.config.max_output_chars]


__all__ = ["PythonState", "PythonToolset", "PythonToolsetConfig"]
