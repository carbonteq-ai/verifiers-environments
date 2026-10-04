"""Versioned collection policy; native episodes remain the execution authority."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .inventory import TaskInventory, content_digest


class CollectionLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    max_concurrent: int = Field(default=2, gt=0, strict=True)
    max_attempts_per_task: int = Field(default=6, gt=0, strict=True)
    """Ordinary, confirmation and rescue attempts; infrastructure retries have their own cap."""
    max_total_attempts: int = Field(gt=0, strict=True)
    max_infrastructure_retries: int = Field(default=0, ge=0, strict=True)
    max_elapsed_seconds: float = Field(gt=0, allow_inf_nan=False)
    attempt_timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    max_turns: int = Field(gt=0, strict=True)
    max_output_tokens: int = Field(gt=0, strict=True)
    """Total sampled output tokens per episode, not a per-response limit."""
    cost_ceiling_usd: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    cost_measurement: Literal["priced_usage", "unavailable"]

    @model_validator(mode="after")
    def check_cost(self) -> CollectionLimits:
        if self.cost_measurement == "priced_usage" and self.cost_ceiling_usd is None:
            raise ValueError("priced collection requires a hard cost ceiling")
        if self.cost_measurement == "unavailable" and self.cost_ceiling_usd is not None:
            raise ValueError("unmeasured cost cannot have an enforceable currency ceiling")
        if self.max_concurrent > self.max_total_attempts:
            raise ValueError("concurrency exceeds total attempt ceiling")
        return self


class TaskSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_name: str = Field(min_length=1)
    task_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    family: str = Field(min_length=1)
    split: Literal["development", "reward_test", "evaluation"]


class CalibrationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    inventory_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_id: Literal["gpt-6-luna"]
    provider_model_id: str = Field(min_length=1)
    route_identity: str = Field(min_length=1)
    # Composition supplies the native config; credentials never belong here.
    native_config: dict[str, Any]
    source_identity: dict[str, Any]
    scorer_revision: str = Field(min_length=1)
    tasks: tuple[TaskSelection, ...] = Field(min_length=1)
    limits: CollectionLimits
    parent_manifest_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def check_manifest(self) -> CalibrationManifest:
        names = [task.task_name for task in self.tasks]
        if len(names) != len(set(names)):
            raise ValueError("duplicate selected task")
        families: dict[str, str] = {}
        for task in self.tasks:
            previous = families.setdefault(task.family, task.split)
            if previous != task.split:
                raise ValueError("related task family crosses splits")
        if self.limits.max_total_attempts < len(self.tasks):
            raise ValueError("attempt ceiling cannot cover even one attempt per task")
        if not self.native_config or not self.source_identity:
            raise ValueError("native configuration and source identity are required")
        if self.digest != content_digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("collection manifest content digest mismatch")
        return self

    def validate_inventory(self, inventory: TaskInventory) -> None:
        inventory = TaskInventory.model_validate(inventory.model_dump())
        checked = CalibrationManifest.model_validate(self.model_dump())
        if checked.inventory_digest != inventory.digest:
            raise ValueError("collection inventory changed")
        if checked.source_identity != inventory.source_identity:
            raise ValueError("collection source differs from frozen inventory")
        available = {task.task_name: task for task in inventory.tasks}
        for selected in checked.tasks:
            task = available.get(selected.task_name)
            if task is None or task.digest != selected.task_digest:
                raise ValueError("selected task is absent or changed")
            if task.initial_score["status"] != "valid":
                raise ValueError("selected task has an unresolved initial verifier failure")


def plan_collection(
    inventory: TaskInventory,
    *,
    selections: tuple[TaskSelection, ...],
    route_identity: str,
    provider_model_id: str = "gpt-6-luna",
    native_config: dict[str, Any],
    scorer_revision: str,
    limits: CollectionLimits,
    parent_manifest_digest: str | None = None,
) -> CalibrationManifest:
    body = {
        "schema_version": 1,
        "inventory_digest": inventory.digest,
        "model_id": "gpt-6-luna",
        "provider_model_id": provider_model_id,
        "route_identity": route_identity,
        "native_config": native_config,
        "source_identity": inventory.source_identity,
        "scorer_revision": scorer_revision,
        "tasks": [task.model_dump(mode="json") for task in selections],
        "limits": limits.model_dump(mode="json"),
        "parent_manifest_digest": parent_manifest_digest,
    }
    manifest = CalibrationManifest.model_validate({**body, "digest": content_digest(body)})
    manifest.validate_inventory(inventory)
    return manifest
