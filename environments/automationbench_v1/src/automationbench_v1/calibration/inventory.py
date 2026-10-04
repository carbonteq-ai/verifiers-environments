"""Freeze generated tasks, including hidden verifier inputs, for host-side replay.

These files are private calibration artifacts. Never place them in the agent's
filesystem or messages: they include assertions and the entire starting world.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..scoring import score_world
from ..taskset import (
    AutomationBenchConfig,
    AutomationBenchData,
    AutomationBenchTask,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)


def content_digest(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class FrozenTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_name: str
    domain: str
    data: dict[str, Any]
    config: dict[str, Any]
    digest: str
    initial_score: dict[str, Any]

    @model_validator(mode="after")
    def validate_task(self) -> FrozenTask:
        data = AutomationBenchData.model_validate(self.data)
        AutomationBenchTaskConfig.model_validate(self.config)
        if (data.task_name, data.domain) != (self.task_name, self.domain):
            raise ValueError("task identity differs from frozen data")
        if self.digest != content_digest({"data": self.data, "config": self.config}):
            raise ValueError("frozen task content digest mismatch")
        return self

    def instantiate(self) -> AutomationBenchTask:
        # Revalidate mutable nested dictionaries, and never invoke a factory.
        checked = FrozenTask.model_validate(self.model_dump())
        return AutomationBenchTask(
            AutomationBenchData.model_validate(checked.data),
            AutomationBenchTaskConfig.model_validate(checked.config),
        )


class TaskInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    source_identity: dict[str, Any]
    loader_config: dict[str, Any]
    tasks: tuple[FrozenTask, ...] = Field(min_length=1)
    digest: str

    @model_validator(mode="after")
    def validate_inventory(self) -> TaskInventory:
        names = [task.task_name for task in self.tasks]
        if len(names) != len(set(names)):
            raise ValueError("duplicate task identity in inventory")
        if self.digest != content_digest(self.model_dump(exclude={"digest"})):
            raise ValueError("inventory content digest mismatch")
        if not self.source_identity:
            raise ValueError("source identity is required")
        return self


def freeze_inventory(
    config: AutomationBenchConfig, *, source_identity: dict[str, Any]
) -> TaskInventory:
    tasks = []
    for task in AutomationBenchTaskset(config).load():
        data = task.data.model_dump(mode="json")
        task_config = task.config.model_dump(mode="json")
        try:
            score = score_world(
                world=data["initial_state"],
                initial_state=data["initial_state"],
                assertions=tuple(data["assertions"]),
            )
            initial_score = {
                "status": "valid",
                "partial_credit": score.partial_credit,
                "strict_completion": score.task_completed_correctly,
                "assertion_results": list(score.assertion_results),
            }
        except Exception as exc:  # noqa: BLE001 -- retain task-local verifier failures as evidence
            # A broken verifier is not an observed wrong answer.
            initial_score = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        tasks.append(
            FrozenTask(
                task_name=task.data.task_name,
                domain=task.data.domain,
                data=data,
                config=task_config,
                digest=content_digest({"data": data, "config": task_config}),
                initial_score=initial_score,
            )
        )
    body = {
        "schema_version": 1,
        "source_identity": source_identity,
        "loader_config": config.model_dump(mode="json"),
        "tasks": [task.model_dump(mode="json") for task in tasks],
    }
    return TaskInventory.model_validate({**body, "digest": content_digest(body)})


def save_inventory(inventory: TaskInventory, path: Path) -> None:
    checked = TaskInventory.model_validate(inventory.model_dump())
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents silently overwriting a generated task bank.
    with path.open("x", encoding="utf-8") as stream:
        stream.write(checked.model_dump_json(indent=2) + "\n")


def load_inventory(path: Path) -> TaskInventory:
    return TaskInventory.model_validate_json(path.read_text(encoding="utf-8"))
