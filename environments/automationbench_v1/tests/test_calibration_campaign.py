"""Offline campaign partition/split contracts; no signed-in model dispatch."""

import pytest

from automationbench_v1.calibration.campaign import partition_inventory, split_selections
from automationbench_v1.calibration.inventory import content_digest, freeze_inventory
from automationbench_v1.taskset import AutomationBenchConfig


def test_partition_is_exhaustive_and_only_changes_declared_clock_context():
    inventory = freeze_inventory(
        AutomationBenchConfig(
            domains=["simple", "hr"],
            task_names=["simple.email_sf_contact_phone_update", "hr.i9_verification_tracking"],
        ),
        source_identity={"test": True},
    )
    result, partitions = partition_inventory(inventory)
    assert partitions == {
        "timed": ["hr.i9_verification_tracking"],
        "untimed": ["simple.email_sf_contact_phone_update"],
    }
    assert len(result.tasks) == len(inventory.tasks) == 2
    original = {task.task_name: task for task in inventory.tasks}
    for task in result.tasks:
        prior = original[task.task_name]
        assert task.data["initial_state"] == prior.data["initial_state"]
        assert task.data["assertions"] == prior.data["assertions"]
        if task.task_name.startswith("simple."):
            assert task == prior
        else:
            assert task.config["world_time_context"] is True
            assert task.data["prompt"][1:] == prior.data["prompt"][1:]
            assert task.data["prompt"][0]["content"].startswith(prior.data["prompt"][0]["content"])
            assert task.digest != prior.digest


def test_reviewed_splits_require_exact_coverage_and_family_disjointness():
    inventory = freeze_inventory(
        AutomationBenchConfig(
            task_names=[
                "simple.email_sf_contact_phone_update",
                "simple.email_sf_contact_email_update",
            ]
        ),
        source_identity={"test": True},
    )
    rows = {
        task.task_name: {"family": "contact-field-updates", "split": "development"}
        for task in inventory.tasks
    }
    assignment = {
        "schema_version": 1,
        "reviewed": True,
        "method": "explicit source-reviewed related variants",
        "tasks": rows,
    }
    selections = split_selections(inventory, assignment)
    assert len(selections) == 2 and len({row.family for row in selections}) == 1
    rows[inventory.tasks[1].task_name]["split"] = "evaluation"
    with pytest.raises(ValueError, match="crosses splits"):
        split_selections(inventory, assignment)
    rows.pop(inventory.tasks[1].task_name)
    with pytest.raises(ValueError, match="exactly"):
        split_selections(inventory, assignment)
    assignment["reviewed"] = False
    with pytest.raises(ValueError, match="reviewed"):
        split_selections(inventory, assignment)


def test_invalid_declared_clock_is_not_silently_treated_as_missing():
    inventory = freeze_inventory(
        AutomationBenchConfig(task_names=["simple.email_sf_contact_phone_update"]),
        source_identity={"test": True},
    )
    body = inventory.model_dump(mode="json", exclude={"digest"})
    task = body["tasks"][0]
    task["data"]["initial_state"].setdefault("meta", {})["current_time"] = "not-a-clock"
    task["digest"] = content_digest({"data": task["data"], "config": task["config"]})
    modified = type(inventory).model_validate({**body, "digest": content_digest(body)})
    with pytest.raises(ValueError, match="invalid declared clock"):
        partition_inventory(modified)
