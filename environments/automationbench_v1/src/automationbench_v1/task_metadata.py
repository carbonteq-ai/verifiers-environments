"""Host-side task facets and source-bound reference observations.

This is a derived export, not a scorer or an eligibility decision. Native
episodes and frozen inventories remain authoritative. No value enters prompts.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

DIGEST = r"^[0-9a-f]{64}$"
FACETS = ("workflow", "capabilities", "guard_patterns")
METADATA_FIELDS = (*FACETS, "task_metadata_digest", "task_metadata_status")


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def task_content_digest(data: dict[str, Any]) -> str:
    """Exclude reporting metadata and positional idx, retaining every task input."""
    return digest(
        {key: value for key, value in data.items() if key not in (*METADATA_FIELDS, "idx")}
    )


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Artifact(Record):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=DIGEST)

    @classmethod
    def capture(cls, path: Path) -> Self:
        return cls(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def read(self) -> bytes:
        raw = Path(self.path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.sha256:
            raise ValueError(f"metadata source artifact hash mismatch: {self.path}")
        return raw


class Classification(Record):
    status: Literal["not_reviewed", "reviewed"] = "not_reviewed"
    labels: tuple[str, ...] = ()
    definition_revision: str | None = None
    evidence: tuple[Artifact, ...] = ()

    @model_validator(mode="after")
    def check(self) -> Self:
        if any(not item.strip() or item != item.strip() for item in self.labels):
            raise ValueError("classification labels must be nonempty trimmed strings")
        if tuple(sorted(set(self.labels))) != self.labels:
            raise ValueError("classification labels must be sorted and unique")
        if self.status == "reviewed":
            if not self.definition_revision or not self.evidence:
                raise ValueError("reviewed classification requires definition and evidence")
        elif self.labels or self.evidence or self.definition_revision:
            raise ValueError("unreviewed classification cannot claim labels")
        return self


class Measurement(Record):
    status: Literal["observed", "unavailable"]
    value: int | None = Field(default=None, ge=0, strict=True)
    convention: str = Field(min_length=1)
    reason: str | None = None

    @model_validator(mode="after")
    def check(self) -> Self:
        if (self.status == "observed") != (self.value is not None):
            raise ValueError("measurement value and status disagree")
        if self.status == "unavailable" and not self.reason:
            raise ValueError("unavailable measurement requires reason")
        return self


class ReferenceObservation(Record):
    """One retained attempt; no aggregate success rate or enforced budget."""

    episode: Artifact
    inventory: Artifact
    manifest: Artifact
    episode_id: str
    trace_id: str
    attempt_id: str
    run_id: str
    source_identity_digest: str = Field(pattern=DIGEST)
    source_revisions: dict[str, str]
    frozen_task_digest: str = Field(pattern=DIGEST)
    scorer_revision: str
    model: str
    provider_model: str
    route: str
    sampling: dict[str, Any] | None
    collection_limits: dict[str, Any]
    split: str
    reference_family: str
    recorded_reward: float | None
    recorded_reward_weight: float | None
    recorded_strict_completion: float | None
    execution_ok: bool
    is_completed: bool
    stop_condition: str | None
    truncation: Literal["truncated", "not_truncated", "unknown"]
    tool_calls: Measurement
    reported_output_tokens: Measurement
    sampled_output_tokens: Measurement
    redesigned_guard_qualification: Literal["unassessed"] = "unassessed"
    efficiency_budget_status: Literal["observation_only"] = "observation_only"


class TaskMetadata(Record):
    task_name: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    task_content_digest: str = Field(pattern=DIGEST)
    classifications: dict[str, Classification] = Field(
        default_factory=lambda: {name: Classification() for name in FACETS}
    )
    references: tuple[ReferenceObservation, ...] = ()

    @model_validator(mode="after")
    def check(self) -> Self:
        if set(self.classifications) != set(FACETS):
            raise ValueError("classification dimensions must be explicit")
        ids = [(item.episode.sha256, item.trace_id) for item in self.references]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate reference observation")
        return self


class TaskMetadataExport(Record):
    schema_version: Literal[1] = 1
    producer: Literal["automationbench-task-metadata-v1"] = "automationbench-task-metadata-v1"
    source_index: Artifact
    tasks: tuple[TaskMetadata, ...] = Field(min_length=1)
    digest: str = Field(pattern=DIGEST)

    @model_validator(mode="after")
    def check(self) -> Self:
        names = [task.task_name for task in self.tasks]
        if names != sorted(set(names)):
            raise ValueError("metadata tasks must be unique and sorted")
        if self.digest != digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("metadata export content digest mismatch")
        return self

    def verify_sources(self) -> None:
        artifacts = [self.source_index]
        for task in self.tasks:
            for classification in task.classifications.values():
                artifacts.extend(classification.evidence)
            for reference in task.references:
                artifacts.extend((reference.episode, reference.inventory, reference.manifest))
        for path, sha256 in sorted({(item.path, item.sha256) for item in artifacts}):
            Artifact(path=path, sha256=sha256).read()


def _measurement(value: int | None, convention: str, reason: str) -> Measurement:
    return Measurement(
        status="unavailable" if value is None else "observed",
        value=value,
        convention=convention,
        reason=reason if value is None else None,
    )


def _observe(episode: dict, trace: dict, frozen, manifest, artifacts) -> ReferenceObservation:
    occurrences = {
        event["invocation_id"]
        for event in trace.get("tool_execution_events", [])
        if event.get("source") == "tool_server" and event.get("phase") == "dispatch"
    }
    events = trace.get("tool_execution_events", [])
    budget = trace.get("info", {}).get("automationbench_output_budget", {})
    accounting = budget.get("response_accounting") or {}
    output = (
        accounting.get("reported_counts", {}).get("outputTokens")
        if accounting.get("status") == "reconciled"
        else None
    )
    nodes = [node for node in trace.get("nodes", []) if node.get("sampled")]
    aligned = bool(nodes) and all(
        node.get("token_ids")
        and len(node["token_ids"]) == len(node.get("mask", []))
        and all(type(value) is bool for value in node["mask"])
        for node in nodes
    )
    sampled = sum(sum(node["mask"]) for node in nodes) if aligned else None
    stop = trace.get("stop_condition")
    truncated = stop in {
        "max_turns",
        "max_input_tokens",
        "max_output_tokens",
        "max_total_tokens",
    } or any(call.get("finish_reason") == "length" for call in trace.get("calls", []))
    sdk = trace.get("info", {}).get("codex_sdk", {})
    # A terminal SDK response may not have native model-call finish reasons.
    truncation = (
        "truncated"
        if truncated
        else ("unknown" if sdk and not trace.get("calls") else "not_truncated")
    )
    reward = trace.get("rewards", {}).get("partial_credit") or {}
    task_selection = next(item for item in manifest.tasks if item.task_name == frozen.task_name)
    revisions = {
        name: item["git_revision"]
        for name, item in manifest.source_identity.get("packages", {}).items()
        if "git_revision" in item
    }
    return ReferenceObservation(
        episode=artifacts[0],
        inventory=artifacts[1],
        manifest=artifacts[2],
        episode_id=episode["id"],
        trace_id=trace["id"],
        attempt_id=episode["group"]["id"],
        run_id=episode["run"]["id"],
        source_identity_digest=digest(manifest.source_identity),
        source_revisions=revisions,
        frozen_task_digest=frozen.digest,
        scorer_revision=manifest.scorer_revision,
        model=trace["agent"]["config"]["model"],
        provider_model=manifest.provider_model_id,
        route=manifest.route_identity,
        sampling=trace["agent"]["config"].get("sampling", {}),
        collection_limits=manifest.limits.model_dump(mode="json"),
        split=task_selection.split,
        reference_family=task_selection.family,
        recorded_reward=reward.get("score"),
        recorded_reward_weight=reward.get("weight"),
        recorded_strict_completion=trace.get("metrics", {}).get("task_completed_correctly"),
        execution_ok=episode["ok"] and trace["ok"],
        is_completed=trace["is_completed"],
        stop_condition=stop,
        truncation=truncation,
        tool_calls=_measurement(
            len(occurrences) if events else None,
            "distinct retained tool_server dispatch invocation IDs, including search and failures",
            "tool_execution_receipts_unavailable",
        ),
        reported_output_tokens=_measurement(
            output,
            accounting.get("contract") or "SDK reported completed-response output tokens",
            accounting.get("reason") or "reconciled_sdk_usage_unavailable",
        ),
        sampled_output_tokens=_measurement(
            sampled,
            "original native sampled token positions",
            "original_sampled_token_alignment_unavailable",
        ),
    )


def build_reference_metadata(index_path: Path) -> TaskMetadataExport:
    """Export retained development episodes from a review index or reference selection.

    Each episode must have its original inventory.json and manifest.json in its
    parent run directory. Index family/score annotations are not trusted as labels.
    """
    from .calibration.collector import validate_episode
    from .calibration.inventory import load_inventory
    from .calibration.models import CalibrationManifest

    source = Artifact.capture(index_path)
    index = json.loads(source.read())
    if "source_index_path" in index:
        Artifact(path=index["source_index_path"], sha256=index["source_index_sha256"]).read()
    rows = index.get("tasks", index.get("entries"))
    if not isinstance(rows, list):
        raise TypeError("metadata index requires tasks or entries")
    tasks, runs = {}, {}
    for row in rows:
        if row.get("split") != "development":
            raise ValueError("reference metadata export requires explicit development split")
        path_value = row.get("source_episode_path", row.get("episode_path"))
        if path_value is None:
            raise ValueError(
                "reference index entry lacks retained episode; export retained entries only"
            )
        episode_ref = Artifact(
            path=path_value, sha256=row.get("source_episode_sha256", row.get("episode_digest"))
        )
        episode_ref.read()
        directory = Path(episode_ref.path).parent.parent
        if directory not in runs:
            inventory_ref = Artifact.capture(directory / "inventory.json")
            manifest_ref = Artifact.capture(directory / "manifest.json")
            inventory = load_inventory(Path(inventory_ref.path))
            manifest = CalibrationManifest.model_validate_json(manifest_ref.read())
            manifest.validate_inventory(inventory)
            runs[directory] = (inventory, manifest, inventory_ref, manifest_ref)
        inventory, manifest, inventory_ref, manifest_ref = runs[directory]
        frozen = next(
            (task for task in inventory.tasks if task.task_name == row["task_name"]), None
        )
        if frozen is None:
            raise ValueError("metadata task missing from source inventory")
        native, _ = validate_episode(Path(episode_ref.path), frozen)
        episode = json.loads(episode_ref.read())
        if (
            native.run is None
            or native.run.id != manifest.digest
            or native.group is None
            or native.group.id != row["attempt_id"]
        ):
            raise ValueError("metadata episode run/attempt source mismatch")
        selected = next(
            (item for item in manifest.tasks if item.task_name == frozen.task_name), None
        )
        if selected is None or selected.split != "development":
            raise ValueError("metadata task lacks development source binding")
        observations = tuple(
            _observe(episode, trace, frozen, manifest, (episode_ref, inventory_ref, manifest_ref))
            for trace in episode["traces"]
        )
        entry = TaskMetadata(
            task_name=frozen.task_name,
            domain=frozen.domain,
            task_content_digest=task_content_digest(frozen.data),
            references=observations,
        )
        if entry.task_name in tasks:
            raise ValueError("duplicate metadata task; explicit attempt aggregation is required")
        tasks[entry.task_name] = entry
    body = {
        "schema_version": 1,
        "producer": "automationbench-task-metadata-v1",
        "source_index": source.model_dump(mode="json"),
        "tasks": [tasks[key].model_dump(mode="json") for key in sorted(tasks)],
    }
    return TaskMetadataExport.model_validate({**body, "digest": digest(body)})


def save_task_metadata(export: TaskMetadataExport, path: Path) -> None:
    checked = TaskMetadataExport.model_validate(export.model_dump(mode="json"))
    checked.verify_sources()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(checked.model_dump_json(indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_task_metadata(path: Path, *, expected_digest: str) -> TaskMetadataExport:
    export = TaskMetadataExport.model_validate_json(path.read_bytes())
    if export.digest != expected_digest:
        raise ValueError("metadata selection digest mismatch")
    export.verify_sources()
    return export


def attach_task_metadata(data, export: TaskMetadataExport):
    """Attach declared facets to native task data without modifying its prompt."""
    export = TaskMetadataExport.model_validate(export.model_dump(mode="json"))
    entry = next((task for task in export.tasks if task.task_name == data.task_name), None)
    if entry is None:
        raise ValueError(f"task missing from selected metadata: {data.task_name}")
    if entry.domain != data.domain or entry.task_content_digest != task_content_digest(
        data.model_dump(mode="json")
    ):
        raise ValueError(f"metadata task content hash mismatch: {data.task_name}")
    updates: dict[str, Any] = {
        key: list(value.labels) for key, value in entry.classifications.items()
    }
    updates.update(
        task_metadata_digest=export.digest,
        task_metadata_status={key: value.status for key, value in entry.classifications.items()},
    )
    return type(data).model_validate({**data.model_dump(mode="python"), **updates})
