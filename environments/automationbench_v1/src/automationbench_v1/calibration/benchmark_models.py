"""Sealed three-model comparison policy, separate from Luna's SDK collection."""

from __future__ import annotations

import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..capture import canonical_json
from .eligibility import ReassessmentVerifier, TaskEligibilityProof, validate_eligibility_proof
from .frozen_verification import FrozenVerifierBinding
from .inventory import TaskInventory, content_digest
from .models import TaskSelection
from .reward_revision import RedesignRevision

type ModelSize = Literal["9b", "4b", "2b"]


class BenchmarkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ModelBenchmarkBinding(BenchmarkRecord):
    """Declared immutable serving inputs; actual deployment qualification is separate.

    No credentials, serving launch policy or teacher configuration belongs here.
    Binding equality is required at dispatch, but is not proof a remote service
    actually loaded these weights. Composition must qualify that before real runs.
    """

    size: ModelSize
    model_id: Literal["Qwen/Qwen3.5-9B", "Qwen/Qwen3.5-4B", "Qwen/Qwen3.5-2B"]
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    served_model_id: str = Field(min_length=1)
    tokenizer_id: str = Field(min_length=1)
    tokenizer_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    tokenizer_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    chat_template_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    renderer_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_id: str = Field(min_length=1)
    runtime_revision: str = Field(pattern=r"^(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")
    runtime_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    route_identity: str = Field(min_length=1)
    precision: Literal["bf16", "fp16", "fp32", "int8", "int4"]
    reasoning_mode: str = Field(min_length=1)
    tools_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    native_configuration_json: str

    @property
    def digest(self) -> str:
        return content_digest(self.model_dump(mode="json"))

    @model_validator(mode="after")
    def verify(self) -> Self:
        if self.model_id != f"Qwen/Qwen3.5-{self.size.upper()}":
            raise ValueError("model size differs from its selected family")
        configured = json.loads(self.native_configuration_json)
        if not isinstance(configured, dict) or not configured:
            raise ValueError("native model configuration must be an explicit object")
        if canonical_json(configured) != self.native_configuration_json:
            raise ValueError("native model configuration must be canonical JSON")
        return self


class EligibleBenchmarkTask(BenchmarkRecord):
    selection: TaskSelection
    proof: TaskEligibilityProof


class EligibleBenchmarkPool(BenchmarkRecord):
    schema_version: Literal[1] = 1
    inventory_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    redesign_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_identity_json: str
    tasks: tuple[EligibleBenchmarkTask, ...] = Field(min_length=1)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify(self) -> Self:
        names = [item.selection.task_name for item in self.tasks]
        if len(names) != len(set(names)):
            raise ValueError("duplicate eligible benchmark task")
        families: dict[str, str] = {}
        for item in self.tasks:
            selected = item.selection
            if families.setdefault(selected.family, selected.split) != selected.split:
                raise ValueError("benchmark family crosses declared splits")
            if (item.proof.task_name, item.proof.task_digest, item.proof.redesign_digest) != (
                selected.task_name,
                selected.task_digest,
                self.redesign_digest,
            ):
                raise ValueError("benchmark proof belongs to another task or redesign")
        if canonical_json(json.loads(self.source_identity_json)) != self.source_identity_json:
            raise ValueError("benchmark source identity must be canonical JSON")
        if self.digest != content_digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("eligible pool digest mismatch")
        return self

    def validate_inventory(
        self,
        inventory: TaskInventory,
        revision: RedesignRevision,
        *,
        approved_bindings: dict[str, FrozenVerifierBinding],
        reassessment_verifiers: dict[str, ReassessmentVerifier],
    ) -> None:
        checked = type(self).model_validate_json(self.model_dump_json())
        inventory = TaskInventory.model_validate_json(inventory.model_dump_json())
        revision = RedesignRevision.model_validate_json(revision.model_dump_json())
        if checked.redesign_digest != revision.digest:
            raise ValueError("accepted redesign changed; Luna eligibility must be reverified")
        if (
            checked.inventory_digest != inventory.digest
            or checked.source_identity_json != canonical_json(inventory.source_identity)
        ):
            raise ValueError("benchmark inventory or source changed")
        available = {task.task_name: task for task in inventory.tasks}
        for item in checked.tasks:
            frozen = available.get(item.selection.task_name)
            if frozen is None or frozen.digest != item.selection.task_digest:
                raise ValueError("benchmark task is outside the eligible frozen pool")
            if frozen.initial_score.get("status") != "valid":
                raise ValueError("benchmark task has unresolved initial verifier failure")
            validate_eligibility_proof(
                item.proof,
                task_name=frozen.task_name,
                task_digest=frozen.digest,
                redesign_digest=revision.digest,
                current_redesign=revision,
                approved_bindings=approved_bindings,
                reassessment_verifiers=reassessment_verifiers,
            )


class BenchmarkLimits(BenchmarkRecord):
    max_concurrent: int = Field(default=10, gt=0, strict=True)
    max_total_attempts: int = Field(gt=0, strict=True)
    max_elapsed_seconds: float = Field(gt=0)
    attempt_timeout_seconds: float = Field(gt=0)
    max_turns: int = Field(gt=0, strict=True)
    max_output_tokens: int = Field(gt=0, strict=True)
    max_input_tokens_per_response: int = Field(gt=0, strict=True)
    max_tool_calls: int = Field(gt=0, strict=True)


class BenchmarkManifest(BenchmarkRecord):
    schema_version: Literal[1] = 1
    purpose: Literal["qwen35_three_model_benchmark"] = "qwen35_three_model_benchmark"
    pool: EligibleBenchmarkPool
    bindings: tuple[ModelBenchmarkBinding, ...]
    repeats_per_task_and_model: Literal[3] = 3
    sampling_json: str
    limits: BenchmarkLimits
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def expected_attempts(self) -> int:
        return len(self.pool.tasks) * len(self.bindings) * self.repeats_per_task_and_model

    @model_validator(mode="after")
    def verify(self) -> Self:
        if len(self.bindings) != 3 or {item.size for item in self.bindings} != {"9b", "4b", "2b"}:
            raise ValueError("benchmark requires all three distinct Qwen model bindings")
        if len({item.served_model_id for item in self.bindings}) != 3:
            raise ValueError("served model aliases must distinguish all three bindings")
        if len({item.tools_policy_digest for item in self.bindings}) != 1:
            raise ValueError("benchmark models must share the same tool policy")
        sampling = json.loads(self.sampling_json)
        if (
            not isinstance(sampling, dict)
            or not sampling
            or canonical_json(sampling) != self.sampling_json
        ):
            raise ValueError("benchmark sampling must be one explicit canonical policy")
        if self.limits.max_total_attempts != self.expected_attempts:
            raise ValueError("benchmark ceiling must account for exactly nine attempts per task")
        if self.limits.max_concurrent > self.expected_attempts:
            raise ValueError("benchmark concurrency exceeds its logical attempt count")
        if self.digest != content_digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("benchmark manifest digest mismatch")
        return self


def plan_benchmark(
    inventory: TaskInventory,
    *,
    revision: RedesignRevision,
    tasks: tuple[EligibleBenchmarkTask, ...],
    bindings: tuple[ModelBenchmarkBinding, ...],
    sampling: dict,
    limits: BenchmarkLimits,
    approved_bindings: dict[str, FrozenVerifierBinding],
    reassessment_verifiers: dict[str, ReassessmentVerifier],
) -> BenchmarkManifest:
    pool_body = {
        "schema_version": 1,
        "inventory_digest": inventory.digest,
        "redesign_digest": revision.digest,
        "source_identity_json": canonical_json(inventory.source_identity),
        "tasks": [item.model_dump(mode="json") for item in tasks],
    }
    pool = EligibleBenchmarkPool.model_validate({**pool_body, "digest": content_digest(pool_body)})
    pool.validate_inventory(
        inventory,
        revision,
        approved_bindings=approved_bindings,
        reassessment_verifiers=reassessment_verifiers,
    )
    body = {
        "schema_version": 1,
        "purpose": "qwen35_three_model_benchmark",
        "pool": pool.model_dump(mode="json"),
        "bindings": [item.model_dump(mode="json") for item in bindings],
        "repeats_per_task_and_model": 3,
        "sampling_json": canonical_json(sampling),
        "limits": limits.model_dump(mode="json"),
    }
    return BenchmarkManifest.model_validate({**body, "digest": content_digest(body)})


class BenchmarkAttempt(BenchmarkRecord):
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_size: ModelSize
    task_name: str = Field(min_length=1)
    task_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    occurrence: int = Field(ge=0, lt=3, strict=True)
    attempt_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify(self) -> Self:
        if self.attempt_id != content_digest(self.model_dump(mode="json", exclude={"attempt_id"})):
            raise ValueError("benchmark attempt identity mismatch")
        return self


def benchmark_attempts(manifest: BenchmarkManifest) -> tuple[BenchmarkAttempt, ...]:
    """Fresh logical occurrences; no success-driven stopping or invisible retries."""
    manifest = BenchmarkManifest.model_validate_json(manifest.model_dump_json())
    attempts = []
    for occurrence in range(manifest.repeats_per_task_and_model):
        for item in manifest.pool.tasks:
            for binding in manifest.bindings:
                body = {
                    "manifest_digest": manifest.digest,
                    "binding_digest": binding.digest,
                    "model_size": binding.size,
                    "task_name": item.selection.task_name,
                    "task_digest": item.selection.task_digest,
                    "occurrence": occurrence,
                }
                attempts.append(
                    BenchmarkAttempt.model_validate({**body, "attempt_id": content_digest(body)})
                )
    return tuple(attempts)


class BenchmarkArtifact(BenchmarkRecord):
    path: str = Field(min_length=1)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class BenchmarkAttemptResult(BenchmarkRecord):
    attempt: BenchmarkAttempt
    status: Literal["completed", "truncated", "failed", "interrupted"]
    episode_path: str = Field(min_length=1)
    episode_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    error_type: str | None = None
    summary_json: str
    discarded_traces: tuple[BenchmarkArtifact, ...] = ()
    controller_receipt: BenchmarkArtifact | None = None
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify(self) -> Self:
        if self.status in {"failed", "interrupted"} and not self.error_type:
            raise ValueError("failed benchmark attempt requires an explained disposition")
        if (self.status == "interrupted") != (self.controller_receipt is not None):
            raise ValueError("interrupted benchmark attempt requires a controller receipt")
        if canonical_json(json.loads(self.summary_json)) != self.summary_json:
            raise ValueError("benchmark summary must be canonical JSON")
        if self.digest != content_digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("benchmark result digest mismatch")
        return self


class ModelBenchmarkResult(BenchmarkRecord):
    """Collection coverage only: completed collection does not mean model success."""

    manifest: BenchmarkManifest
    attempts: tuple[BenchmarkAttemptResult, ...]
    pending_attempt_ids: tuple[str, ...]
    collection_status: Literal["complete", "incomplete"]
    qualification: Literal["scaffold_only"] = "scaffold_only"

    @model_validator(mode="after")
    def verify(self) -> Self:
        expected = {item.attempt_id: item for item in benchmark_attempts(self.manifest)}
        returned = {item.attempt.attempt_id: item for item in self.attempts}
        if len(returned) != len(self.attempts):
            raise ValueError("duplicate benchmark occurrence result")
        if any(expected.get(key) != item.attempt for key, item in returned.items()):
            raise ValueError("unexpected or changed benchmark occurrence")
        missing = set(expected) - set(returned)
        if (
            len(set(self.pending_attempt_ids)) != len(self.pending_attempt_ids)
            or set(self.pending_attempt_ids) != missing
        ):
            raise ValueError("benchmark missing occurrence accounting mismatch")
        if self.collection_status != ("incomplete" if missing else "complete"):
            raise ValueError("benchmark collection completeness mismatch")
        return self
