"""Synthetic sealed SDK/native source fixtures; no model or credential calls."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Literal, cast

import pytest
import verifiers.v1 as vf
from verifiers.v1.assessment_source import capture_trace_source

from automationbench.schema.world import WorldState
from automationbench_v1.calibration.collector import (
    _write_native,
    collect,
    read_retained_artifacts,
    validate_episode,
)
from automationbench_v1.calibration.eligibility import (
    ReassessmentReplay,
    RequiredRewardCheck,
    TaskEligibilityProof,
    TaskRewardContract,
    build_eligibility_proof,
    validate_eligibility_proof,
)
from automationbench_v1.calibration.frozen_verification import (
    build_frozen_verification,
    capture_frozen_verifier_binding,
)
from automationbench_v1.calibration.inventory import (
    content_digest,
    freeze_inventory,
    save_inventory,
)
from automationbench_v1.calibration.journal import AttemptJournal
from automationbench_v1.calibration.models import CollectionLimits, TaskSelection, plan_collection
from automationbench_v1.calibration.reward_revision import capture_redesign_revision
from automationbench_v1.calibration.sdk_runner import SIGNED_IN_ROUTE_IDENTITY
from automationbench_v1.calibration.source import source_identity
from automationbench_v1.calibration.verify import scorer_fingerprint
from automationbench_v1.capture import canonical_json
from automationbench_v1.taskset import AutomationBenchConfig
from automationbench_v1.tools import AutomationBenchState


class FixtureVerifier:
    producer_id = "fixture.closed-policy"
    producer_revision = "1"
    rubric_revision = "1"
    source_digest = "e" * 64

    def replay(self, *, episode, task, contract, request):
        trace = episode.traces[0]
        evidence = {
            "task_digest": task.digest,
            "world_digest": trace.info["automationbench_collection_state"]["digest"],
        }
        source = capture_trace_source(cast(vf.Trace, trace), task_evidence=evidence)
        subject = vf.SubjectRef(
            kind="trace", snapshot_id=source.snapshot_id, episode_id=episode.id, trace_id=trace.id
        )
        view = vf.ObservationView.capture(
            {"fixture": "declared deterministic context"},
            snapshot_id=source.snapshot_id,
            builder_revision="fixture-closed-policy",
            scope="retrospective",
            subjects=(subject,),
        )
        run = vf.AssessmentRun(
            run_id=request.run_id,
            producer_id=self.producer_id,
            producer_revision=self.producer_revision,
            rubric_revision=self.rubric_revision,
            snapshot_id=source.snapshot_id,
            invocation_id=request.invocation_id,
            attempt_id=request.attempt_id,
            expected=tuple(
                vf.AssessmentTarget(subject=subject, signal=item.signal) for item in contract.checks
            ),
        )
        world = json.loads(trace.info["automationbench_collection_state"]["world_json"])
        values = {
            "goal": float(bool(world["salesforce"]["contacts"])),
            "guard": float(bool(trace.errors) or not trace.ok),
            "coverage": float("codex_sdk/events.json" in trace.state.artifacts),
        }
        findings = tuple(
            vf.Assessment(
                assessment_id=f"fixture-{item.key}",
                run_id=run.run_id,
                subject=subject,
                view_id=view.view_id,
                signal=item.signal,
                status="valid",
                value=values[item.purpose],
            )
            for item in contract.checks
        )
        return ReassessmentReplay(
            batch=vf.AssessmentBatch(source=source, run=run, views=(view,), assessments=findings)
        )


def make_reference(
    directory: Path,
    *,
    output=12,
    original_budget=16384,
    missing_usage=False,
    guard_value=0.0,
    guard_status: Literal["valid", "abstained"] = "valid",
    mutate_source=False,
    solved=True,
    admission_policy="accepted_redesign",
):
    """Exercise the real builder on fabricated reported usage and native results.

    The signed-in labels are fixture material, not a claim of real authentication.
    The fixture contract has no promotion authority outside these tests.
    """
    directory.mkdir(parents=True, exist_ok=True)
    import verifiers

    import automationbench
    import automationbench_v1

    identity = source_identity(directory / "source-snapshot.zip")
    binding = capture_frozen_verifier_binding(
        interpreter=Path(sys.executable),
        package_roots={
            "automationbench": Path(automationbench.__file__).parent,
            "automationbench_environment": Path(automationbench_v1.__file__).parent,
            "verifiers": Path(verifiers.__file__).parent,
        },
        source_archive=directory / "source-snapshot.zip",
        source_identity=identity,
    )
    inventory = freeze_inventory(
        AutomationBenchConfig(
            domains=["simple"], task_names=["simple.email_sf_contact_phone_update"]
        ),
        source_identity=identity,
    )
    task = inventory.tasks[0]
    selection = TaskSelection(
        task_name=task.task_name,
        task_digest=task.digest,
        family=task.task_name,
        split="development",
    )
    manifest = plan_collection(
        inventory,
        selections=(selection,),
        route_identity=SIGNED_IN_ROUTE_IDENTITY,
        native_config={"fixture": "native-sdk-event-shape-only"},
        scorer_revision=scorer_fingerprint(),
        limits=CollectionLimits(
            max_concurrent=1,
            max_attempts_per_task=2,
            max_total_attempts=2,
            max_elapsed_seconds=600,
            attempt_timeout_seconds=30,
            max_turns=20,
            max_output_tokens=original_budget,
            cost_measurement="unavailable",
        ),
    )
    ctx = vf.ModelContext("gpt-6-luna", vf.EvalClientConfig())

    class FixtureEnv:
        async def run_episode(self, native_task, context, **callbacks):
            episode = vf.Episode[Any, Any, Any](
                task=vf.TraceTask(type="AutomationBenchTask", data=native_task.data)
            )
            trace = vf.Trace(
                episode_id=episode.id,
                task=episode.task,
                agent=vf.AgentInfo(config=vf.AgentConfig()),
                state=AutomationBenchState(),
            )
            await native_task.setup(trace, None)
            state = WorldState.model_validate(native_task.data.initial_state)
            if solved:
                state.salesforce.contacts[0].phone = "+1-555-0101"
            trace.state.world = state.model_dump(mode="json")
            trace.ok = True
            trace.stop_condition = "agent_completed"
            await native_task.score(trace)
            await native_task.finalize(trace, None)
            counts = {
                "inputTokens": 30,
                "cachedInputTokens": 0,
                "cacheWriteInputTokens": 0,
                "outputTokens": output,
                "reasoningOutputTokens": 5,
                "totalTokens": 30 + output,
            }
            sdk = {
                "sdk_version": "0.160.0",
                "provider_mode": "signed_in",
                "fresh_thread_requested": True,
                "output_budget": original_budget,
                "events": [
                    {"kind": "authenticated", "account_type": "chatgpt", "model": "gpt-6-luna"},
                    {
                        "kind": "thread_started",
                        "raw_response_events_requested": True,
                        "response": {"thread": {"id": "fixture-thread"}},
                    },
                    {
                        "kind": "event",
                        "event": {
                            "method": "rawResponse/completed",
                            "params": {
                                "threadId": "fixture-thread",
                                "turnId": "fixture-turn",
                                "responseId": "fixture-response",
                                "usage": None if missing_usage else counts,
                                "usageMetadata": None,
                            },
                        },
                    },
                    {
                        "kind": "event",
                        "event": {
                            "method": "thread/tokenUsage/updated",
                            "params": {
                                "threadId": "fixture-thread",
                                "turnId": "fixture-turn",
                                "tokenUsage": {"total": counts},
                            },
                        },
                    },
                    {
                        "kind": "event",
                        "event": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "fixture-thread",
                                "turn": {"id": "fixture-turn", "status": "completed"},
                            },
                        },
                    },
                    {"kind": "finished", "ok": True, "status": "completed"},
                ],
            }
            trace.info["codex_sdk"] = sdk
            trace.state.artifacts["codex_sdk/events.json"] = canonical_json(sdk).encode()
            episode.traces = [trace]
            episode.ok = True
            episode.assessment_finalization_state = "completed"
            if callbacks.get("on_trace"):
                callbacks["on_trace"](trace)
            return episode

    directory.mkdir(parents=True, exist_ok=True)
    save_inventory(inventory, directory / "inventory.json")
    _write_native(directory / "manifest.json", manifest.model_dump(mode="json"))
    (attempt,) = asyncio.run(
        collect(cast(vf.Env, FixtureEnv()), ctx, inventory, manifest, directory)
    )
    assert attempt.episode_path is not None
    episode_path = Path(attempt.episode_path)
    episode, digest = validate_episode(episode_path, task, attempt)
    trace = episode.traces[0]
    trace.state.artifacts.update(read_retained_artifacts(episode_path.parent, trace))
    verification = build_frozen_verification(
        approved_binding=binding,
        inventory_path=directory / "inventory.json",
        manifest_path=directory / "manifest.json",
        journal_path=directory / "attempts.jsonl",
        episode_path=episode_path,
    )
    _write_native(directory / "frozen-verification.json", verification.model_dump(mode="json"))
    checks = tuple(
        RequiredRewardCheck(
            key=key,
            purpose=cast(Literal["goal", "guard", "coverage"], purpose),
            signal=vf.SignalDefinition(
                signal_id=f"fixture.{key}",
                revision="1",
                semantics="other",
                description=f"Closed fixture {purpose}",
                units="fixture checks",
            ),
            producer_id="fixture.closed-policy",
            producer_revision="1",
            rubric_revision="1",
            subject_kind="trace",
            expected_value=value,
        )
        for key, purpose, value in (
            ("goals", "goal", 1.0),
            ("guards", "guard", 0.0),
            ("coverage", "coverage", 1.0),
        )
    )
    contract_body = {
        "schema_version": 2,
        "task_name": task.task_name,
        "task_digest": task.digest,
        "policy_source_digest": "f" * 64,
        "admission_policy": admission_policy,
        "guard_set": {
            "status": "reviewed_closed",
            "check_keys": ["guards"],
            "policy_source_digest": "f" * 64,
            "scope": "task_specific",
            "review_revision": "fixture-policy-review-1",
        },
        "checks": [item.model_dump(mode="json") for item in checks],
    }
    contract = TaskRewardContract.model_validate(
        {**contract_body, "digest": content_digest(contract_body)}
    )
    revision = capture_redesign_revision(
        {
            "task_contracts": {task.task_name: contract.digest},
            "frozen_verifiers": [binding.digest],
            "assessment_verifiers": {"fixture.closed-policy@1/1": FixtureVerifier.source_digest},
        },
        "c" * 64,
    )
    _write_native(directory / "revision.json", revision.model_dump(mode="json"))
    if mutate_source:
        trace.nodes.append(
            vf.MessageNode(
                parent=None, message=vf.UserMessage(content="not original"), sampled=False
            )
        )
    source = capture_trace_source(
        cast(vf.Trace, trace),
        task_evidence={
            "task_digest": task.digest,
            "world_digest": trace.info["automationbench_collection_state"]["digest"],
        },
    )
    subject = vf.SubjectRef(
        kind="trace", snapshot_id=source.snapshot_id, episode_id=episode.id, trace_id=trace.id
    )
    view = vf.ObservationView.capture(
        {"fixture": "declared deterministic context"},
        snapshot_id=source.snapshot_id,
        builder_revision="fixture-closed-policy",
        scope="retrospective",
        subjects=(subject,),
    )
    run = vf.AssessmentRun(
        run_id="fixture-run",
        producer_id="fixture.closed-policy",
        producer_revision="1",
        rubric_revision="1",
        snapshot_id=source.snapshot_id,
        invocation_id="fixture-invocation",
        attempt_id="fixture-assessment-attempt",
        expected=tuple(vf.AssessmentTarget(subject=subject, signal=item.signal) for item in checks),
    )
    findings = tuple(
        vf.Assessment(
            assessment_id=f"fixture-{item.key}",
            run_id=run.run_id,
            subject=subject,
            view_id=view.view_id,
            signal=item.signal,
            status=guard_status if item.purpose == "guard" else "valid",
            value=(guard_value if guard_status == "valid" else None)
            if item.purpose == "guard"
            else item.expected_value,
        )
        for item in checks
    )
    batch = vf.AssessmentBatch(source=source, run=run, views=(view,), assessments=findings)
    _write_native(
        directory / "reassessment.json",
        {
            "schema_version": 1,
            "original_episode_digest": digest,
            "redesign_digest": revision.digest,
            "contract_digest": contract.digest,
            "selected_run_ids": [run.run_id],
            "batches": [batch.model_dump(mode="json")],
            "credit_assignments": [],
        },
    )
    kwargs = {
        "inventory_path": directory / "inventory.json",
        "manifest_path": directory / "manifest.json",
        "journal_path": directory / "attempts.jsonl",
        "episode_path": episode_path,
        "assessment_path": directory / "reassessment.json",
        "revision_path": directory / "revision.json",
        "frozen_verification_path": directory / "frozen-verification.json",
        "approved_binding": binding,
        "current_redesign": revision,
        "reassessment_verifiers": {"fixture.closed-policy@1/1": FixtureVerifier()},
        "contract": contract,
    }
    return {
        "inventory": inventory,
        "manifest": manifest,
        "revision": revision,
        "selection": selection,
        "contract": contract,
        "kwargs": kwargs,
        "episode": episode,
    }


@pytest.fixture
def reference(tmp_path):
    return make_reference(tmp_path / "reference")


def test_official_scorer_change_invalidates_current_proof(reference, monkeypatch):
    from automationbench_v1.calibration import reward_revision

    proof = build_eligibility_proof(**reference["kwargs"])
    monkeypatch.setattr(reward_revision, "scorer_fingerprint", lambda: "d" * 64)
    with pytest.raises(ValueError, match="scorer changed"):
        validate_eligibility_proof(
            proof,
            task_name=proof.task_name,
            task_digest=proof.task_digest,
            redesign_digest=proof.redesign_digest,
            current_redesign=reference["revision"],
            reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
            approved_bindings={
                reference["kwargs"]["approved_binding"].digest: reference["kwargs"][
                    "approved_binding"
                ]
            },
        )


def test_closed_contract_native_sources_and_current_budget(reference):
    proof = build_eligibility_proof(**reference["kwargs"])
    assert proof.reported_output_tokens == 12
    assert {item.key: item.value for item in proof.checks} == {
        "goals": 1,
        "guards": 0,
        "coverage": 1,
    }
    assert TaskEligibilityProof.model_validate_json(proof.model_dump_json()) == proof
    validate_eligibility_proof(
        proof,
        task_name=proof.task_name,
        task_digest=proof.task_digest,
        redesign_digest=reference["revision"].digest,
        current_redesign=reference["revision"],
        reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
        approved_bindings={
            reference["kwargs"]["approved_binding"].digest: reference["kwargs"]["approved_binding"]
        },
    )
    # Later collection work leaves this exact terminal prefix unchanged.
    with AttemptJournal(reference["kwargs"]["journal_path"], reference["manifest"]) as journal:
        journal.start(proof.task_name, kind="confirmation")
    validate_eligibility_proof(
        proof,
        task_name=proof.task_name,
        task_digest=proof.task_digest,
        redesign_digest=reference["revision"].digest,
        current_redesign=reference["revision"],
        reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
        approved_bindings={
            reference["kwargs"]["approved_binding"].digest: reference["kwargs"]["approved_binding"]
        },
    )
    with pytest.raises(ValueError, match="another task"):
        validate_eligibility_proof(
            proof,
            task_name="outside-pool",
            current_redesign=reference["revision"],
            reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
            approved_bindings={
                reference["kwargs"]["approved_binding"].digest: reference["kwargs"][
                    "approved_binding"
                ]
            },
            task_digest=proof.task_digest,
            redesign_digest=proof.redesign_digest,
        )


@pytest.mark.parametrize(
    "options,reason",
    [
        ({"output": 16385}, "budget is unqualified"),
        ({"missing_usage": True}, "budget is unqualified"),
        ({"original_budget": 32768}, "original signed-in Luna"),
        ({"guard_value": 1.0}, "differ from deterministic replay"),
        ({"guard_status": "abstained"}, "differ from deterministic replay"),
        ({"mutate_source": True}, "original native material"),
    ],
)
def test_unknown_excess_rescue_harm_unavailable_or_different_source(tmp_path, options, reason):
    source = make_reference(tmp_path / "reference", **options)
    with pytest.raises(ValueError, match=reason):
        build_eligibility_proof(**source["kwargs"])


def test_official_full_score_alone_and_changed_artifacts_do_not_admit(reference):
    proof = build_eligibility_proof(**reference["kwargs"])
    path = reference["kwargs"]["assessment_path"]
    document = json.loads(path.read_text())
    document.update(selected_run_ids=[], batches=[])
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="selected attempts"):
        build_eligibility_proof(**reference["kwargs"])
    with pytest.raises(ValueError, match="artifact changed"):
        validate_eligibility_proof(
            proof,
            task_name=proof.task_name,
            task_digest=proof.task_digest,
            redesign_digest=proof.redesign_digest,
            current_redesign=reference["revision"],
            reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
            approved_bindings={
                reference["kwargs"]["approved_binding"].digest: reference["kwargs"][
                    "approved_binding"
                ]
            },
        )


def test_redesign_change_invalidates_even_sealed_original_results(reference):
    proof = build_eligibility_proof(**reference["kwargs"])
    changed = capture_redesign_revision(
        {"task_contracts": {proof.task_name: proof.contract.digest}, "policy_revision": "next"},
        "c" * 64,
    )
    with pytest.raises(ValueError, match="another task or accepted redesign"):
        validate_eligibility_proof(
            proof,
            task_name=proof.task_name,
            task_digest=proof.task_digest,
            redesign_digest=changed.digest,
            current_redesign=changed,
            reassessment_verifiers=reference["kwargs"]["reassessment_verifiers"],
            approved_bindings={
                reference["kwargs"]["approved_binding"].digest: reference["kwargs"][
                    "approved_binding"
                ]
            },
        )


def test_resealed_task_evidence_rejects_and_missing_replay_is_closed(reference):
    path = reference["kwargs"]["assessment_path"]
    document = json.loads(path.read_bytes())
    batch = vf.AssessmentBatch.model_validate(document["batches"][0])
    trace = reference["episode"].traces[0]
    source = capture_trace_source(cast(vf.Trace, trace), task_evidence={"fabricated": "facts"})
    subject = batch.assessments[0].subject.model_copy(update={"snapshot_id": source.snapshot_id})
    old_view = batch.views[0]
    assert old_view.input_json is not None
    view = vf.ObservationView.capture(
        json.loads(old_view.input_json),
        snapshot_id=source.snapshot_id,
        builder_revision=old_view.builder_revision,
        scope=old_view.scope,
        subjects=(subject,),
    )
    request = batch.run.model_copy(
        update={
            "snapshot_id": source.snapshot_id,
            "expected": tuple(
                vf.AssessmentTarget(subject=subject, signal=item.signal)
                for item in batch.assessments
            ),
        }
    )
    findings = tuple(
        item.model_copy(update={"subject": subject, "view_id": view.view_id})
        for item in batch.assessments
    )
    forged = vf.AssessmentBatch(source=source, run=request, views=(view,), assessments=findings)
    document["batches"] = [forged.model_dump(mode="json")]
    path.write_text(canonical_json(document))
    with pytest.raises(ValueError, match="differ from deterministic replay"):
        build_eligibility_proof(**reference["kwargs"])
    missing = {**reference["kwargs"], "reassessment_verifiers": {}}
    with pytest.raises(ValueError, match="no independently approved deterministic replay"):
        build_eligibility_proof(**missing)
