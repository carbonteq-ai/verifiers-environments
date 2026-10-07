"""Manufactured public requests, real Jira actions and native replay envelopes."""

import asyncio
import copy
import json
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_manifest_created_objects import (
    HUBSPOT_PROMPT,
    PROMPT,
    bindings,
    check,
    create,
    hubspot_associate,
    hubspot_bindings,
    hubspot_check,
    hubspot_create,
    hubspot_initial,
    hubspot_spec,
    initial,
    spec,
    status,
)
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_notification_evidence import run_operations

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.loader import load_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_created_assessments import (
    capture_created_inputs,
    manifest_created_identity,
)
from automationbench_v1.manifest_guard_assessments import digest, execution_subject
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig


def declaration(done=False):
    selected = check(done=done)
    return load_contract(
        canonical_json(
            {
                "schema_version": 1,
                "manifest_id": "manufactured-created-native",
                "revision": "1",
                "public_request": PROMPT[0]["content"],
                "bindings": bindings(),
                "sources": {
                    "request": spec().model_dump(mode="json"),
                    "issues": {"adapter": "jira.issues@1", "project_id": "proj_qa"},
                },
                "checks": [selected.model_dump(mode="json")],
                "credit": [
                    {
                        "check": selected.check_id,
                        "policy": "created_retained_completion_once@1",
                        "channel": "completion",
                        "completion_selection": "earliest",
                        "goal_fields": ["status"] if done else ["summary", "project", "issuetype"],
                    }
                ],
            }
        )
    )


def scored(
    monkeypatch,
    *,
    calls=None,
    missing_ack=None,
    done=False,
    public=None,
    score=True,
    prompt=None,
    contract=None,
):
    monkeypatch.setattr(
        manifest_assessments, "load_task_contract", lambda _: contract or declaration(done)
    )
    task, _, trace = native_fixture(
        run_operations(public or initial(), calls if calls is not None else [create()]),
        missing_ack=missing_ack,
    )
    data = AutomationBenchData.model_validate(
        {**task.data.model_dump(mode="json"), "prompt": PROMPT if prompt is None else prompt}
    )
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    trace.task = trace.task.model_copy(update={"data": data})
    episode = vf.WireEpisode.model_validate(
        {"task": trace.task.model_dump(mode="json"), "traces": [trace.model_dump(mode="json")]}
    )
    retained = cast(Any, episode.traces[0])
    retained.state = trace.state
    scalar = copy.deepcopy(retained.rewards)
    if score:
        asyncio.run(task.score(retained))
    assert retained.rewards == scalar
    return task, episode, retained


def goals(trace):
    return [
        record for record in terminal_records(trace) if record.signal.signal_id == "request.created"
    ]


def clean(trace):
    assert not trace.assessment_errors and not trace.credit_errors
    assert not any(
        batch.run.status in {"failed", "interrupted"} for batch in trace.assessment_batches
    )


def hubspot_declaration(collection, *, associated=False):
    selected = hubspot_check(collection, associated=associated)
    goal_fields = (
        ["associated_contact_ids"]
        if associated
        else ["email"]
        if collection == "contacts"
        else ["dealname", "amount"]
    )
    return load_contract(
        canonical_json(
            {
                "schema_version": 1,
                "manifest_id": "manufactured-hubspot-native",
                "revision": "1",
                "public_request": HUBSPOT_PROMPT[0]["content"],
                "bindings": hubspot_bindings(),
                "sources": {
                    "request": hubspot_spec(collection).model_dump(mode="json"),
                    "objects": {"adapter": "hubspot.objects@1", "collection": collection},
                },
                "checks": [selected.model_dump(mode="json")],
                "credit": [
                    {
                        "check": selected.check_id,
                        "policy": "created_retained_completion_once@1",
                        "channel": "completion",
                        "completion_selection": "earliest",
                        "goal_fields": goal_fields,
                    }
                ],
            }
        )
    )


@pytest.mark.parametrize(
    "collection,associated", [("contacts", False), ("deals", False), ("deals", True)]
)
def test_hubspot_native_completion_rescore_and_strict_reload(monkeypatch, collection, associated):
    calls = [hubspot_create(collection)] + (
        [hubspot_associate(), hubspot_associate()] if associated else []
    )
    task, episode, trace = scored(
        monkeypatch,
        public=hubspot_initial(),
        calls=calls,
        prompt=HUBSPOT_PROMPT,
        contract=hubspot_declaration(collection, associated=associated),
    )
    clean(trace)
    assert len(goals(trace)) == 1 and goals(trace)[0].value == 1
    assert len(penalties(trace)) == 1
    witness = "execution-1" if associated else "execution-0"
    part = penalties(trace)[0]
    assert part.recipient.execution.invocation_id == witness
    assert part.parent_assessment_ids == (goals(trace)[0].assessment_id,)
    original = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == original
    reloaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    retained = cast(Any, reloaded.traces[0])
    retained.state = trace.state
    asyncio.run(task.score(retained))
    clean(retained)
    assert tuple(retained.credit_assignments) == original


@pytest.mark.parametrize("collection", ["contacts", "deals"])
def test_hubspot_native_missing_ack_keeps_outcome_without_credit(monkeypatch, collection):
    _, _, trace = scored(
        monkeypatch,
        public=hubspot_initial(),
        calls=[hubspot_create(collection)],
        missing_ack=0,
        prompt=HUBSPOT_PROMPT,
        contract=hubspot_declaration(collection),
    )
    clean(trace)
    assert goals(trace)[0].value == 1 and not penalties(trace)


def test_hubspot_native_credit_retarget_cannot_claim_birth_as_association(monkeypatch):
    task, _, trace = scored(
        monkeypatch,
        public=hubspot_initial(),
        prompt=HUBSPOT_PROMPT,
        calls=[hubspot_create("deals"), hubspot_associate()],
        contract=hubspot_declaration("deals", associated=True),
    )
    clean(trace)
    request = trace.credit_assignments[0].request
    configuration = json.loads(request.rule.configuration_json)
    configuration["allocation_witness"].update(
        occurrence="execution-0", effect_id="execution-0", expected_revision=0, applied_revision=1
    )
    target = request.targets[0].model_copy(
        update={"recipient": execution_subject(request.source, "execution-0")}
    )
    forged = request.model_copy(
        update={
            "targets": (target,),
            "rule": request.rule.model_copy(
                update={"configuration_json": canonical_json(configuration)}
            ),
        }
    )
    with pytest.raises(ValueError, match="allocation_proof_mismatch"):
        asyncio.run(manifest_created_identity(task, forged))


def test_birth_outcome_exact_credit_and_native_reload_consumption(monkeypatch):
    task, episode, trace = scored(monkeypatch, calls=[create(summary="Other"), create(), create()])
    clean(trace)
    assert len(goals(trace)) == 1 and goals(trace)[0].value == 1
    assert len(penalties(trace)) == 1
    part = penalties(trace)[0]
    assert part.value == 1 and part.recipient.execution.invocation_id == "execution-1"
    assert part.parent_assessment_ids == (goals(trace)[0].assessment_id,)
    original = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == original
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    clean(replay)
    assert tuple(replay.credit_assignments) == original


@pytest.mark.parametrize(
    "calls,value,witness",
    [
        ([create(), status("Done")], 1, "execution-1"),
        ([create(), status("Done"), status("Broken")], 0, None),
        ([create(), status("Done"), status("Broken"), status("Done")], 1, "execution-1"),
        ([create(), status("To Do"), status("Done")], 1, "execution-2"),
    ],
)
def test_final_retention_damage_repair_and_noops(monkeypatch, calls, value, witness):
    _, _, trace = scored(monkeypatch, calls=calls, done=True)
    clean(trace)
    assert goals(trace)[0].value == value
    assert len(penalties(trace)) == (1 if witness else 0)
    if witness:
        assert penalties(trace)[0].recipient.execution.invocation_id == witness


def test_missing_ack_preserves_outcome_without_action_credit(monkeypatch):
    _, _, trace = scored(monkeypatch, missing_ack=0)
    clean(trace)
    assert goals(trace)[0].value == 1 and not penalties(trace)


def test_changed_public_authority_preserves_one_unavailable_request(monkeypatch):
    _, _, trace = scored(monkeypatch, prompt=[{"role": "user", "content": "Cancel this request."}])
    clean(trace)
    assert len(goals(trace)) == 1 and goals(trace)[0].status == "abstained"
    assert goals(trace)[0].value is None and not penalties(trace)


def test_coherent_retarget_to_actual_unrelated_birth_rejected(monkeypatch):
    task, _, trace = scored(monkeypatch, calls=[create(), create(summary="Other")])
    clean(trace)
    request = trace.credit_assignments[0].request
    configuration = json.loads(request.rule.configuration_json)
    source = json.loads(request.source.source_json)
    other = source["task_evidence"]["final"]["jira"]["issues"][1]
    configuration["allocation_witness"].update(
        native_record_id=other["id"],
        effect_id=other["creation_action_id"],
        occurrence="execution-1",
        expected_revision=1,
        applied_revision=2,
    )
    target = request.targets[0].model_copy(
        update={"recipient": execution_subject(request.source, "execution-1")}
    )
    forged = request.model_copy(
        update={
            "targets": (target,),
            "rule": request.rule.model_copy(
                update={"configuration_json": canonical_json(configuration)}
            ),
        }
    )
    with pytest.raises(ValueError, match="allocation_proof_mismatch"):
        asyncio.run(manifest_created_identity(task, forged))


def test_failed_current_attempt_cannot_reuse_positive_parent(monkeypatch):
    original = ManifestAssessmentTask.plan_credit

    def failed(self, source, assessments, context):
        changed = tuple(
            batch.model_copy(update={"run": batch.run.model_copy(update={"status": "failed"})})
            for batch in assessments
        )
        return original(self, source, changed, context)

    monkeypatch.setattr(ManifestAssessmentTask, "plan_credit", failed)
    _, _, trace = scored(monkeypatch)
    assert not penalties(trace)


def test_new_native_object_does_not_reset_request_consumption(monkeypatch):
    _, _, prefix = scored(monkeypatch)
    task, _, extended = scored(monkeypatch, calls=[create(), create()], score=False)
    extended.id = prefix.id
    extended.credit_assignments = prefix.credit_assignments
    asyncio.run(task.score(extended))
    clean(extended)
    assert len(penalties(extended)) == 1


def test_new_failed_attempt_never_falls_back_to_historical_positive_parent(monkeypatch):
    task, _, trace = scored(monkeypatch)
    clean(trace)
    previous = tuple(trace.credit_assignments)

    def failed(*args):
        raise ValueError("manufactured_current_failure")

    monkeypatch.setattr(manifest_assessments, "assess_created", failed)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == previous
    assert any(batch.run.status == "failed" for batch in trace.assessment_batches)


def test_coherent_foreign_view_cannot_publish_success(monkeypatch):
    original = ManifestAssessmentTask.assessment_requests

    def substituted(self, source):
        result = []
        for name, request in original(self, source):
            view = request.views[0]
            material = json.loads(view.input_json)
            material["source"]["task_evidence"]["final"]["jira"]["issues"][0]["fields"][
                "summary"
            ] = "Exact audit"
            material.update(capture_created_inputs(material["source"], declaration()))
            replacement = vf.ObservationView.capture(
                material,
                snapshot_id=source.snapshot_id,
                builder_revision=view.builder_revision,
                scope=view.scope,
                subjects=view.subjects,
            )
            config = json.loads(request.run.configuration_json)
            config["source_digest"] = digest(material["source"])
            result.append(
                (
                    name,
                    request.model_copy(
                        update={
                            "views": (replacement,),
                            "run": request.run.model_copy(
                                update={"configuration_json": canonical_json(config)}
                            ),
                        }
                    ),
                )
            )
        return result

    monkeypatch.setattr(ManifestAssessmentTask, "assessment_requests", substituted)
    _, _, trace = scored(monkeypatch, calls=[create(summary="Other")])
    assert any(batch.run.status == "failed" for batch in trace.assessment_batches)
    assert not goals(trace) and not penalties(trace)
