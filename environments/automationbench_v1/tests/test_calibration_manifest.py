import pytest
from pydantic import ValidationError

from automationbench_v1.calibration.inventory import freeze_inventory
from automationbench_v1.calibration.models import (
    CalibrationManifest,
    CollectionLimits,
    TaskSelection,
    plan_collection,
)
from automationbench_v1.taskset import AutomationBenchConfig


def test_collection_plan_is_bound_to_actual_tasks_and_limits() -> None:
    inventory = freeze_inventory(AutomationBenchConfig(), source_identity={"fixture": "candidate"})
    task = inventory.tasks[0]
    manifest = plan_collection(
        inventory,
        selections=(
            TaskSelection(
                task_name=task.task_name,
                task_digest=task.digest,
                family="email-update",
                split="development",
            ),
        ),
        route_identity="fixture-only",
        native_config={"harness": "codex"},
        scorer_revision="fixture-only",
        limits=CollectionLimits(
            max_concurrent=1,
            max_total_attempts=2,
            max_elapsed_seconds=60,
            attempt_timeout_seconds=20,
            max_turns=4,
            max_output_tokens=100,
            cost_measurement="unavailable",
        ),
    )
    restored = CalibrationManifest.model_validate_json(manifest.model_dump_json())
    restored.validate_inventory(inventory)
    changed = manifest.model_dump()
    changed["limits"]["max_total_attempts"] = 20
    with pytest.raises(ValidationError, match="digest mismatch"):
        CalibrationManifest.model_validate(changed)
    changed = inventory.model_copy(update={"source_identity": {"fixture": "different"}})
    with pytest.raises(ValidationError):
        manifest.validate_inventory(changed)


def test_related_families_cannot_leak_across_splits() -> None:
    inventory = freeze_inventory(AutomationBenchConfig(), source_identity={"fixture": "candidate"})
    selections = tuple(
        TaskSelection(
            task_name=task.task_name, task_digest=task.digest, family="shared-family", split=split
        )
        for task, split in zip(inventory.tasks[:2], ("development", "evaluation"), strict=True)
    )
    with pytest.raises(ValidationError, match="family crosses splits"):
        plan_collection(
            inventory,
            selections=selections,
            route_identity="fixture-only",
            native_config={"harness": "codex"},
            scorer_revision="fixture-only",
            limits=CollectionLimits(
                max_total_attempts=2,
                max_elapsed_seconds=60,
                attempt_timeout_seconds=20,
                max_turns=4,
                max_output_tokens=100,
                cost_measurement="unavailable",
            ),
        )


def test_priced_collection_requires_cost_cap_and_positive_limits() -> None:
    with pytest.raises(ValidationError, match="hard cost ceiling"):
        CollectionLimits(
            max_total_attempts=2,
            max_elapsed_seconds=60,
            attempt_timeout_seconds=20,
            max_turns=4,
            max_output_tokens=100,
            cost_measurement="priced_usage",
        )
    with pytest.raises(ValidationError):
        CollectionLimits(
            max_total_attempts=0,
            max_elapsed_seconds=60,
            attempt_timeout_seconds=20,
            max_turns=4,
            max_output_tokens=100,
            cost_measurement="unavailable",
        )
