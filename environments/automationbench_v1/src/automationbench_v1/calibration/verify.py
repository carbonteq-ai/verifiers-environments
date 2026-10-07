"""Provisional final-state verification; redesigned action guards remain separate."""

from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path

import pydantic

import automationbench

from ..capture import canonical_json
from ..scoring import score_world
from .collector import _read_outcome, read_retained_artifacts, validate_episode
from .inventory import FrozenTask, content_digest
from .journal import AttemptEvent
from .models import CalibrationManifest
from .sdk_runner import SIGNED_IN_ROUTE_IDENTITY


def scorer_fingerprint() -> str:
    """Current benchmark Python sources, adapter scorer and validation runtime."""
    root = Path(next(iter(automationbench.__path__)))
    sources = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*.py"))
    }
    sources["adapter/scoring.py"] = hashlib.sha256(
        Path(__file__).parents[1].joinpath("scoring.py").read_bytes()
    ).hexdigest()
    return content_digest(
        {
            "sources": sources,
            "python": platform.python_version(),
            "pydantic": pydantic.__version__,
        }
    )


def verify_retained(
    path: Path,
    task: FrozenTask,
    attempt: AttemptEvent,
    manifest: CalibrationManifest,
) -> dict:
    """Recompute current official outcomes from exact, retained native artifacts.

    This does not certify transient action guards, replay, model access, output
    accounting or the redesigned scorer. Those checks are required before Qwen
    eligibility. Artifact corruption raises; absent proof is explicit.
    """
    # Frozen models can still contain mutable nested dictionaries. Recheck the
    # manifest digest at the point of verification rather than trusting creation.
    manifest = CalibrationManifest.model_validate(manifest.model_dump())
    task = FrozenTask.model_validate(task.model_dump())
    if attempt.task_name != task.task_name or attempt.task_digest != task.digest:
        raise ValueError("attempt differs from supplied frozen task")
    if attempt.manifest_digest != manifest.digest or not any(
        item.task_name == task.task_name and item.task_digest == task.digest
        for item in manifest.tasks
    ):
        raise ValueError("attempt/task differ from selected manifest")
    if manifest.scorer_revision != scorer_fingerprint():
        raise ValueError("current scorer differs from frozen scorer identity")
    episode, digest = validate_episode(path, task, attempt)
    if digest != attempt.episode_digest or attempt.outcome_digest is None:
        raise ValueError("native artifact is not bound to a committed outcome")
    outcome, outcome_digest = _read_outcome(path.with_name("outcome.json"), attempt, task, digest)
    if outcome_digest != attempt.outcome_digest or any(
        outcome[key] != getattr(attempt, key)
        for key in ("status", "error_type", "failure_category")
    ):
        raise ValueError("committed outcome differs from journal")
    report = {
        "attempt_id": attempt.attempt_id,
        "task_digest": task.digest,
        "episode_digest": digest,
        "outcome_digest": outcome_digest,
        "scorer_revision": manifest.scorer_revision,
        "current_outcome_verified": False,
        "scope": "current_final_state_assertions",
        "qwen_eligibility": "pending_reward_redesign_and_budget_qualification",
        "reason": None,
    }
    if attempt.status != "retained" or not episode.ok or episode.errors or len(episode.traces) != 1:
        return {**report, "reason": "execution_not_completed_cleanly"}
    trace = episode.traces[0]
    if not trace.ok or trace.errors or trace.stop_condition not in (None, "agent_completed"):
        return {**report, "reason": "trace_failed_or_stopped"}
    sdk = trace.info.get("codex_sdk")
    if manifest.route_identity == SIGNED_IN_ROUTE_IDENTITY and not isinstance(sdk, dict):
        return {**report, "reason": "sdk_completion_unavailable"}
    if isinstance(sdk, dict):
        events = sdk.get("events")
        if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
            return {**report, "reason": "sdk_completion_unavailable"}
        finished = [event for event in events if event.get("kind") == "finished"]
        if (
            len(finished) != 1
            or finished[0].get("ok") is not True
            or finished[0].get("status") != "completed"
        ):
            return {**report, "reason": "sdk_completion_unavailable"}
        sealed = read_retained_artifacts(path.parent, trace).get("codex_sdk/events.json")
        if sealed is None:
            return {**report, "reason": "sealed_sdk_source_unavailable"}
        if canonical_json(json.loads(sealed)) != canonical_json(sdk):
            return {**report, "reason": "sdk_info_differs_from_sealed_source"}
    retained = trace.info.get("automationbench_collection_state")
    finalized = trace.info.get("automationbench")
    if (
        not isinstance(retained, dict)
        or retained.get("status") != "available"
        or not isinstance(finalized, dict)
    ):
        return {**report, "reason": "finalized_world_unavailable"}
    encoded = retained.get("world_json")
    if not isinstance(encoded, str) or hashlib.sha256(encoded.encode()).hexdigest() != retained.get(
        "digest"
    ):
        raise ValueError("retained world bytes differ from state digest")
    world = json.loads(encoded)
    if canonical_json(world) != encoded:
        raise ValueError("retained world is noncanonical")
    snapshot = score_world(
        world=world,
        initial_state=task.data["initial_state"],
        assertions=tuple(task.data["assertions"]),
    )
    if finalized.get("end_state") != snapshot.end_state or finalized.get("assertions") != list(
        snapshot.assertion_results
    ):
        raise ValueError("finalized state/scorer results differ from recomputed evidence")
    all_passed = len(snapshot.assertion_results) == len(task.data["assertions"]) and all(
        result.get("passed") is True for result in snapshot.assertion_results
    )
    # Preserve the official score separately; this conservative reference check
    # may decline a trace whose excluded assertion failed. It changes no reward.
    return {
        **report,
        "official_strict_score": snapshot.task_completed_correctly,
        "official_partial_credit": snapshot.partial_credit,
        "all_declared_assertions_passed": all_passed,
        "assertion_results": list(snapshot.assertion_results),
        "current_outcome_verified": snapshot.task_completed_correctly == 1 and all_passed,
        "reason": None
        if snapshot.task_completed_correctly == 1 and all_passed
        else "assertions_not_fully_satisfied",
    }
