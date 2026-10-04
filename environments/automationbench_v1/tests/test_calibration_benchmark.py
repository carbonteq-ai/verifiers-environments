"""Synthetic protocol qualification only: no serving, credentials or inference."""

import asyncio
import json
import time
from collections import Counter

import pytest
import verifiers.v1 as vf
from test_calibration_eligibility import make_reference

from automationbench_v1.calibration.benchmark import _load_result, collect_benchmark
from automationbench_v1.calibration.benchmark_models import (
    BenchmarkAttemptResult,
    BenchmarkLimits,
    BenchmarkManifest,
    EligibleBenchmarkTask,
    ModelBenchmarkBinding,
    benchmark_attempts,
    plan_benchmark,
)
from automationbench_v1.calibration.collector import _write_native
from automationbench_v1.calibration.eligibility import build_eligibility_proof
from automationbench_v1.calibration.inventory import content_digest
from automationbench_v1.capture import canonical_json


def collect_kwargs(reference):
    return {
        "current_redesign": reference["revision"],
        "reassessment_verifiers": reference["kwargs"]["reassessment_verifiers"],
        "approved_bindings": {
            reference["kwargs"]["approved_binding"].digest: reference["kwargs"]["approved_binding"]
        },
    }


def make_benchmark(tmp_path):
    reference = make_reference(tmp_path / "reference")
    proof = build_eligibility_proof(**reference["kwargs"])
    bindings = tuple(
        ModelBenchmarkBinding.model_validate(
            {
                "size": size,
                "model_id": f"Qwen/Qwen3.5-{size.upper()}",
                "model_revision": "a" * 40,
                "served_model_id": f"fixture-{size}",
                "tokenizer_id": f"Qwen/Qwen3.5-{size.upper()}",
                "tokenizer_revision": "b" * 40,
                "tokenizer_digest": "c" * 64,
                "chat_template_digest": "d" * 64,
                "renderer_source_digest": "e" * 64,
                "runtime_id": "fixture-native-null",
                "runtime_revision": "f" * 40,
                "runtime_source_digest": "a" * 64,
                "route_identity": f"fixture://{size}",
                "precision": "bf16",
                "reasoning_mode": "enabled",
                "tools_policy_digest": "b" * 64,
                "native_configuration_json": canonical_json({"fixture": size}),
            }
        )
        for size in ("9b", "4b", "2b")
    )
    manifest = plan_benchmark(
        reference["inventory"],
        revision=reference["revision"],
        tasks=(EligibleBenchmarkTask(selection=reference["selection"], proof=proof),),
        bindings=bindings,
        sampling={"temperature": 0.5},
        limits=BenchmarkLimits(
            max_concurrent=2,
            max_total_attempts=9,
            max_elapsed_seconds=60,
            attempt_timeout_seconds=5,
            max_turns=16,
            max_output_tokens=16384,
            max_input_tokens_per_response=32768,
            max_tool_calls=64,
        ),
        reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
        approved_bindings={
            reference["kwargs"]["approved_binding"].digest: reference["kwargs"]["approved_binding"]
        },
    )
    return reference, manifest


class FixtureRunner:
    def __init__(self, manifest):
        self.bindings = manifest.bindings
        self.limits = manifest.limits
        self.sampling_json = manifest.sampling_json
        self.started = []
        self.active = 0
        self.peak = 0
        self.refilled = False

    async def run_attempt(self, task, attempt, *, on_trace, on_discard):
        self.started.append(attempt)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if attempt.model_size == "9b" and attempt.occurrence == 0:
                # A slow first slot remains occupied while the other is refilled.
                while len(self.started) < 3:
                    await asyncio.sleep(0)
                self.refilled = True
            else:
                await asyncio.sleep(0)
            if attempt.model_size == "4b" and attempt.occurrence == 0:
                raise RuntimeError("synthetic failure")
            episode = vf.Episode(task=vf.TraceTask(type="AutomationBenchTask", data=task.data))
            trace = vf.Trace(
                episode_id=episode.id,
                task=episode.task,
                agent=vf.AgentInfo(config=vf.AgentConfig()),
            )
            trace.ok = True
            trace.stop_condition = (
                "max_turns"
                if attempt.model_size == "2b" and attempt.occurrence == 0
                else "agent_completed"
            )
            episode.traces = [trace]
            episode.ok = True
            on_trace(trace)
            return episode
        finally:
            self.active -= 1


def test_all_three_bindings_same_pool_nine_consumed_attempts_and_refill(tmp_path):
    reference, manifest = make_benchmark(tmp_path)
    attempts = benchmark_attempts(manifest)
    assert len(attempts) == len({item.attempt_id for item in attempts}) == 9
    assert Counter(item.model_size for item in attempts) == {"9b": 3, "4b": 3, "2b": 3}
    assert len({item.task_digest for item in attempts}) == 1
    assert len({item.binding_digest for item in attempts}) == 3
    runner = FixtureRunner(manifest)
    destination = tmp_path / "benchmark"
    result = asyncio.run(
        collect_benchmark(
            runner,
            reference["inventory"],
            manifest,
            destination,
            current_redesign=reference["revision"],
            reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
            approved_bindings={
                reference["kwargs"]["approved_binding"].digest: reference["kwargs"][
                    "approved_binding"
                ]
            },
        )
    )
    assert runner.peak == 2 and runner.refilled
    assert result.collection_status == "complete" and result.qualification == "scaffold_only"
    assert Counter(item.status for item in result.attempts) == {
        "completed": 7,
        "failed": 1,
        "truncated": 1,
    }
    assert len(runner.started) == 9  # success and failure both consume exactly one occurrence
    resumed = asyncio.run(
        collect_benchmark(
            runner,
            reference["inventory"],
            manifest,
            destination,
            current_redesign=reference["revision"],
            reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
            approved_bindings={
                reference["kwargs"]["approved_binding"].digest: reference["kwargs"][
                    "approved_binding"
                ]
            },
        )
    )
    assert resumed == result and len(runner.started) == 9
    # A crash after committing native episode bytes but before the result marker
    # must preserve those bytes and consume the occurrence without another run.
    first = attempts[0]
    episode_path = destination / first.attempt_id / "episode.json"
    retained_bytes = episode_path.read_bytes()
    (destination / first.attempt_id / "attempt-result.json").unlink()
    recovered = asyncio.run(
        collect_benchmark(
            runner,
            reference["inventory"],
            manifest,
            destination,
            current_redesign=reference["revision"],
            reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
            approved_bindings={
                reference["kwargs"]["approved_binding"].digest: reference["kwargs"][
                    "approved_binding"
                ]
            },
        )
    )
    assert len(runner.started) == 9 and episode_path.read_bytes() == retained_bytes
    assert (
        next(item for item in recovered.attempts if item.attempt == first).status == "interrupted"
    )
    # Crash again after publishing the independent receipt but before the result.
    # Recovery must reuse the exact original receipt, not overwrite it.
    receipt_path = destination / first.attempt_id / "controller-interruption.json"
    receipt_bytes = receipt_path.read_bytes()
    (destination / first.attempt_id / "attempt-result.json").unlink()
    recovered_again = asyncio.run(
        collect_benchmark(
            runner, reference["inventory"], manifest, destination, **collect_kwargs(reference)
        )
    )
    assert recovered_again == recovered and receipt_path.read_bytes() == receipt_bytes
    episode_path.write_bytes(retained_bytes + b" ")
    with pytest.raises(ValueError, match="digest"):
        asyncio.run(
            collect_benchmark(
                runner,
                reference["inventory"],
                manifest,
                destination,
                current_redesign=reference["revision"],
                reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
                approved_bindings={
                    reference["kwargs"]["approved_binding"].digest: reference["kwargs"][
                        "approved_binding"
                    ]
                },
            )
        )


def test_pool_and_runner_changes_rejected_before_dispatch(tmp_path):
    reference, manifest = make_benchmark(tmp_path)
    selected = reference["selection"].model_copy(update={"task_name": "outside.pool"})
    with pytest.raises(ValueError, match="task"):
        plan_benchmark(
            reference["inventory"],
            revision=reference["revision"],
            tasks=(EligibleBenchmarkTask(selection=selected, proof=manifest.pool.tasks[0].proof),),
            bindings=manifest.bindings,
            sampling={"temperature": 0.5},
            limits=manifest.limits,
            reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
            approved_bindings={
                reference["kwargs"]["approved_binding"].digest: reference["kwargs"][
                    "approved_binding"
                ]
            },
        )
    runner = FixtureRunner(manifest)
    runner.sampling_json = canonical_json({"temperature": 1})
    with pytest.raises(ValueError, match="runner"):
        asyncio.run(
            collect_benchmark(
                runner,
                reference["inventory"],
                manifest,
                tmp_path / "benchmark",
                current_redesign=reference["revision"],
                reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
                approved_bindings={
                    reference["kwargs"]["approved_binding"].digest: reference["kwargs"][
                        "approved_binding"
                    ]
                },
            )
        )
    assert not runner.started
    with pytest.raises(ValueError, match="size"):
        ModelBenchmarkBinding.model_validate({**manifest.bindings[0].model_dump(), "size": "4b"})


def test_unfinished_start_consumed_without_retry(tmp_path):
    reference, manifest = make_benchmark(tmp_path)
    directory = (tmp_path / "benchmark").resolve()
    first = benchmark_attempts(manifest)[0]
    _write_native(
        directory / first.attempt_id / "attempt-start.json", first.model_dump(mode="json")
    )
    runner = FixtureRunner(manifest)
    result = asyncio.run(
        collect_benchmark(
            runner,
            reference["inventory"],
            manifest,
            directory,
            current_redesign=reference["revision"],
            reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
            approved_bindings={
                reference["kwargs"]["approved_binding"].digest: reference["kwargs"][
                    "approved_binding"
                ]
            },
        )
    )
    assert len(runner.started) == 8
    assert next(item for item in result.attempts if item.attempt == first).status == "interrupted"


def test_parsing_has_no_execution_authority_and_empty_registry_rejects(tmp_path, monkeypatch):
    from automationbench_v1.calibration import frozen_verification

    reference, manifest = make_benchmark(tmp_path)
    invoked = []
    monkeypatch.setattr(frozen_verification.subprocess, "run", lambda *a, **k: invoked.append(a))
    assert BenchmarkManifest.model_validate_json(manifest.model_dump_json()) == manifest
    with pytest.raises(ValueError, match="not independently approved"):
        manifest.pool.validate_inventory(
            reference["inventory"],
            reference["revision"],
            approved_bindings={},
            reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
        )
    assert not invoked


def test_resume_rejects_resealed_status_error_and_foreign_discard(tmp_path):
    reference, manifest = make_benchmark(tmp_path)
    destination = tmp_path / "benchmark"
    result = asyncio.run(
        collect_benchmark(
            FixtureRunner(manifest),
            reference["inventory"],
            manifest,
            destination,
            **collect_kwargs(reference),
        )
    )
    completed = next(item for item in result.attempts if item.status == "completed")
    directory = destination / completed.attempt.attempt_id
    task = next(
        item
        for item in reference["inventory"].tasks
        if item.task_name == completed.attempt.task_name
    )
    path = directory / "attempt-result.json"
    original = path.read_bytes()
    body = completed.model_dump(mode="json", exclude={"digest"})
    body["error_type"] = "InventedError"
    path.write_text(canonical_json({**body, "digest": content_digest(body)}))
    with pytest.raises(ValueError, match="error differs"):
        _load_result(directory, completed.attempt, task, manifest.limits)
    body["status"] = "interrupted"
    with pytest.raises(ValueError, match="controller receipt"):
        BenchmarkAttemptResult.model_validate({**body, "digest": content_digest(body)})
    path.write_bytes(original)
    episode = vf.WireEpisode.model_validate_json((directory / "episode.json").read_bytes())
    foreign = episode.traces[0].model_copy(deep=True)
    foreign.episode_id = "foreign-episode"
    foreign_path = directory / "discarded-0.json"
    digest = _write_native(foreign_path, foreign.model_dump(mode="json"))
    body = completed.model_dump(mode="json", exclude={"digest"})
    body["discarded_traces"] = [{"path": str(foreign_path), "digest": digest}]
    path.write_text(canonical_json({**body, "digest": content_digest(body)}))
    with pytest.raises(ValueError, match="another occurrence"):
        _load_result(directory, completed.attempt, task, manifest.limits)


def test_selected_proof_mutation_stops_refill_before_new_start(tmp_path):
    reference, manifest = make_benchmark(tmp_path)
    path = reference["kwargs"]["assessment_path"]
    original = path.read_bytes()

    class MutatingRunner(FixtureRunner):
        async def run_attempt(self, task, attempt, **kwargs):
            episode = await super().run_attempt(task, attempt, **kwargs)
            path.write_bytes(original + b" ")
            return episode

    runner = MutatingRunner(manifest)
    # Remove the fixture's special slow slot: it awaits a third start, which must
    # never occur once the first completed slot has changed the proof closure.
    runner.started.append(None)
    try:
        with pytest.raises(ValueError, match="source closure changed"):
            asyncio.run(
                collect_benchmark(
                    runner,
                    reference["inventory"],
                    manifest,
                    tmp_path / "benchmark",
                    **collect_kwargs(reference),
                )
            )
        assert len([item for item in runner.started if item is not None]) == 2
    finally:
        path.write_bytes(original)


def test_expired_resume_deadline_dispatches_nothing(tmp_path):
    reference, manifest = make_benchmark(tmp_path)
    directory = tmp_path / "benchmark"
    _write_native(directory / "benchmark-manifest.json", manifest.model_dump(mode="json"))
    _write_native(
        directory / "collection-start.json",
        {
            "manifest_digest": manifest.digest,
            "started_at_unix": time.time() - manifest.limits.max_elapsed_seconds - 1,
        },
    )
    runner = FixtureRunner(manifest)
    result = asyncio.run(
        collect_benchmark(
            runner, reference["inventory"], manifest, directory, **collect_kwargs(reference)
        )
    )
    assert not runner.started and len(result.pending_attempt_ids) == 9


def test_timeout_and_cancellation_preserve_consumed_attempts(tmp_path):
    reference, manifest = make_benchmark(tmp_path)
    limits = manifest.limits.model_copy(update={"attempt_timeout_seconds": 0.03})
    body = manifest.model_dump(mode="json", exclude={"digest"})
    body["limits"] = limits.model_dump(mode="json")
    manifest = BenchmarkManifest.model_validate({**body, "digest": content_digest(body)})

    class SlowRunner(FixtureRunner):
        async def run_attempt(self, task, attempt, **kwargs):
            if attempt.model_size == "9b" and attempt.occurrence == 0:
                self.started.append(attempt)
                episode = vf.Episode(task=vf.TraceTask(type="AutomationBenchTask", data=task.data))
                trace = vf.Trace(
                    episode_id=episode.id,
                    task=episode.task,
                    agent=vf.AgentInfo(config=vf.AgentConfig()),
                )
                kwargs["on_trace"](trace)
                await asyncio.sleep(1)
            return await super().run_attempt(task, attempt, **kwargs)

    runner = SlowRunner(manifest)
    directory = tmp_path / "timeout"
    result = asyncio.run(
        collect_benchmark(
            runner, reference["inventory"], manifest, directory, **collect_kwargs(reference)
        )
    )
    first = benchmark_attempts(manifest)[0]
    timed_out = next(item for item in result.attempts if item.attempt == first)
    assert timed_out.status == "truncated" and timed_out.error_type == "TimeoutError"
    assert len(result.attempts) == 9
    assert json.loads(timed_out.summary_json)["usage_status"] == "unavailable"

    class CancelRunner(FixtureRunner):
        async def run_attempt(self, task, attempt, **kwargs):
            self.started.append(attempt)
            raise asyncio.CancelledError()

    cancelled = CancelRunner(manifest)
    directory = tmp_path / "cancelled"
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            collect_benchmark(
                cancelled, reference["inventory"], manifest, directory, **collect_kwargs(reference)
            )
        )
    started_ids = {item.attempt_id for item in cancelled.started}
    # An interruption receipt may survive even when its final result does not.
    lost_marker = next(iter(started_ids))
    receipt_path = directory / lost_marker / "controller-interruption.json"
    receipt_bytes = receipt_path.read_bytes()
    (directory / lost_marker / "attempt-result.json").unlink()
    resumed = FixtureRunner(manifest)
    resumed.started.append(None)
    result = asyncio.run(
        collect_benchmark(
            resumed, reference["inventory"], manifest, directory, **collect_kwargs(reference)
        )
    )
    assert not started_ids.intersection(
        item.attempt_id for item in resumed.started if item is not None
    )
    assert all(
        item.status == "interrupted" and item.controller_receipt is not None
        for item in result.attempts
        if item.attempt.attempt_id in started_ids
    )
    assert receipt_path.read_bytes() == receipt_bytes
