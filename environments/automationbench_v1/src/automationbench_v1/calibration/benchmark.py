"""Bounded injected-runner benchmark scaffolding; never launches serving/inference.

This deliberately leaves Luna's SDK manifest/journal contracts unchanged. Native
artifact retention is reused; a future shared collector protocol can unify the
small scheduling seam after the model binding and runtime gates are qualified.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol, cast

import verifiers.v1 as vf

from ..capture import canonical_json
from ..taskset import AutomationBenchTask
from .benchmark_models import (
    BenchmarkArtifact,
    BenchmarkAttempt,
    BenchmarkAttemptResult,
    BenchmarkLimits,
    BenchmarkManifest,
    ModelBenchmarkBinding,
    ModelBenchmarkResult,
    ModelSize,
    benchmark_attempts,
)
from .collector import (
    _retain_artifacts,
    _retain_host_state,
    _write_native,
    read_retained_artifacts,
    validate_episode,
)
from .eligibility import ReassessmentVerifier
from .frozen_verification import FrozenVerifierBinding
from .inventory import FrozenTask, TaskInventory, content_digest
from .reward_revision import RedesignRevision, capture_redesign_revision


class _AdmissionSession:
    """Private replay cache: fresh content checks retain the initial approval.

    Initial pool admission executes each independent replay once. Later starts
    reuse that result only while the exact approved content closure is unchanged.
    A new process always creates a new session and performs independent replay.
    """

    def __init__(self, manifest, revision, approved_bindings, reassessment_verifiers):
        self.revision = revision.model_copy(deep=True)
        self.bindings = approved_bindings
        self.verifiers = reassessment_verifiers
        self.binding_identity = {
            key: value.model_dump_json() for key, value in approved_bindings.items()
        }
        self.verifier_identity = self._verifier_identity()
        self.shared = {}
        self.selected = {}
        self.trees = {}
        for item in manifest.pool.tasks:
            proof = item.proof
            files = {
                (ref.path, ref.prefix_bytes): ref.digest
                for ref in (*proof.files, *proof.frozen_verification.files)
            }
            episode = vf.WireEpisode.model_validate_json(
                Path(
                    proof.files[[ref.name for ref in proof.files].index("episode")].path
                ).read_bytes()
            )
            episode_path = Path(next(ref.path for ref in proof.files if ref.name == "episode"))
            for trace in episode.traces:
                reference = trace.info.get("automationbench_collection_artifacts")
                if reference is not None:
                    files[(str(episode_path.parent / reference["path"]), None)] = reference[
                        "digest"
                    ]
            self.selected[proof.task_name] = files
            binding = proof.frozen_verification.binding
            self.shared[(binding.interpreter, None)] = binding.interpreter_digest
            self.shared[(binding.archive_path, None)] = binding.archive_digest
            manifest_path = next(ref.path for ref in proof.files if ref.name == "manifest")
            identity = json.loads(Path(manifest_path).read_bytes())["source_identity"]
            for name, package in identity["packages"].items():
                root = Path(binding.package_roots[name])
                self.trees[str(root)] = frozenset(
                    relative for relative in package["files"] if not relative.startswith("project/")
                )
                for relative, digest in package["files"].items():
                    if relative.startswith("project/"):
                        project = next(
                            parent
                            for parent in root.parents
                            if (parent / "pyproject.toml").exists()
                        )
                        path = project / relative.removeprefix("project/")
                    else:
                        path = root / relative
                    self.shared[(str(path), None)] = digest

    def _verifier_identity(self):
        return {
            key: (
                value.producer_id,
                value.producer_revision,
                value.rubric_revision,
                value.source_digest,
                id(value),
            )
            for key, value in self.verifiers.items()
        }

    @staticmethod
    def _check_files(files):
        for (path, prefix), digest in files.items():
            raw = Path(path).read_bytes()
            if prefix is not None:
                raw = raw[:prefix]
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("benchmark approved source closure changed")

    def check(self, task_name=None):
        if (
            self.binding_identity
            != {key: value.model_dump_json() for key, value in self.bindings.items()}
            or self.verifier_identity != self._verifier_identity()
        ):
            raise ValueError("benchmark independent approval registry changed")
        current = capture_redesign_revision(
            json.loads(self.revision.configuration_json), self.revision.native_source_digest
        )
        if current != self.revision:
            raise ValueError("benchmark accepted redesign source changed")
        self._check_files(self.shared)
        for root, expected in self.trees.items():
            observed = frozenset(
                str(path.relative_to(root))
                for path in Path(root).rglob("*")
                if path.is_file()
                and path.suffix in {".py", ".json"}
                and "__pycache__" not in path.parts
            )
            if observed != expected:
                raise ValueError("benchmark frozen source membership changed")
        selected = self.selected.values() if task_name is None else (self.selected[task_name],)
        for files in selected:
            self._check_files(files)


class AsyncBenchmarkRunner(Protocol):
    """Composition owns service/client lifetime, route qualification and budgets.

    Implementations must execute the supplied freshly instantiated native task,
    enforce the declared output/input/tool ceilings, expose live/discarded traces,
    and avoid internal retries or provider fallback. A matching declaration alone
    does not qualify those behaviors; real Qwen integration remains a release gate.
    """

    bindings: tuple[ModelBenchmarkBinding, ...]
    sampling_json: str
    limits: BenchmarkLimits

    async def run_attempt(
        self,
        task: AutomationBenchTask,
        attempt: BenchmarkAttempt,
        *,
        on_trace: Callable[[vf.Trace], None],
        on_discard: Callable[[vf.Trace], None],
    ) -> vf.Episode: ...


class NativeBenchmarkRunner:
    """Adapt already configured native environments/contexts; no lifecycle startup.

    The caller must qualify and enter these environments/clients before real use.
    This adapter neither verifies loaded remote weights nor adds a second serving
    system. It remains scaffold-only until real model/runtime/budget probes pass.
    """

    def __init__(
        self,
        *,
        bindings: tuple[ModelBenchmarkBinding, ...],
        contexts: Mapping[ModelSize, vf.ModelContext],
        environments: Mapping[ModelSize, vf.Env],
        sampling_json: str,
        limits: BenchmarkLimits,
    ) -> None:
        self.bindings = bindings
        self.sampling_json = sampling_json
        self.limits = limits
        self._contexts = dict(contexts)
        self._environments = dict(environments)
        sizes = {binding.size for binding in bindings}
        if (
            len(bindings) != 3
            or sizes != {"9b", "4b", "2b"}
            or set(contexts) != sizes
            or set(environments) != sizes
        ):
            raise ValueError("native benchmark requires all three supplied model contexts")
        for binding in bindings:
            if contexts[binding.size].model != binding.served_model_id:
                raise ValueError("native inference model differs from benchmark binding")

    async def run_attempt(
        self,
        task: AutomationBenchTask,
        attempt: BenchmarkAttempt,
        *,
        on_trace: Callable[[vf.Trace], None],
        on_discard: Callable[[vf.Trace], None],
    ) -> vf.Episode:
        binding = next(item for item in self.bindings if item.size == attempt.model_size)
        if binding.digest != attempt.binding_digest:
            raise ValueError("native benchmark binding changed")
        return await self._environments[attempt.model_size].run_episode(
            cast(vf.Task[Any, Any, Any], task),
            self._contexts[attempt.model_size],
            on_trace=on_trace,
            on_discard=on_discard,
        )


def _summary(episode: vf.Episode[Any, Any, Any], limits: BenchmarkLimits) -> dict[str, Any]:
    """Observed accounting only; missing call usage never becomes verified zero."""
    calls = [call for trace in episode.traces for call in trace.calls]
    usage = episode.usage
    usage_complete = bool(calls) and all(call.usage is not None for call in calls)
    output = usage.completion_tokens if usage is not None else None
    budget_status = (
        "observed_exceeded"
        if output is not None and output > limits.max_output_tokens
        else "observed_within"
        if usage_complete
        else "unavailable"
    )
    batches = [
        *episode.assessment_batches,
        *(batch for trace in episode.traces for batch in trace.assessment_batches),
    ]
    findings = {
        item.assessment_id: {
            "assessment_id": item.assessment_id,
            "subject_id": item.subject.subject_id,
            "signal_id": item.signal.signal_id,
            "revision": item.signal.revision,
            "status": item.status,
            "value": item.value,
        }
        for batch in batches
        for item in batch.assessments
    }
    return {
        "episode_ok": episode.ok,
        "usage_status": "complete" if usage_complete else "unavailable",
        "reported_usage": None if usage is None else usage.model_dump(mode="json"),
        "output_budget_status": budget_status,
        "output_accounting_contract": "native_reported_completion_tokens",
        "reported_output_lower_bound": output,
        "turns": sum(trace.num_turns for trace in episode.traces),
        "execution_observations": sum(
            event.phase == "dispatch"
            for trace in episode.traces
            for event in trace.tool_execution_events
        ),
        "execution_count_contract": "reported_dispatch_receipts_no_cross_origin_deduplication",
        "stop_conditions": [trace.stop_condition for trace in episode.traces],
        "error_types": [error.type for error in episode.errors]
        + [error.type for trace in episode.traces for error in trace.errors],
        "assessment_results": list(findings.values()),
        "assessment_batch_statuses": [batch.run.status for batch in batches],
        "real_qwen_runtime_qualified": False,
    }


def _retained_episode(
    task: FrozenTask,
    attempt: BenchmarkAttempt,
    directory: Path,
    limits: BenchmarkLimits,
    *,
    episode: vf.Episode | None,
    seen: list[vf.Trace],
    discarded: list[vf.Trace],
    failure: BaseException | None,
    interrupted: bool = False,
) -> BenchmarkAttemptResult:
    artifacts = []
    for index, trace in enumerate(discarded):
        _retain_host_state(trace)
        _retain_artifacts(trace, directory, f"discarded-{index}-artifacts.json")
        path = directory / f"discarded-{index}.json"
        artifacts.append(
            BenchmarkArtifact(path=str(path), digest=_write_native(path, trace.to_record()))
        )
    if episode is None:
        live = [trace for trace in seen if all(trace is not old for old in discarded)]
        identities = {trace.episode_id for trace in (*live, *discarded) if trace.episode_id}
        if len(identities) > 1:
            raise ValueError("benchmark live traces span multiple native episodes")
        episode = vf.Episode(
            task=vf.TraceTask(type="AutomationBenchTask", data=task.instantiate().data),
            traces=live,
        )
        if identities:
            episode.id = next(iter(identities))
        episode.errors.append(
            vf.Error(
                type=type(failure).__name__,
                message="benchmark attempt failed; native prefix retained",
            )
        )
    if (
        episode.task.type != "AutomationBenchTask"
        or episode.task.data.model_dump(mode="json") != task.data
    ):
        raise ValueError("benchmark runner returned a different native task")
    for index, trace in enumerate(episode.traces):
        _retain_host_state(trace)
        _retain_artifacts(trace, directory, f"trace-{index}-artifacts.json")
    episode.group = vf.GroupInfo(id=attempt.attempt_id)
    episode.run = vf.EvalRunInfo(id=attempt.manifest_digest, repetition_index=attempt.occurrence)
    path = directory / "episode.json"
    digest = _write_native(path, episode.to_record())
    if any(trace.episode_id != episode.id for trace in discarded):
        raise ValueError("discarded benchmark trace belongs to another occurrence")
    validate_episode(path, task)
    summary = _summary(episode, limits)
    errors = summary["error_types"]
    truncated = (
        isinstance(failure, TimeoutError)
        or summary["output_budget_status"] == "observed_exceeded"
        or any(
            stop in {"max_output_tokens", "max_turns", "max_tool_calls", "max_input_tokens"}
            for stop in summary["stop_conditions"]
        )
    )
    status = (
        "interrupted"
        if interrupted or isinstance(failure, asyncio.CancelledError)
        else "truncated"
        if truncated
        else "failed"
        if failure is not None or errors or not episode.ok
        else "completed"
    )
    error_type = (
        type(failure).__name__
        if failure is not None
        else (errors[0] if errors else "NativeEpisodeNotOk" if not episode.ok else None)
    )
    body = {
        "attempt": attempt.model_dump(mode="json"),
        "status": status,
        "episode_path": str(path),
        "episode_digest": digest,
        "error_type": error_type,
        "summary_json": canonical_json(summary),
        "discarded_traces": [artifact.model_dump(mode="json") for artifact in artifacts],
        "controller_receipt": _controller_receipt(
            directory,
            attempt,
            digest,
            "cancelled"
            if isinstance(failure, asyncio.CancelledError)
            else "missing_episode_at_recovery",
            error_type,
        ).model_dump(mode="json")
        if status == "interrupted"
        else None,
    }
    result = BenchmarkAttemptResult.model_validate({**body, "digest": content_digest(body)})
    _write_native(directory / "attempt-result.json", result.model_dump(mode="json"))
    return result


def _controller_receipt(directory, attempt, episode_digest, reason, error_type):
    path = directory / "controller-interruption.json"
    body = {
        "schema_version": 1,
        "attempt_id": attempt.attempt_id,
        "episode_digest": episode_digest,
        "reason": reason,
        "error_type": error_type,
    }
    if path.exists():
        raw = path.read_bytes()
        if raw != (canonical_json(body) + "\n").encode():
            raise ValueError("existing benchmark controller receipt changed")
        digest = hashlib.sha256(raw).hexdigest()
    else:
        digest = _write_native(path, body)
    return BenchmarkArtifact(path=str(path), digest=digest)


def _load_result(
    directory: Path,
    attempt: BenchmarkAttempt,
    task: FrozenTask,
    limits: BenchmarkLimits,
    *,
    retained: BenchmarkAttemptResult | None = None,
) -> BenchmarkAttemptResult:
    result = BenchmarkAttemptResult.model_validate_json(
        retained.model_dump_json()
        if retained is not None
        else (directory / "attempt-result.json").read_text()
    )
    if result.attempt != attempt:
        raise ValueError("retained benchmark result differs from expected occurrence")
    path = directory / "episode.json"
    if result.episode_path != str(path):
        raise ValueError("benchmark episode reference escaped its attempt directory")
    episode, digest = validate_episode(path, task)
    if (
        digest != result.episode_digest
        or episode.group is None
        or episode.group.id != attempt.attempt_id
        or episode.run is None
        or episode.run.type != "eval"
        or episode.run.id != attempt.manifest_digest
        or episode.run.repetition_index != attempt.occurrence
    ):
        raise ValueError("retained benchmark episode identity or digest changed")
    summary = _summary(episode, limits)
    if result.summary_json != canonical_json(summary):
        raise ValueError("retained benchmark summary differs from native evidence")
    truncated = (
        summary["output_budget_status"] == "observed_exceeded"
        or "TimeoutError" in summary["error_types"]
        or any(
            stop in {"max_output_tokens", "max_turns", "max_tool_calls", "max_input_tokens"}
            for stop in summary["stop_conditions"]
        )
    )
    expected_status = (
        "truncated"
        if truncated
        else "failed"
        if summary["error_types"] or not episode.ok
        else "completed"
    )
    if result.status != "interrupted" and result.status != expected_status:
        raise ValueError("retained benchmark status differs from native evidence")
    errors = summary["error_types"]
    expected_error = errors[0] if errors else "NativeEpisodeNotOk" if not episode.ok else None
    if result.status != "interrupted" and result.error_type != expected_error:
        raise ValueError("retained benchmark error differs from native evidence")
    if result.controller_receipt is not None:
        receipt = result.controller_receipt
        expected_path = directory / "controller-interruption.json"
        raw = expected_path.read_bytes()
        record = json.loads(raw)
        if (
            receipt.path != str(expected_path)
            or hashlib.sha256(raw).hexdigest() != receipt.digest
            or set(record)
            != {"schema_version", "attempt_id", "episode_digest", "reason", "error_type"}
            or record["schema_version"] != 1
            or record["attempt_id"] != attempt.attempt_id
            or record["episode_digest"] != digest
            or record["error_type"] != result.error_type
        ):
            raise ValueError("benchmark controller interruption receipt differs")
        if record["reason"] == "missing_result_at_recovery":
            justified = result.error_type == "UnfinishedPriorBenchmarkStart"
        elif record["reason"] == "missing_episode_at_recovery":
            justified = (
                result.error_type == "RuntimeError"
                and not episode.traces
                and errors == ["RuntimeError"]
            )
        elif record["reason"] == "cancelled":
            justified = result.error_type == "CancelledError" and "CancelledError" in errors
        else:
            justified = False
        if not justified:
            raise ValueError(
                "benchmark interruption is not justified by controller/native evidence"
            )
    for index, artifact in enumerate(result.discarded_traces):
        expected = directory / f"discarded-{index}.json"
        if (
            artifact.path != str(expected)
            or hashlib.sha256(expected.read_bytes()).hexdigest() != artifact.digest
        ):
            raise ValueError("discarded benchmark trace changed")
        trace = vf.WireTrace.model_validate_json(expected.read_bytes())
        if trace.task.data.model_dump(mode="json") != task.data:
            raise ValueError("discarded benchmark trace belongs to another task")
        if trace.episode_id != episode.id:
            raise ValueError("discarded benchmark trace belongs to another occurrence")
        read_retained_artifacts(directory, trace)
    return result


def _recover_interrupted(
    directory: Path, attempt: BenchmarkAttempt, task: FrozenTask, limits: BenchmarkLimits
) -> BenchmarkAttemptResult:
    """Retain a crash-window episode without rewriting already committed bytes."""
    path = directory / "episode.json"
    if not path.exists():
        return _retained_episode(
            task,
            attempt,
            directory,
            limits,
            episode=None,
            seen=[],
            discarded=[],
            failure=RuntimeError("unfinished prior benchmark start"),
            interrupted=True,
        )
    episode, digest = validate_episode(path, task)
    if (
        episode.group is None
        or episode.group.id != attempt.attempt_id
        or episode.run is None
        or episode.run.type != "eval"
        or episode.run.id != attempt.manifest_digest
        or episode.run.repetition_index != attempt.occurrence
    ):
        raise ValueError("unfinished benchmark episode identity changed")
    discarded = []
    indexed = {}
    for retained in directory.glob("discarded-*.json"):
        # Artifact envelopes are not independent native traces.
        if retained.name.endswith("-artifacts.json"):
            continue
        match = re.fullmatch(r"discarded-(0|[1-9][0-9]*)\.json", retained.name)
        if match is None:
            raise ValueError("unfinished discarded trace has no canonical ordinal")
        indexed[int(match[1])] = retained
    if set(indexed) != set(range(len(indexed))):
        raise ValueError("unfinished discarded trace ordinals are incomplete")
    for _, retained in sorted(indexed.items()):
        trace = vf.WireTrace.model_validate_json(retained.read_bytes())
        if trace.task.data.model_dump(mode="json") != task.data:
            raise ValueError("unfinished discarded trace belongs to another task")
        if trace.episode_id != episode.id:
            raise ValueError("unfinished discarded trace belongs to another occurrence")
        read_retained_artifacts(directory, trace)
        discarded.append(
            BenchmarkArtifact(
                path=str(retained),
                digest=hashlib.sha256(retained.read_bytes()).hexdigest(),
            )
        )
    receipt_path = directory / "controller-interruption.json"
    if receipt_path.exists():
        raw = receipt_path.read_bytes()
        receipt = BenchmarkArtifact(path=str(receipt_path), digest=hashlib.sha256(raw).hexdigest())
        error_type = json.loads(raw).get("error_type")
    else:
        error_type = "UnfinishedPriorBenchmarkStart"
        receipt = _controller_receipt(
            directory, attempt, digest, "missing_result_at_recovery", error_type
        )
    body = {
        "attempt": attempt.model_dump(mode="json"),
        "status": "interrupted",
        "episode_path": str(path),
        "episode_digest": digest,
        "error_type": error_type,
        "summary_json": canonical_json(_summary(episode, limits)),
        "discarded_traces": [item.model_dump(mode="json") for item in discarded],
        "controller_receipt": receipt.model_dump(mode="json"),
    }
    result = BenchmarkAttemptResult.model_validate({**body, "digest": content_digest(body)})
    _load_result(directory, attempt, task, limits, retained=result)
    _write_native(directory / "attempt-result.json", result.model_dump(mode="json"))
    return _load_result(directory, attempt, task, limits)


async def collect_benchmark(
    runner: AsyncBenchmarkRunner,
    inventory: TaskInventory,
    manifest: BenchmarkManifest,
    directory: Path,
    *,
    current_redesign: RedesignRevision,
    approved_bindings: dict[str, FrozenVerifierBinding],
    reassessment_verifiers: dict[str, ReassessmentVerifier],
) -> ModelBenchmarkResult:
    """One work-conserving queue; every persisted start consumes a logical attempt.

    Resume checks all retained artifacts. An unfinished prior start becomes explicit
    interrupted evidence; it is not resubmitted. No retries, rescoring, paid route
    selection, model startup or success-based stopping occurs here.
    """
    import fcntl

    manifest = BenchmarkManifest.model_validate_json(manifest.model_dump_json())
    admission = _AdmissionSession(
        manifest, current_redesign, approved_bindings, reassessment_verifiers
    )
    manifest.pool.validate_inventory(
        inventory,
        current_redesign,
        approved_bindings=approved_bindings,
        reassessment_verifiers=reassessment_verifiers,
    )
    admission.check()
    if (
        tuple(runner.bindings) != manifest.bindings
        or runner.limits != manifest.limits
        or runner.sampling_json != manifest.sampling_json
    ):
        raise ValueError("injected runner model, sampling or limits differ from benchmark")
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    ownership = (directory / "collection.lock").open("ab")
    try:
        fcntl.flock(ownership.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest_path = directory / "benchmark-manifest.json"
        if manifest_path.exists():
            retained = BenchmarkManifest.model_validate_json(manifest_path.read_text())
            if retained != manifest:
                raise ValueError("cannot resume a changed benchmark manifest")
        else:
            _write_native(manifest_path, manifest.model_dump(mode="json"))
        clock_path = directory / "collection-start.json"
        if clock_path.exists():
            started = json.loads(clock_path.read_text())
            if (
                set(started) != {"manifest_digest", "started_at_unix"}
                or started["manifest_digest"] != manifest.digest
                or type(started["started_at_unix"]) not in {int, float}
                or not math.isfinite(started["started_at_unix"])
                or started["started_at_unix"] <= 0
            ):
                raise ValueError("benchmark collection deadline identity changed")
        else:
            started = {"manifest_digest": manifest.digest, "started_at_unix": time.time()}
            _write_native(clock_path, started)
        remaining = max(
            0, started["started_at_unix"] + manifest.limits.max_elapsed_seconds - time.time()
        )
        deadline = time.monotonic() + remaining
        frozen = {task.task_name: task for task in inventory.tasks}
        results: dict[str, BenchmarkAttemptResult] = {}
        pending = []
        attempts = benchmark_attempts(manifest)
        for attempt in attempts:
            attempt_dir = directory / attempt.attempt_id
            start = attempt_dir / "attempt-start.json"
            if not start.exists():
                if (attempt_dir / "attempt-result.json").exists():
                    raise ValueError("benchmark result has no consumed start")
                pending.append(attempt)
                continue
            if BenchmarkAttempt.model_validate_json(start.read_text()) != attempt:
                raise ValueError("retained benchmark start changed")
            if (attempt_dir / "attempt-result.json").exists():
                result = _load_result(
                    attempt_dir, attempt, frozen[attempt.task_name], manifest.limits
                )
            else:
                result = _recover_interrupted(
                    attempt_dir,
                    attempt,
                    frozen[attempt.task_name],
                    manifest.limits,
                )
            results[attempt.attempt_id] = result

        async def run(attempt: BenchmarkAttempt) -> None:
            seen: list[vf.Trace] = []
            discarded: list[vf.Trace] = []
            episode = None
            failure = None
            try:
                async with asyncio.timeout(
                    min(
                        manifest.limits.attempt_timeout_seconds, max(0, deadline - time.monotonic())
                    )
                ):
                    episode = await runner.run_attempt(
                        frozen[attempt.task_name].instantiate(),
                        attempt,
                        on_trace=seen.append,
                        on_discard=discarded.append,
                    )
            except (Exception, asyncio.CancelledError) as exc:  # noqa: BLE001 - retain every failed logical attempt
                failure = exc
            result = _retained_episode(
                frozen[attempt.task_name],
                attempt,
                directory / attempt.attempt_id,
                manifest.limits,
                episode=episode,
                seen=seen,
                discarded=discarded,
                failure=failure,
            )
            results[attempt.attempt_id] = result
            if isinstance(failure, asyncio.CancelledError):
                raise failure

        active: set[asyncio.Task] = set()
        try:
            while pending or active:
                while (
                    pending
                    and len(active) < manifest.limits.max_concurrent
                    and time.monotonic() < deadline
                ):
                    attempt = pending.pop(0)
                    admission.check(attempt.task_name)
                    _write_native(
                        directory / attempt.attempt_id / "attempt-start.json",
                        attempt.model_dump(mode="json"),
                    )
                    active.add(asyncio.create_task(run(attempt)))
                if not active:
                    break
                finished, active = await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
                for completed in finished:
                    completed.result()
        finally:
            for live in active:
                live.cancel()
            if active:
                await asyncio.gather(*active, return_exceptions=True)
        admission.check()
        summary = ModelBenchmarkResult(
            manifest=manifest,
            attempts=tuple(
                results[item.attempt_id] for item in attempts if item.attempt_id in results
            ),
            pending_attempt_ids=tuple(
                item.attempt_id for item in attempts if item.attempt_id not in results
            ),
            collection_status="complete" if len(results) == len(attempts) else "incomplete",
        )
        summary_path = (
            directory / f"benchmark-result-{content_digest(summary.model_dump(mode='json'))}.json"
        )
        if not summary_path.exists():
            _write_native(summary_path, summary.model_dump(mode="json"))
        return summary
    finally:
        ownership.close()
