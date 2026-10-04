"""Durable attempt accounting pointing to native episode files, not copied traces."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .inventory import content_digest
from .models import CalibrationManifest


class AttemptEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sequence: int = Field(ge=0, strict=True)
    recorded_at_unix: float = Field(default_factory=time.time, ge=0, allow_inf_nan=False)
    manifest_digest: str
    attempt_id: str
    task_name: str
    task_digest: str
    occurrence: int = Field(ge=0, strict=True)
    logical_occurrence: int = Field(ge=0, strict=True)
    retry_of: str | None = None
    kind: Literal["initial", "confirmation", "rescue", "infrastructure_retry"]
    status: Literal["started", "retained", "failed", "interrupted"]
    episode_path: str | None = Field(default=None, min_length=1)
    episode_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    outcome_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    error_type: str | None = None
    failure_category: (
        Literal["infrastructure", "policy", "scorer", "cancelled", "unknown"] | None
    ) = None

    @model_validator(mode="after")
    def check_result(self) -> AttemptEvent:
        expected = content_digest(
            {
                "manifest": self.manifest_digest,
                "task": self.task_digest,
                "occurrence": self.occurrence,
            }
        )
        if self.attempt_id != expected:
            raise ValueError("attempt identity differs from occurrence")
        if (self.episode_path is None) != (self.episode_digest is None):
            raise ValueError("native episode path and digest must be supplied together")
        if self.outcome_digest is not None and self.episode_path is None:
            raise ValueError("outcome digest requires its native episode artifact")
        if self.status == "retained" and self.episode_path is None:
            raise ValueError("retained attempt requires a native episode artifact")
        if self.status in ("failed", "interrupted") and (
            not self.error_type or self.failure_category is None
        ):
            raise ValueError("failed attempt requires an explained disposition")
        if (self.kind == "infrastructure_retry") != (self.retry_of is not None):
            raise ValueError("infrastructure retry requires a parent execution")
        if self.status == "started" and (
            self.episode_path is not None or self.error_type is not None
        ):
            raise ValueError("started attempt cannot contain an outcome")
        return self


class AttemptJournal:
    """One collector owns writes; replay rejects conflicting or incomplete lines.

    A POSIX advisory lock enforces exclusive ownership for this journal's lifetime.
    The async collector writes on its event-loop thread. This is not a concurrent
    multi-process writer API.
    A started occurrence without a terminal event remains interrupted evidence;
    it is never implicitly treated as a task that was not tried.
    """

    def __init__(self, path: Path, manifest: CalibrationManifest):
        import fcntl

        path = path.resolve()
        self.path = path
        self.manifest = CalibrationManifest.model_validate(manifest.model_dump())
        self.events: list[AttemptEvent] = []
        self.latest: dict[str, AttemptEvent] = {}
        self.poisoned = False
        path.parent.mkdir(parents=True, exist_ok=True)
        # Stable lock inode; never unlink while another process could be waiting.
        self._ownership = path.with_suffix(path.suffix + ".lock").open("ab")
        try:
            fcntl.flock(self._ownership.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            if path.exists():
                raw = path.read_bytes()
                if raw and not raw.endswith(b"\n"):
                    raise ValueError(
                        "incomplete journal tail; preserve and reconcile before resume"
                    )
                for line in raw.splitlines():
                    self._accept(AttemptEvent.model_validate_json(line))
            remaining = self.manifest.limits.max_elapsed_seconds
            if self.events:
                remaining = max(0, self.events[0].recorded_at_unix + remaining - time.time())
            self._monotonic_deadline = time.monotonic() + remaining
        except BaseException:
            self._ownership.close()
            raise

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        self._ownership.close()

    def _validate_next(self, event: AttemptEvent) -> None:
        if event.manifest_digest != self.manifest.digest or event.sequence != len(self.events):
            raise ValueError("journal identity or sequence mismatch")
        tasks = {task.task_name: task for task in self.manifest.tasks}
        selected = tasks.get(event.task_name)
        if selected is None or selected.task_digest != event.task_digest:
            raise ValueError("journal task differs from collection")
        previous = self.latest.get(event.attempt_id)
        if previous is None:
            if event.status != "started":
                raise ValueError("attempt has no start event")
            if self.events and not (
                max(row.recorded_at_unix for row in self.events)
                <= event.recorded_at_unix
                < self.events[0].recorded_at_unix + self.manifest.limits.max_elapsed_seconds
            ):
                raise ValueError("started occurrence is outside the recorded collection deadline")
            started = [row for row in self.latest.values() if row.task_name == event.task_name]
            if event.occurrence != len(started):
                raise ValueError("task occurrence is not contiguous")
            limits = self.manifest.limits
            if len(self.latest) >= limits.max_total_attempts:
                raise ValueError("total attempt ceiling exceeded")
            ordinary = sum(row.kind != "infrastructure_retry" for row in started)
            if event.kind != "infrastructure_retry" and ordinary >= limits.max_attempts_per_task:
                raise ValueError("task attempt ceiling exceeded")
            retries = sum(row.kind == "infrastructure_retry" for row in self.latest.values())
            if (
                event.kind == "infrastructure_retry"
                and retries >= limits.max_infrastructure_retries
            ):
                raise ValueError("infrastructure retry ceiling exceeded")
            if event.kind == "infrastructure_retry":
                parent = self.latest.get(event.retry_of or "")
                if (
                    parent is None
                    or parent.task_name != event.task_name
                    or parent.status != "failed"
                    or parent.failure_category != "infrastructure"
                    or event.logical_occurrence != parent.logical_occurrence
                    or any(row.retry_of == event.retry_of for row in self.latest.values())
                ):
                    raise ValueError("retry parent is not an eligible infrastructure failure")
            elif event.logical_occurrence != ordinary:
                raise ValueError("logical task occurrence is not contiguous")
        elif (
            previous.status != "started"
            or event.status == "started"
            or (
                previous.task_name,
                previous.task_digest,
                previous.occurrence,
                previous.kind,
                previous.logical_occurrence,
                previous.retry_of,
            )
            != (
                event.task_name,
                event.task_digest,
                event.occurrence,
                event.kind,
                event.logical_occurrence,
                event.retry_of,
            )
        ):
            raise ValueError("invalid or duplicate attempt transition")

    def _accept(self, event: AttemptEvent) -> None:
        self._validate_next(event)
        self.events.append(event)
        self.latest[event.attempt_id] = event

    def append(self, **fields) -> AttemptEvent:
        if self.poisoned or self._ownership.closed:
            raise RuntimeError("journal must be reopened and reconciled before writing")
        event = AttemptEvent(
            sequence=len(self.events), manifest_digest=self.manifest.digest, **fields
        )
        # Validate before writing; update in-memory accounting only after fsync.
        self._validate_next(event)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            new_file = not self.path.exists()
            with self.path.open("ab") as stream:
                stream.write((event.model_dump_json() + "\n").encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            if new_file:
                directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        except BaseException:
            self.poisoned = True
            raise
        self._accept(event)
        return event

    def start(
        self, task_name: str, *, kind: str = "initial", retry_of: str | None = None
    ) -> AttemptEvent:
        if time.monotonic() >= self._monotonic_deadline or (
            self.events
            and time.time()
            >= (self.events[0].recorded_at_unix + self.manifest.limits.max_elapsed_seconds)
        ):
            raise ValueError("collection elapsed-time ceiling reached")
        selected = next(task for task in self.manifest.tasks if task.task_name == task_name)
        occurrence = sum(row.task_name == task_name for row in self.latest.values())
        logical_occurrence = (
            self.latest[retry_of].logical_occurrence
            if retry_of in self.latest
            else sum(
                row.task_name == task_name and row.kind != "infrastructure_retry"
                for row in self.latest.values()
            )
        )
        attempt_id = content_digest(
            {
                "manifest": self.manifest.digest,
                "task": selected.task_digest,
                "occurrence": occurrence,
            }
        )
        return self.append(
            attempt_id=attempt_id,
            task_name=task_name,
            task_digest=selected.task_digest,
            occurrence=occurrence,
            logical_occurrence=logical_occurrence,
            retry_of=retry_of,
            kind=kind,
            status="started",
        )

    def finish(self, started: AttemptEvent, *, status: str, **outcome) -> AttemptEvent:
        fields = started.model_dump(
            exclude={"sequence", "manifest_digest", "status", "recorded_at_unix"}
        )
        return self.append(**{**fields, **outcome, "status": status})
