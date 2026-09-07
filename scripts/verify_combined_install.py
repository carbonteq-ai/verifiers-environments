"""Activate every installed taskset through the Verifiers v1 loader.

This check intentionally does not materialize tasks or score a row. Several real
packages load immutable Hub data at task selection time and GSM8K/Math Python
scoring may require a runtime. Network/data qualification belongs to package
tests and later release gates; the combined install gate proves import and
declarative loader compatibility without those external services.
"""

from __future__ import annotations

from verifiers.v1.utils.loaders import load_environment, resolve_env_config

TASKSET_IDS = (
    "automationbench-v1",
    "gsm8k-v1",
    "ifeval-v1",
    "math-python-v1",
    "mmlu-pro-v1",
    "reasoning-gym-v1",
)


def main() -> None:
    for taskset_id in TASKSET_IDS:
        config = resolve_env_config(
            {
                "taskset": {"id": taskset_id},
                "agent": {
                    "harness": {"id": "null"},
                    "runtime": {"type": "subprocess"},
                },
            }
        )
        environment = load_environment(config)
        print(f"activated {taskset_id}: {type(environment.taskset).__name__}")


if __name__ == "__main__":
    main()
