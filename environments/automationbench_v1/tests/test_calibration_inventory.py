from pathlib import Path

import pytest
from pydantic import ValidationError

import automationbench_v1.calibration.inventory as inventory_module
from automationbench_v1.calibration.inventory import (
    TaskInventory,
    freeze_inventory,
    load_inventory,
    save_inventory,
)
from automationbench_v1.taskset import AutomationBenchConfig


def test_inventory_reloads_actual_generated_tasks_without_factories(tmp_path: Path) -> None:
    inventory = freeze_inventory(
        AutomationBenchConfig(domains=["simple"]), source_identity={"candidate": "test-only"}
    )
    path = tmp_path / "private-inventory.json"
    save_inventory(inventory, path)
    restored = load_inventory(path)
    assert restored == inventory
    for frozen in restored.tasks:
        task = frozen.instantiate()
        assert task.data.model_dump(mode="json") == frozen.data
        assert task.key == frozen.task_name
        assert frozen.initial_score["status"] == "valid"
    with pytest.raises(FileExistsError):
        save_inventory(inventory, path)


def test_inventory_rejects_tampering_and_mutable_nested_data(tmp_path: Path) -> None:
    inventory = freeze_inventory(
        AutomationBenchConfig(domains=["simple"]), source_identity={"candidate": "test-only"}
    )
    raw = inventory.model_dump()
    raw["tasks"][0]["data"]["task_name"] = "forged"
    with pytest.raises(ValidationError):
        TaskInventory.model_validate(raw)
    inventory.tasks[0].data["prompt"] = "changed after validation"
    with pytest.raises(ValidationError, match="digest mismatch"):
        save_inventory(inventory, tmp_path / "bad.json")


def test_verifier_execution_failure_is_retained_without_numeric_zero(monkeypatch) -> None:
    def broken_score(**kwargs):
        raise RuntimeError("verifier fixture failed")

    monkeypatch.setattr(inventory_module, "score_world", broken_score)
    inventory = freeze_inventory(
        AutomationBenchConfig(domains=["simple"]), source_identity={"candidate": "test-only"}
    )
    assert inventory.tasks
    for task in inventory.tasks:
        assert task.initial_score == {
            "status": "failed",
            "error_type": "RuntimeError",
            "error": "verifier fixture failed",
        }
