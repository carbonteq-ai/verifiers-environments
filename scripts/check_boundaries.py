"""Validate that every environment remains an independently installable package."""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = ROOT / "environments"
VERIFIERS_REVISION = "284a868d6a9022109b749710672a0460e8a996d4"
PACKAGES = {
    "gsm8k_v1": "gsm8k-v1",
    "automationbench_v1": "automationbench-v1",
    "mmlu_pro_v1": "mmlu-pro-v1",
    "ifeval_v1": "ifeval-v1",
    "reasoning_gym_v1": "reasoning-gym-v1",
    "math_python_v1": "math-python-v1",
}
FORBIDDEN_ROOTS = {
    "posttrain",
    "posttrain_lab",
    "trackio",
    "wandb",
    "trl",
    "vllm",
    "dstack",
}
SIBLING_MODULES = frozenset(PACKAGES)


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.partition(".")[0])
    return roots


def validate_package(module: str, distribution: str) -> list[str]:
    package_root = ENVIRONMENTS / module
    failures: list[str] = []
    pyproject_path = package_root / "pyproject.toml"
    lock_path = package_root / "uv.lock"
    source_root = package_root / "src" / module

    for required in (
        pyproject_path,
        lock_path,
        package_root / "README.md",
        source_root / "__init__.py",
    ):
        if not required.is_file():
            failures.append(f"{package_root.relative_to(ROOT)}: missing {required.name}")

    if not pyproject_path.is_file():
        return failures

    project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]
    if project["name"] != distribution:
        failures.append(f"{module}: distribution is {project['name']!r}, expected {distribution!r}")
    if project["requires-python"] != ">=3.12,<3.14":
        failures.append(f"{module}: requires-python must be >=3.12,<3.14")

    dependencies = tuple(project.get("dependencies", ()))
    expected = (
        "verifiers @ git+https://github.com/PrimeIntellect-ai/verifiers.git@" + VERIFIERS_REVISION
    )
    if expected not in dependencies:
        failures.append(f"{module}: must depend on exact pinned Verifiers")
    forbidden_dependency_fragments = (
        "posttrain",
        "trackio",
        "wandb",
        "trl",
        "vllm",
        "dstack",
    )
    if any(
        any(fragment in item.lower() for fragment in forbidden_dependency_fragments)
        for item in dependencies
    ):
        failures.append(f"{module}: framework and tracking dependencies are forbidden")
    if any("file:" in item or " ../" in item or " @ ../" in item for item in dependencies):
        failures.append(f"{module}: local-path dependencies are forbidden")

    for source in sorted(source_root.rglob("*.py")):
        roots = imported_roots(source)
        blocked = sorted(roots & (FORBIDDEN_ROOTS | (SIBLING_MODULES - {module})))
        if blocked:
            failures.append(
                f"{source.relative_to(ROOT)} imports forbidden package roots: {', '.join(blocked)}"
            )
    return failures


def main() -> int:
    failures: list[str] = []
    if (ROOT / "pyproject.toml").exists() or (ROOT / "uv.lock").exists():
        failures.append("repository root must not be a uv workspace or runtime package")
    actual = {path.name for path in ENVIRONMENTS.iterdir() if path.is_dir()}
    if actual != set(PACKAGES):
        failures.append(
            "environment directories differ: "
            f"actual={sorted(actual)!r}, expected={sorted(PACKAGES)!r}"
        )
    for module, distribution in PACKAGES.items():
        failures.extend(validate_package(module, distribution))
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1
    print("validated six independent Verifiers environment package boundaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
