"""Bounded native episode collection with artifact-first crash reconciliation.

Composition owns the serving context and guarded inference client. This module
does not resolve credentials, start services, or declare a paid route ready.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, cast

import verifiers.v1 as vf

from .budgets import retain_sdk_budget
from .inventory import FrozenTask, TaskInventory
from .journal import AttemptEvent, AttemptJournal
from .models import CalibrationManifest


def _write_native(path: Path, record: dict) -> str:
    """Publish complete bytes exclusively; a crash never leaves a partial final file."""
    from ..capture import canonical_json

    raw = (canonical_json(record) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # Never overwrite an existing retained artifact.
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return hashlib.sha256(raw).hexdigest()


def validate_episode(
    path: Path, task: FrozenTask, attempt: AttemptEvent | None = None
) -> tuple[vf.WireEpisode, str]:
    raw = path.read_bytes()
    episode = vf.WireEpisode.model_validate_json(raw)
    if episode.task.type != "AutomationBenchTask" or (
        episode.task.data.model_dump(mode="json") != task.data
    ):
        raise ValueError("native episode does not contain the exact frozen task")
    for trace in episode.traces:
        if trace.episode_id != episode.id or (trace.task.data.model_dump(mode="json") != task.data):
            raise ValueError("native trace task or episode identity differs")
        read_retained_artifacts(path.parent, trace)
    if attempt is not None and (
        episode.group is None
        or episode.group.id != attempt.attempt_id
        or episode.run is None
        or episode.run.type != "eval"
        or episode.run.id != attempt.manifest_digest
        or episode.run.repetition_index != attempt.occurrence
    ):
        raise ValueError("native episode is not bound to its collection attempt")
    return episode, hashlib.sha256(raw).hexdigest()


def _retain_artifacts(trace: vf.Trace, directory: Path, name: str) -> None:
    """Retain excluded native state artifacts as bytes, without interpreting names."""
    if not trace.state.artifacts:
        return
    values = {
        key: {
            "sha256": None if value is None else hashlib.sha256(value).hexdigest(),
            "bytes_base64": None if value is None else base64.b64encode(value).decode("ascii"),
        }
        for key, value in trace.state.artifacts.items()
    }
    digest = _write_native(directory / name, {"trace_id": trace.id, "artifacts": values})
    trace.info["automationbench_collection_artifacts"] = {"path": name, "digest": digest}


def read_retained_artifacts(directory: Path, trace: vf.WireTrace) -> dict[str, bytes | None]:
    """Validate a retained envelope; absent legacy envelopes stay unavailable."""
    reference = trace.info.get("automationbench_collection_artifacts")
    if reference is None:
        return {}
    if not isinstance(reference, dict) or set(reference) != {"path", "digest"}:
        raise ValueError("invalid native artifact reference")
    name = reference["path"]
    if (
        not isinstance(name, str)
        or re.fullmatch(r"(?:trace|discarded)-\d+-artifacts\.json", name) is None
    ):
        raise ValueError("invalid native artifact envelope path")
    raw = (directory / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference["digest"]:
        raise ValueError("native artifact envelope digest mismatch")
    record = json.loads(raw)
    if set(record) != {"trace_id", "artifacts"} or record["trace_id"] != trace.id:
        raise ValueError("native artifact envelope differs from trace")
    values = record["artifacts"]
    if not isinstance(values, dict):
        raise TypeError("native artifact envelope requires named values")
    decoded = {}
    for key, value in values.items():
        if not isinstance(value, dict) or set(value) != {"sha256", "bytes_base64"}:
            raise ValueError("invalid native artifact value")
        encoded = value["bytes_base64"]
        data = None if encoded is None else base64.b64decode(encoded, validate=True)
        if (None if data is None else hashlib.sha256(data).hexdigest()) != value["sha256"]:
            raise ValueError("native artifact byte digest mismatch")
        decoded[key] = data
    return decoded


def _retain_host_state(trace: vf.Trace) -> None:
    """Capture host-observed state without scorer hooks or a causal/order claim."""
    from ..capture import canonical_json
    from ..tools import AutomationBenchState

    state = trace.state
    if isinstance(state, AutomationBenchState):
        encoded = canonical_json(state.world)
        trace.info["automationbench_collection_state"] = {
            "status": "available",
            "world_json": encoded,
            "digest": hashlib.sha256(encoded.encode()).hexdigest(),
            "state_revision": trace.tool_state_revision,
            "scope": "host state observed at collector retention",
        }
    else:
        trace.info["automationbench_collection_state"] = {
            "status": "unavailable",
            "reason": "automationbench_host_state_absent",
        }


def _read_outcome(
    path: Path, event: AttemptEvent, task: FrozenTask, digest: str
) -> tuple[dict, str]:
    raw = path.read_bytes()
    saved = json.loads(raw)
    if set(saved) != {
        "attempt_id",
        "manifest_digest",
        "episode_digest",
        "status",
        "error_type",
        "failure_category",
        "discarded_artifacts",
    } or (
        saved["attempt_id"] != event.attempt_id
        or saved["manifest_digest"] != event.manifest_digest
        or saved["episode_digest"] != digest
    ):
        raise ValueError("saved outcome does not match its native artifact")
    artifacts = saved["discarded_artifacts"]
    if not isinstance(artifacts, list):
        raise TypeError("discarded native artifact inventory is invalid")
    for index, item in enumerate(artifacts):
        if set(item) != {"path", "digest", "trace_id"} or item["path"] != f"discarded-{index}.json":
            raise ValueError("discarded native artifact identity is invalid")
        encoded = path.with_name(item["path"]).read_bytes()
        trace = vf.WireTrace.model_validate_json(encoded)
        read_retained_artifacts(path.parent, trace)
        if (
            hashlib.sha256(encoded).hexdigest() != item["digest"]
            or trace.id != item["trace_id"]
            or trace.task.data.model_dump(mode="json") != task.data
        ):
            raise ValueError("discarded native trace bytes or task identity changed")
    return saved, hashlib.sha256(raw).hexdigest()


def reconcile_attempts(journal: AttemptJournal, inventory: TaskInventory, directory: Path) -> None:
    """Recover saved outcomes; preserve an interrupted start instead of replacing it."""
    tasks = {task.task_name: task for task in inventory.tasks}
    for event in tuple(journal.latest.values()):
        path = directory / event.attempt_id / "episode.json"
        if event.episode_path is not None:
            recorded = Path(event.episode_path)
            if recorded.resolve() != path.resolve():
                raise ValueError("journal episode path differs from its attempt directory")
            _, digest = validate_episode(path, tasks[event.task_name], event)
            if digest != event.episode_digest:
                raise ValueError("retained native episode bytes changed")
            if event.outcome_digest is not None:
                saved, outcome_digest = _read_outcome(
                    path.with_name("outcome.json"),
                    event,
                    tasks[event.task_name],
                    digest,
                )
                if outcome_digest != event.outcome_digest or any(
                    saved[key] != getattr(event, key)
                    for key in ("status", "error_type", "failure_category")
                ):
                    raise ValueError("retained outcome bytes or disposition changed")
        elif event.status == "started":
            if path.exists():
                _, digest = validate_episode(path, tasks[event.task_name], event)
                outcome_path = path.with_name("outcome.json")
                outcome = {
                    "status": "interrupted",
                    "error_type": "UncommittedOutcome",
                    "failure_category": "unknown",
                }
                outcome_digest = None
                if outcome_path.exists():
                    saved, outcome_digest = _read_outcome(
                        outcome_path,
                        event,
                        tasks[event.task_name],
                        digest,
                    )
                    outcome = {key: saved[key] for key in outcome}
                journal.finish(
                    event,
                    **outcome,
                    episode_path=str(path.resolve()),
                    episode_digest=digest,
                    outcome_digest=outcome_digest,
                )
            else:
                journal.finish(
                    event,
                    status="interrupted",
                    error_type="ProcessRestart",
                    failure_category="cancelled",
                )


async def collect(
    env: vf.Env,
    ctx: vf.ModelContext,
    inventory: TaskInventory,
    manifest: CalibrationManifest,
    directory: Path,
    *,
    attempts_per_task: int = 1,
    stop_on_execution_error: bool = False,
) -> tuple[AttemptEvent, ...]:
    """Refill free slots immediately; each durable start consumes one attempt.

    ``attempts_per_task`` is a total ordinary-attempt target including prior starts.
    Infrastructure retry and adaptive rescue decisions require explicit scheduling;
    collection never silently resubmits a failed or interrupted attempt.
    Native serving/client lifetime is supplied by the caller.
    """
    manifest.validate_inventory(inventory)
    if ctx.model != manifest.provider_model_id:
        raise ValueError("inference model differs from collection manifest")
    if isinstance(attempts_per_task, bool) or not (
        1 <= attempts_per_task <= manifest.limits.max_attempts_per_task
    ):
        raise ValueError("ordinary attempt target exceeds manifest")
    directory = directory.resolve()
    tasks = {task.task_name: task for task in inventory.tasks}
    with AttemptJournal(directory / "attempts.jsonl", manifest) as journal:
        reconcile_attempts(journal, inventory, directory)
        remaining = manifest.limits.max_elapsed_seconds
        if journal.events:
            remaining = max(0, journal.events[0].recorded_at_unix + remaining - time.time())
        deadline = time.monotonic() + remaining
        pending = []
        for selected in manifest.tasks:
            prior = sum(
                event.task_name == selected.task_name and event.kind != "infrastructure_retry"
                for event in journal.latest.values()
            )
            pending.extend([selected.task_name] * max(0, attempts_per_task - prior))

        async def run(started: AttemptEvent) -> bool:
            task = tasks[started.task_name]
            seen: list[vf.Trace] = []
            discarded: list[vf.Trace] = []
            episode = None
            failure: BaseException | None = None
            try:
                duration = min(
                    manifest.limits.attempt_timeout_seconds,
                    max(0, deadline - time.monotonic()),
                )
                async with asyncio.timeout(duration):
                    episode = await env.run_episode(
                        cast(vf.Task[Any, Any, Any], task.instantiate()),
                        ctx,
                        on_trace=seen.append,
                        on_discard=discarded.append,
                    )
            except (Exception, asyncio.CancelledError) as exc:  # noqa: BLE001 -- retain all failed executions
                failure = exc
            attempt_directory = directory / started.attempt_id
            # Retain native discarded traces independently; do not insert them into
            # a completed episode or erase internal retry consumption.
            discarded_artifacts = []
            for index, trace in enumerate(discarded):
                retain_sdk_budget(trace.info, manifest.limits.max_output_tokens)
                _retain_host_state(trace)
                _retain_artifacts(trace, attempt_directory, f"discarded-{index}-artifacts.json")
                name = f"discarded-{index}.json"
                trace_digest = _write_native(attempt_directory / name, trace.to_record())
                discarded_artifacts.append(
                    {"path": name, "digest": trace_digest, "trace_id": trace.id}
                )
            if episode is None:
                active = [trace for trace in seen if all(trace is not old for old in discarded)]
                identities = {trace.episode_id for trace in active if trace.episode_id}
                if len(identities) > 1:
                    raise ValueError("live traces span more than one native episode")
                episode = vf.Episode(
                    id=next(iter(identities), uuid.uuid4().hex),
                    task=vf.TraceTask(type="AutomationBenchTask", data=task.instantiate().data),
                    traces=active,
                )
                episode.errors.append(vf.Error(type=type(failure).__name__, message=str(failure)))
            for index, trace in enumerate(episode.traces):
                retain_sdk_budget(trace.info, manifest.limits.max_output_tokens)
                _retain_host_state(trace)
                _retain_artifacts(trace, attempt_directory, f"trace-{index}-artifacts.json")
            episode.group = vf.GroupInfo(id=started.attempt_id)
            episode.run = vf.EvalRunInfo(
                id=started.manifest_digest,
                repetition_index=started.occurrence,
            )
            path = attempt_directory / "episode.json"
            digest = _write_native(path, episode.to_record())
            _, checked_digest = validate_episode(path, task, started)
            if checked_digest != digest:
                raise ValueError("native episode changed during retention")
            outcome = {
                "status": "retained"
                if failure is None
                else ("interrupted" if isinstance(failure, asyncio.CancelledError) else "failed"),
                "error_type": type(failure).__name__ if failure is not None else None,
                "failure_category": None
                if failure is None
                else ("cancelled" if isinstance(failure, asyncio.CancelledError) else "unknown"),
            }
            outcome_digest = _write_native(
                attempt_directory / "outcome.json",
                {
                    "attempt_id": started.attempt_id,
                    "manifest_digest": started.manifest_digest,
                    "episode_digest": digest,
                    "discarded_artifacts": discarded_artifacts,
                    **outcome,
                },
            )
            journal.finish(
                started,
                **outcome,
                episode_path=str(path),
                episode_digest=digest,
                outcome_digest=outcome_digest,
            )
            if isinstance(failure, asyncio.CancelledError):
                raise failure
            return (
                failure is not None
                or bool(episode.errors)
                or any(
                    trace.errors
                    or (
                        not trace.ok
                        and trace.stop_condition not in {"max_output_tokens", "max_turns"}
                    )
                    for trace in episode.traces
                )
            )

        active: set[asyncio.Task] = set()
        try:
            while pending or active:
                while pending and len(active) < manifest.limits.max_concurrent:
                    if time.monotonic() >= deadline or (
                        len(journal.latest) >= manifest.limits.max_total_attempts
                    ):
                        pending.clear()
                        break
                    started = journal.start(pending.pop(0))
                    active.add(asyncio.create_task(run(started)))
                if active:
                    completed, active = await asyncio.wait(
                        active, return_when=asyncio.FIRST_COMPLETED
                    )
                    for finished in completed:
                        if finished.result() and stop_on_execution_error:
                            # Drain already-started work, but never refill after an
                            # authentication/runtime/transport failure. Task scores
                            # and failed domain tool payloads do not trigger this.
                            pending.clear()
        finally:
            for running in active:
                running.cancel()
            if active:
                await asyncio.gather(*active, return_exceptions=True)
        return tuple(journal.latest.values())
