"""Generic request obligations with genuine simulator actions in native envelopes."""

import asyncio
import copy
import json
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_manifest_guards import comparison, create, field, literal
from test_manifest_obligations import world
from test_notification_evidence import run_operations

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.loader import load_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_guard_assessments import digest, execution_subject
from automationbench_v1.manifest_obligation_assessments import (
    capture_obligation_inputs,
    manifest_obligation_identity,
)
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig

PROMPT = [{"role": "user", "content": "Create a new Asana task named Provision person@example.com in project-access."}]
SIGNAL = "request.required_creation"


def declaration(*, semantics="new_occurrence", bindings=True, baseline=False, lookup=False):
    check = {"check_id": "requested-creation", "signal_id": SIGNAL, "role": "goal",
        "operator": "effects.required_when@1", "semantics": semantics, "population": "request", "source": "creates",
        "required_when": comparison("eq", field("request", "request_key"), literal("requested-task")),
        "effect_match": {"op": "all", "args": [
            comparison("eq", field("effect", "name"), field("request", "name")),
            comparison("eq", field("effect", "project"), field("request", "project"))]}}
    if baseline:
        check["initially_satisfied_when"] = comparison("eq", field("request", "request_key"), literal("requested-task"))
    if lookup:
        check["lookups"] = [{"source": "request", "alias": "authored", "keys": {"request_key": field("request", "request_key")}}]
    return load_contract(canonical_json({"schema_version": 1, "manifest_id": "manufactured-request-native", "revision": "1",
        "public_request": PROMPT[0]["content"],
        "bindings": [{"path": ["task_evidence", "prompt"], "canonical_sha256": digest(PROMPT)}] if bindings else [],
        "sources": {"request": {"adapter": "public.request@1", "member_key": "requested-task", "fields": {
            "name": {"value": "Provision person@example.com", "authority_paths": [["task_evidence", "prompt", 0, "content"]]},
            "project": {"value": "project-access", "authority_paths": [["task_evidence", "prompt"]]}}},
            "creates": {"adapter": "asana.actions@1", "kind": "create_task"}},
        "checks": [check], "credit": [{"check": check["check_id"], "policy": "required_effect_once@1", "channel": "useful-action"}]}))


def scored(monkeypatch, *, calls=None, missing_ack=None, prompt=None, bindings=True):
    contract = declaration(bindings=bindings)
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    task, episode, trace = native_fixture(run_operations(world(), calls if calls is not None else [create()]), missing_ack=missing_ack)
    public = PROMPT if prompt is None else prompt
    data = AutomationBenchData.model_validate({**task.data.model_dump(mode="json"), "prompt": public})
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    trace.task = trace.task.model_copy(update={"data": data})
    episode = vf.WireEpisode.model_validate({"task": trace.task.model_dump(mode="json"), "traces": [trace.model_dump(mode="json")]})
    retained = cast(Any, episode.traces[0])
    retained.state = trace.state
    scalar = copy.deepcopy(retained.rewards)
    asyncio.run(task.score(retained))
    assert retained.rewards == scalar
    return task, episode, retained


def goals(trace):
    return [record for record in terminal_records(trace) if record.signal.signal_id == SIGNAL]


@pytest.mark.parametrize("options,reason", [({"semantics": "occurrence"}, "request_population_requires_new_occurrence"),
    ({"baseline": True}, "new_occurrence_has_no_initial_discharge"),
    ({"lookup": True}, "request_population_lookup_unsupported")])
def test_request_source_only_main_new_occurrence_population(options, reason):
    with pytest.raises(ValueError, match=reason):
        declaration(**options)


def test_native_score_rescore_reload_keeps_exact_recipient_scalar_and_once_only_credit(monkeypatch):
    task, episode, trace = scored(monkeypatch, calls=[create(email="unrelated@example.com"), create(), create()])
    assert not trace.assessment_errors and not trace.credit_errors
    assert len(goals(trace)) == 1 and goals(trace)[0].status == "valid" and goals(trace)[0].value == 1
    parts = penalties(trace)
    assert len(parts) == 1 and parts[0].recipient.execution.invocation_id == "execution-1"
    assert parts[0].parent_assessment_ids == (goals(trace)[0].assessment_id,)
    assert parts[0].transformation == "required_effect_identity@1"
    original = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == original
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    reloaded = cast(Any, restored.traces[0])
    reloaded.state = trace.state
    asyncio.run(task.score(reloaded))
    assert tuple(reloaded.credit_assignments) == original and reloaded.rewards == trace.rewards
    assert not reloaded.assessment_errors and not reloaded.credit_errors


@pytest.mark.parametrize("options,status,value", [
    ({"calls": [create(email="other@example.com")]}, "valid", 0),
    ({"missing_ack": 0}, "abstained", None),
    ({"bindings": False}, "abstained", None),
    ({"prompt": [{"role": "system", "content": PROMPT[0]["content"]}]}, "abstained", None)])
def test_missing_authority_or_ack_never_hides_obligation_or_credits_it(monkeypatch, options, status, value):
    _, _, trace = scored(monkeypatch, **options)
    assert len(goals(trace)) == 1
    assert (goals(trace)[0].status, goals(trace)[0].value) == (status, value)
    assert not penalties(trace) and not trace.assessment_errors and not trace.credit_errors


def test_coherent_foreign_prompt_and_recaptured_request_cannot_publish(monkeypatch):
    original = ManifestAssessmentTask.assessment_requests
    def forged(self, source):
        result = []
        for name, request in original(self, source):
            view = request.views[0]
            material = json.loads(view.input_json)
            material["source"]["task_evidence"]["prompt"][0]["content"] = "Foreign prompt"
            material.update(capture_obligation_inputs(material["source"], declaration()))
            config = json.loads(request.run.configuration_json)
            config["source_digest"] = digest(material["source"])
            replacement = vf.ObservationView.capture(material, snapshot_id=source.snapshot_id,
                builder_revision=view.builder_revision, scope=view.scope, subjects=view.subjects)
            result.append((name, request.model_copy(update={"views": (replacement,), "run": request.run.model_copy(
                update={"configuration_json": canonical_json(config)})})))
        return result
    monkeypatch.setattr(ManifestAssessmentTask, "assessment_requests", forged)
    _, _, trace = scored(monkeypatch)
    assert not goals(trace) and not penalties(trace)
    assert any(batch.run.status == "failed" for batch in trace.assessment_batches)


def test_projector_recomputes_coherently_retargeted_witness_from_sealed_raw_source(monkeypatch):
    task, _, trace = scored(monkeypatch, calls=[create(), create(email="unrelated@example.com")])
    request = trace.credit_assignments[0].request
    config = json.loads(request.rule.configuration_json)
    raw = json.loads(request.source.source_json)
    safe = {"task_evidence": raw["task_evidence"], "tool_execution_events": raw.get("tool_execution_events", []),
            "state_write_receipts": raw.get("state_write_receipts", [])}
    effects = json.loads(capture_obligation_inputs(safe, declaration())["obligation_effect_evidence_json"])["creates"]["effects"]
    unrelated = next(effect for effect in effects if effect["invocation_id"] == "execution-1")
    assert unrelated["status"] == "qualified" and unrelated["effect_id"]
    config["allocation_witness"]["occurrence"] = "execution-1"
    config["allocation_witness"]["effect_id"] = unrelated["effect_id"]
    recipient = execution_subject(request.source, "execution-1")
    forged = request.model_copy(update={"rule": request.rule.model_copy(update={"configuration_json": canonical_json(config)}),
        "targets": (request.targets[0].model_copy(update={"recipient": recipient}),)})
    with pytest.raises(ValueError, match="allocation_proof"):
        asyncio.run(manifest_obligation_identity(task, forged))
    with pytest.raises(ValueError, match="source_proof"):
        asyncio.run(manifest_obligation_identity(task, request.model_copy(update={"source": request.source.identity})))
