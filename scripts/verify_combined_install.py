"""Activate every installed taskset through the Verifiers v1 loader.

This check intentionally does not materialize tasks or score a row. Several real
packages load immutable Hub data at task selection time and GSM8K/Math Python
scoring may require a runtime. Network/data qualification belongs to package
tests and later release gates; the combined install gate proves import and
declarative loader compatibility without those external services.
"""

from __future__ import annotations

import verifiers.v1 as vf

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
        config = vf.EnvConfig.model_validate(
            {
                "taskset": {"id": taskset_id},
                "harness": {"id": "null", "runtime": {"type": "subprocess"}},
            }
        )
        environment = vf.Environment(config)
        print(f"activated {taskset_id}: {type(environment.taskset).__name__}")


if __name__ == "__main__":
    main()
