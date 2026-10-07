from pathlib import Path

import pytest

from automationbench_v1.calibration.inventory import freeze_inventory
from automationbench_v1.calibration.journal import AttemptJournal
from automationbench_v1.calibration.models import CollectionLimits, TaskSelection, plan_collection
from automationbench_v1.taskset import AutomationBenchConfig


@pytest.fixture
def manifest():
    inventory = freeze_inventory(AutomationBenchConfig(), source_identity={"fixture": "journal"})
    task = inventory.tasks[0]
    return plan_collection(
        inventory,
        selections=(
            TaskSelection(
                task_name=task.task_name,
                task_digest=task.digest,
                family="fixture",
                split="development",
            ),
        ),
        route_identity="fixture",
        native_config={"harness": "codex"},
        scorer_revision="fixture",
        limits=CollectionLimits(
            max_concurrent=1,
            max_total_attempts=3,
            max_attempts_per_task=1,
            max_infrastructure_retries=2,
            max_elapsed_seconds=60,
            attempt_timeout_seconds=20,
            max_turns=4,
            max_output_tokens=100,
            cost_measurement="unavailable",
        ),
    )


def test_retry_links_logical_attempt_and_replays_all_failures(tmp_path: Path, manifest):
    path = tmp_path / "attempts.jsonl"
    name = manifest.tasks[0].task_name
    with AttemptJournal(path, manifest) as journal:
        first = journal.start(name)
        journal.finish(
            first, status="failed", error_type="TransportError", failure_category="infrastructure"
        )
        retry = journal.start(name, kind="infrastructure_retry", retry_of=first.attempt_id)
        assert retry.occurrence == 1 and retry.logical_occurrence == 0
        journal.finish(
            retry, status="retained", episode_path="episodes/native.json", episode_digest="a" * 64
        )
        with pytest.raises(ValueError, match="task attempt ceiling"):
            journal.start(name, kind="rescue")
        expected = list(journal.events)
    with AttemptJournal(path, manifest) as replay:
        assert replay.events == expected
        assert len(replay.latest) == 2
        assert {row.logical_occurrence for row in replay.latest.values()} == {0}


def test_exclusive_writer_and_unfinished_attempt_survive_restart(tmp_path: Path, manifest):
    path = tmp_path / "attempts.jsonl"
    with AttemptJournal(path, manifest) as first:
        begun = first.start(manifest.tasks[0].task_name)
        with pytest.raises(BlockingIOError):
            AttemptJournal(path, manifest)
    with AttemptJournal(path, manifest) as second:
        assert second.latest[begun.attempt_id].status == "started"
        with pytest.raises(ValueError, match="task attempt ceiling"):
            second.start(manifest.tasks[0].task_name)
        second.finish(
            begun, status="interrupted", error_type="ProcessRestart", failure_category="cancelled"
        )


def test_symlink_alias_cannot_acquire_a_second_writer(tmp_path: Path, manifest):
    path = tmp_path / "attempts.jsonl"
    with AttemptJournal(path, manifest) as writer:
        writer.start(manifest.tasks[0].task_name)
        alias = tmp_path / "alias.jsonl"
        alias.symlink_to(path)
        with pytest.raises(BlockingIOError):
            AttemptJournal(alias, manifest)


def test_started_events_outside_deadline_are_rejected_on_append(tmp_path: Path, manifest):
    from automationbench_v1.calibration.inventory import content_digest

    with AttemptJournal(tmp_path / "attempts.jsonl", manifest) as journal:
        start = journal.start(manifest.tasks[0].task_name)
        journal.finish(
            start, status="failed", error_type="TransportError", failure_category="infrastructure"
        )
        fields = start.model_dump(exclude={"sequence", "manifest_digest"})
        fields.update(
            occurrence=1,
            kind="infrastructure_retry",
            retry_of=start.attempt_id,
            recorded_at_unix=start.recorded_at_unix + 61,
            attempt_id=content_digest(
                {"manifest": manifest.digest, "task": start.task_digest, "occurrence": 1}
            ),
        )
        with pytest.raises(ValueError, match="recorded collection deadline"):
            journal.append(**fields)


def test_fsync_failure_poisons_writer_until_replay(tmp_path: Path, manifest, monkeypatch):
    from automationbench_v1.calibration import journal as module

    path = tmp_path / "attempts.jsonl"
    with AttemptJournal(path, manifest) as journal:
        with monkeypatch.context() as patch:

            def failed_fsync(fd):
                raise OSError("disk fixture")

            patch.setattr(module.os, "fsync", failed_fsync)
            with pytest.raises(OSError, match="disk fixture"):
                journal.start(manifest.tasks[0].task_name)
        assert not journal.events
        with pytest.raises(RuntimeError, match="reopened"):
            journal.start(manifest.tasks[0].task_name)
    # A full line may have reached disk despite fsync failure; do not retry it blindly.
    with AttemptJournal(path, manifest) as replay:
        assert len(replay.events) == 1 and replay.events[0].status == "started"


def test_partial_tail_and_elapsed_deadline_are_not_reset(tmp_path: Path, manifest, monkeypatch):
    from automationbench_v1.calibration import journal as module

    path = tmp_path / "attempts.jsonl"
    with AttemptJournal(path, manifest) as journal:
        start = journal.start(manifest.tasks[0].task_name)
        journal.finish(
            start, status="failed", error_type="TransportError", failure_category="infrastructure"
        )
    monkeypatch.setattr(module.time, "time", lambda: start.recorded_at_unix + 61)
    with (
        AttemptJournal(path, manifest) as replay,
        pytest.raises(ValueError, match="elapsed-time ceiling"),
    ):
        replay.start(
            manifest.tasks[0].task_name, kind="infrastructure_retry", retry_of=start.attempt_id
        )
    with path.open("ab") as stream:
        stream.write(b'{"partial":')
    with pytest.raises(ValueError, match="incomplete journal tail"):
        AttemptJournal(path, manifest)
