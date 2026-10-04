"""Native artifact recovery and bounded slot refill without provider inference."""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
import verifiers.v1 as vf

from automationbench_v1.calibration.collector import (
    _write_native,
    collect,
    read_retained_artifacts,
    reconcile_attempts,
    validate_episode,
)
from automationbench_v1.calibration.evidence import inspect_capture
from automationbench_v1.calibration.inventory import content_digest, freeze_inventory
from automationbench_v1.calibration.journal import AttemptJournal
from automationbench_v1.calibration.models import CollectionLimits, TaskSelection, plan_collection
from automationbench_v1.calibration.verify import scorer_fingerprint, verify_retained
from automationbench_v1.taskset import AutomationBenchConfig


@pytest.mark.parametrize(
    "case",
    [
        "solved",
        "unsolved",
        "failed_execution",
        "missing_finalization",
        "malformed_sdk",
        "excluded_failure",
        "sdk_solved",
        "sdk_seal_mismatch",
        "sdk_seal_missing",
        "sdk_type_mutation",
        "sdk_absent_info",
        "normal_completion",
        "budget_stop",
    ],
)
def test_offline_verification_binds_current_scorer_and_declines_incomplete_proof(
    tmp_path, inputs, case
):
    from automationbench.schema.world import WorldState
    from automationbench_v1.scoring import score_world
    from automationbench_v1.tools import AutomationBenchState

    inventory, original, ctx = inputs
    if case == "excluded_failure":
        inventory_body = inventory.model_dump(mode="json", exclude={"digest"})
        task_body = inventory_body["tasks"][0]
        excluded = {**task_body["data"]["assertions"][0], "value": "wrong", "excluded": True}
        task_body["data"]["assertions"].append(excluded)
        task_body["digest"] = content_digest(
            {"data": task_body["data"], "config": task_body["config"]}
        )
        inventory = type(inventory).model_validate(
            {**inventory_body, "digest": content_digest(inventory_body)}
        )
    body = original.model_dump(mode="json", exclude={"digest"})
    body["tasks"] = body["tasks"][:1]
    body["inventory_digest"] = inventory.digest
    body["tasks"][0]["task_digest"] = inventory.tasks[0].digest
    body["scorer_revision"] = scorer_fingerprint()
    if case == "sdk_absent_info":
        body["route_identity"] = "codex-sdk:chatgpt"
    manifest = type(original).model_validate({**body, "digest": content_digest(body)})
    frozen = next(task for task in inventory.tasks if task.task_name == manifest.tasks[0].task_name)

    class Runner:
        async def run_episode(self, task, ctx, **callbacks):
            episode = episode_for(task)
            episode.ok = case != "failed_execution"
            trace = vf.Trace(
                episode_id=episode.id,
                agent=vf.AgentInfo(config=vf.AgentConfig()),
                task=episode.task,
            )
            trace.ok = True
            world = WorldState.model_validate(task.data.initial_state)
            if case != "unsolved":
                world.salesforce.contacts[0].phone = "+1-555-0101"
            encoded = world.model_dump(mode="json")
            trace.state = AutomationBenchState(world=encoded)
            if case == "normal_completion":
                trace.stop_condition = "agent_completed"
            if case == "budget_stop":
                trace.stop_condition = "max_output_tokens"
            if case.startswith("sdk_") and case != "sdk_absent_info":
                sdk: dict = {"events": [{"kind": "finished", "ok": True, "status": "completed"}]}
                if case == "sdk_type_mutation":
                    sdk["marker"] = True
                trace.info["codex_sdk"] = sdk
                if case != "sdk_seal_missing":
                    trace.state.artifacts["codex_sdk/events.json"] = json.dumps(sdk).encode()
                if case == "sdk_seal_mismatch":
                    sdk["unexpected_mutation"] = True
                if case == "sdk_type_mutation":
                    sdk["marker"] = 1
            if case == "malformed_sdk":
                trace.info["codex_sdk"] = {"events": [None]}
            if case != "missing_finalization":
                score = score_world(
                    world=encoded,
                    initial_state=task.data.initial_state,
                    assertions=task.data.assertions,
                )
                trace.info["automationbench"] = {
                    "end_state": score.end_state,
                    "assertions": list(score.assertion_results),
                }
            episode.traces.append(trace)
            return episode

    results = asyncio.run(collect(cast(vf.Env, Runner()), ctx, inventory, manifest, tmp_path))
    attempt = results[0]
    assert attempt.episode_path is not None
    path = Path(attempt.episode_path)
    report = verify_retained(path, frozen, attempt, manifest)
    assert report["current_outcome_verified"] is (
        case in {"solved", "sdk_solved", "normal_completion"}
    )
    assert report["qwen_eligibility"] == "pending_reward_redesign_and_budget_qualification"
    if case == "malformed_sdk":
        assert report["reason"] == "sdk_completion_unavailable"
    if case == "sdk_seal_missing":
        assert report["reason"] == "sealed_sdk_source_unavailable"
    if case == "sdk_seal_mismatch":
        assert report["reason"] == "sdk_info_differs_from_sealed_source"
    if case == "sdk_type_mutation":
        assert report["reason"] == "sdk_info_differs_from_sealed_source"
    if case == "sdk_absent_info":
        assert report["reason"] == "sdk_completion_unavailable"
    if case == "budget_stop":
        assert report["reason"] == "trace_failed_or_stopped"
    if case == "sdk_solved":
        episode, _ = validate_episode(path, frozen, attempt)
        loaded = episode.traces[0]
        artifacts = read_retained_artifacts(path.parent, loaded)
        assert artifacts["codex_sdk/events.json"] is not None
        assert json.loads(artifacts["codex_sdk/events.json"]) == loaded.info["codex_sdk"]
        artifact_path = path.parent / loaded.info["automationbench_collection_artifacts"]["path"]
        artifact_path.write_text("corrupted")
        with pytest.raises(ValueError, match="artifact envelope digest"):
            validate_episode(path, frozen, attempt)
    if case == "excluded_failure":
        assert report["official_strict_score"] == 1
        assert report["all_declared_assertions_passed"] is False
        assert report["reason"] == "assertions_not_fully_satisfied"
    if case == "solved":
        assert report["official_strict_score"] == 1
        bad = manifest.model_dump(mode="json", exclude={"digest"})
        bad["scorer_revision"] = "wrong"
        wrong = type(manifest).model_validate({**bad, "digest": content_digest(bad)})
        changed_attempt = attempt.model_copy(update={"manifest_digest": wrong.digest})
        with pytest.raises(ValueError, match="scorer"):
            verify_retained(path, frozen, changed_attempt, wrong)
        mismatched = attempt.model_copy(update={"task_name": "wrong"})
        with pytest.raises(ValueError, match="supplied frozen task"):
            verify_retained(path, frozen, mismatched, manifest)
        mutated = frozen.model_copy(deep=True)
        mutated.data["assertions"][0]["value"] = "changed"
        with pytest.raises(ValueError, match="frozen task content digest"):
            verify_retained(path, mutated, attempt, manifest)
        manifest.native_config["unexpected_mutation"] = True
        with pytest.raises(ValueError, match="manifest content digest"):
            verify_retained(path, frozen, attempt, manifest)


@pytest.fixture
def inputs():
    inventory = freeze_inventory(
        AutomationBenchConfig(domains=["simple"]), source_identity={"fixture": "collector"}
    )
    manifest = plan_collection(
        inventory,
        selections=tuple(
            TaskSelection(
                task_name=task.task_name,
                task_digest=task.digest,
                family=task.task_name,
                split="development",
            )
            for task in inventory.tasks[:3]
        ),
        route_identity="unpaid-fixture",
        native_config={"fixture": True},
        scorer_revision="fixture",
        limits=CollectionLimits(
            max_concurrent=2,
            max_total_attempts=6,
            max_attempts_per_task=2,
            max_elapsed_seconds=60,
            attempt_timeout_seconds=20,
            max_turns=4,
            max_output_tokens=100,
            cost_measurement="unavailable",
        ),
    )
    ctx = vf.ModelContext(model=manifest.provider_model_id, client=vf.EvalClientConfig())
    return inventory, manifest, ctx


def episode_for(task):
    return vf.Episode(task=vf.TraceTask(type="AutomationBenchTask", data=task.data))


def test_crash_window_reconciles_artifact_before_scheduling_and_detects_tamper(tmp_path, inputs):
    inventory, manifest, _ctx = inputs
    frozen = inventory.tasks[0]
    with AttemptJournal(tmp_path / "attempts.jsonl", manifest) as journal:
        begun = journal.start(frozen.task_name)
        path = tmp_path / begun.attempt_id / "episode.json"
        episode = episode_for(frozen.instantiate())
        episode.group = vf.GroupInfo(id=begun.attempt_id)
        episode.run = vf.EvalRunInfo(id=manifest.digest, repetition_index=begun.occurrence)
        _write_native(path, episode.to_record())
    with AttemptJournal(tmp_path / "attempts.jsonl", manifest) as journal:
        reconcile_attempts(journal, inventory, tmp_path)
        retained = journal.latest[begun.attempt_id]
        assert retained.status == "interrupted" and retained.error_type == "UncommittedOutcome"
        assert not validate_episode(path, frozen)[0].ok  # Retained is not solved.
    path.write_bytes(path.read_bytes() + b" ")
    with (
        AttemptJournal(tmp_path / "attempts.jsonl", manifest) as journal,
        pytest.raises(ValueError, match="bytes changed"),
    ):
        reconcile_attempts(journal, inventory, tmp_path)


def test_slot_refill_preserves_native_failed_episodes_and_resume_does_not_repeat(tmp_path, inputs):
    inventory, manifest, ctx = inputs

    async def scenario():
        first_started = asyncio.Event()
        third_started = asyncio.Event()
        names = [task.task_name for task in manifest.tasks]
        calls = []
        active = 0
        peak = 0

        class Runner:
            async def run_episode(self, task, ctx, **callbacks):
                nonlocal active, peak
                calls.append(task.data.task_name)
                assert task.data.model_dump(mode="json") == next(
                    frozen.data
                    for frozen in inventory.tasks
                    if frozen.task_name == task.data.task_name
                )
                active += 1
                peak = max(peak, active)
                if task.data.task_name == names[0]:
                    first_started.set()
                    await third_started.wait()
                elif task.data.task_name == names[1]:
                    await first_started.wait()
                else:
                    third_started.set()
                active -= 1
                return episode_for(task)

        runner = cast(vf.Env, Runner())
        result = await collect(runner, ctx, inventory, manifest, tmp_path)
        assert peak == 2 and len(result) == 3
        assert all(row.status == "retained" for row in result)
        await collect(runner, ctx, inventory, manifest, tmp_path)
        assert calls == names

    asyncio.run(scenario())


def test_execution_error_stops_refill_but_drains_inflight_task(tmp_path, inputs):
    inventory, manifest, ctx = inputs

    async def scenario():
        both_started = asyncio.Event()
        calls = []
        finished = []

        class Runner:
            async def run_episode(self, task, ctx, **callbacks):
                name = task.data.task_name
                calls.append(name)
                if len(calls) == 2:
                    both_started.set()
                await both_started.wait()
                if name == manifest.tasks[0].task_name:
                    raise RuntimeError("synthetic authentication rejection")
                await asyncio.sleep(0.02)
                finished.append(name)
                return episode_for(task)

        result = await collect(
            cast(vf.Env, Runner()), ctx, inventory, manifest, tmp_path, stop_on_execution_error=True
        )
        assert calls == [task.task_name for task in manifest.tasks[:2]]
        assert finished == [manifest.tasks[1].task_name]
        assert len(result) == 2
        assert {row.status for row in result} == {"failed", "retained"}

    asyncio.run(scenario())


def test_cancellation_saves_live_native_prefix_and_consumes_attempt(tmp_path, inputs):
    inventory, manifest, ctx = inputs

    async def scenario():
        started = asyncio.Event()

        class Runner:
            async def run_episode(self, task, ctx, **callbacks):
                episode = episode_for(task)
                trace = vf.Trace(
                    episode_id=episode.id,
                    agent=vf.AgentInfo(config=vf.AgentConfig()),
                    task=episode.task,
                )
                from automationbench_v1.tools import AutomationBenchState

                trace.state = AutomationBenchState(world=task.data.initial_state)
                callbacks["on_trace"](trace)
                started.set()
                await asyncio.Event().wait()

        execution = asyncio.create_task(
            collect(cast(vf.Env, Runner()), ctx, inventory, manifest, tmp_path)
        )
        await started.wait()
        execution.cancel()
        with pytest.raises(asyncio.CancelledError):
            await execution
        with AttemptJournal(tmp_path / "attempts.jsonl", manifest) as journal:
            assert len(journal.latest) == 2
            for result in journal.latest.values():
                assert result.status == "interrupted"
                assert result.episode_path is not None
                episode, _ = validate_episode(
                    Path(result.episode_path),
                    next(task for task in inventory.tasks if task.task_name == result.task_name),
                )
                assert len(episode.traces) == 1 and not episode.ok
                retained = episode.traces[0].info["automationbench_collection_state"]
                assert retained["status"] == "available"
                assert (
                    retained["digest"]
                    == hashlib.sha256(retained["world_json"].encode()).hexdigest()
                )

    asyncio.run(scenario())


def test_unfinished_start_is_not_implicitly_retried(tmp_path, inputs):
    inventory, manifest, _ctx = inputs
    with AttemptJournal(tmp_path / "attempts.jsonl", manifest) as journal:
        first = journal.start(manifest.tasks[0].task_name)
    with AttemptJournal(tmp_path / "attempts.jsonl", manifest) as journal:
        reconcile_attempts(journal, inventory, tmp_path)
        assert journal.latest[first.attempt_id].status == "interrupted"
        assert journal.latest[first.attempt_id].episode_path is None


def test_saved_disposition_survives_missing_terminal_line_and_cross_attempt_copy_rejects(
    tmp_path, inputs
):
    inventory, manifest, _ctx = inputs
    frozen = inventory.tasks[0]
    with AttemptJournal(tmp_path / "attempts.jsonl", manifest) as journal:
        first = journal.start(frozen.task_name)
        episode = episode_for(frozen.instantiate())
        episode.group = vf.GroupInfo(id=first.attempt_id)
        episode.run = vf.EvalRunInfo(id=manifest.digest, repetition_index=first.occurrence)
        path = tmp_path / first.attempt_id / "episode.json"
        digest = _write_native(path, episode.to_record())
        _write_native(
            path.with_name("outcome.json"),
            {
                "attempt_id": first.attempt_id,
                "manifest_digest": manifest.digest,
                "episode_digest": digest,
                "status": "failed",
                "error_type": "TimeoutError",
                "failure_category": "unknown",
                "discarded_artifacts": [],
            },
        )
    with AttemptJournal(tmp_path / "attempts.jsonl", manifest) as journal:
        reconcile_attempts(journal, inventory, tmp_path)
        recovered = journal.latest[first.attempt_id]
        assert recovered.status == "failed" and recovered.error_type == "TimeoutError"
        second = journal.start(frozen.task_name)
        copied = tmp_path / second.attempt_id / "episode.json"
        copied.parent.mkdir()
        copied.write_bytes(path.read_bytes())
        with pytest.raises(ValueError, match="bound to its collection attempt"):
            reconcile_attempts(journal, inventory, tmp_path)


def test_discarded_retry_traces_remain_separate_and_verified_on_resume(tmp_path, inputs):
    inventory, manifest, ctx = inputs

    class Runner:
        async def run_episode(self, task, ctx, **callbacks):
            episode = episode_for(task)
            discarded = vf.Trace(
                episode_id=episode.id,
                agent=vf.AgentInfo(config=vf.AgentConfig()),
                task=episode.task,
            )
            callbacks["on_trace"](discarded)
            callbacks["on_discard"](discarded)
            return episode

    result = asyncio.run(collect(cast(vf.Env, Runner()), ctx, inventory, manifest, tmp_path))
    first = result[0]
    assert first.outcome_digest is not None and first.episode_path is not None
    assert validate_episode(Path(first.episode_path), inventory.tasks[0], first)[0].traces == []
    discarded_path = Path(first.episode_path).with_name("discarded-0.json")
    discarded_path.write_bytes(discarded_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="discarded native trace bytes"):
        asyncio.run(collect(cast(vf.Env, Runner()), ctx, inventory, manifest, tmp_path))


def test_action_inspection_validates_bytes_and_keeps_incomplete_capture_unavailable(inputs):
    pytest.importorskip("verifiers.v1.mcp.execution")
    from automationbench_v1.capture import canonical_json

    inventory, _manifest, _ctx = inputs
    episode = episode_for(inventory.tasks[0].instantiate())
    trace = vf.Trace(
        episode_id=episode.id,
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=episode.task,
    )
    episode.traces.append(trace)
    snapshot = canonical_json({})
    digest = hashlib.sha256(snapshot.encode()).hexdigest()
    evidence = {
        "kind": "automationbench_raw_action",
        "action": {
            "occurrence_index": 0,
            "tool_name": "read",
            "arguments_json": "{}",
            "before_digest": digest,
            "after_digest": digest,
            "status": "returned",
            "result_json": "null",
        },
        "snapshots": {digest: snapshot},
    }

    def events(raw):
        result = []
        for index, phase in enumerate(("dispatch", "returned")):
            receipt = vf.ToolServerReceipt(
                invocation_id="same-local-index",
                tool_name="read",
                arguments_json="{}",
                event_index=index,
                phase=phase,
                result_json="null" if index else None,
                evidence_json=(canonical_json(raw),) if index else (),
                state_persistence="unchanged" if index else "not_attempted",
            )
            result.append(
                vf.ToolServerExecutionEvent(
                    invocation_id=receipt.invocation_id,
                    event_index=index,
                    phase=phase,
                    receipt_seq=index,
                    state_revision=0,
                    receipt_json=canonical_json(receipt.model_dump(mode="json")),
                )
            )
        return tuple(result)

    trace.tool_execution_events = events(evidence)
    restored = vf.WireEpisode.model_validate(episode.to_record())
    assert inspect_capture(restored).observed_invocations_complete
    evidence["snapshots"][digest] = '{"tampered":true}'
    trace.tool_execution_events = events(evidence)
    with pytest.raises(ValueError, match="snapshot bytes"):
        inspect_capture(vf.WireEpisode.model_validate(episode.to_record()))
    trace.tool_execution_events = trace.tool_execution_events[:1]
    incomplete = inspect_capture(vf.WireEpisode.model_validate(episode.to_record()))
    assert not incomplete.observed_invocations_complete
    assert (
        incomplete.actions == () and "incomplete_receipt_pair" in incomplete.unavailable_reasons[0]
    )
