"""Real simulator effects in manufactured native envelopes; bounded Luna replay."""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_manifest_guards import comparison, create, field, literal
from test_manifest_obligations import obligation, world
from test_notification_evidence import run_operations
from verifiers.v1.assessment_source import capture_trace_source

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import EffectSource, TableSource, load_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_guard_assessments import digest, execution_subject
from automationbench_v1.manifest_obligation_assessments import (
    OBLIGATION_OUTPUT,
    capture_obligation_inputs,
)
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState


def contract(*, baseline=True, second=False, semantics="occurrence"):
    check = obligation()
    check["semantics"] = semantics
    if not baseline:
        check.pop("initially_satisfied_when")
    checks = [check]
    if second:
        other = copy.deepcopy(check)
        other["check_id"] = "second-obligation"
        checks.append(other)
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "manufactured-obligation-fixture", "revision": "1",
        "public_request": "Provision each qualifying pending request once; initial Fulfilled marks prior completion.",
        "sources": {
            **{name: TableSource(path=("task_evidence", "initial", "google_sheets"),
                spreadsheet_id="sheet", worksheet_id=name, key_fields=("Email",),
                required_fields=("Manager", "Status", "Fulfilled") if name == "queue" else ("Rank",)
            ).model_dump(mode="json") for name in ("queue", "directory")},
            "creates": EffectSource(adapter="asana.actions@1", kind="create_task").model_dump(mode="json")},
        "checks": checks,
        "credit": [{"check": item["check_id"], "policy": "required_effect_once@1", "channel": "useful-action"}
                   for item in checks]}))


def scored(monkeypatch, *, material=None, baseline=True, second=False, missing_ack=None, semantics="occurrence"):
    declared = contract(baseline=baseline, second=second, semantics=semantics)
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, episode, trace = native_fixture(material or run_operations(world(), [create()]), missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar
    return task, episode, trace


def goals(trace):
    return [record for record in terminal_records(trace) if record.signal.signal_id == "access.required_effect"]


def test_coherent_alternate_initial_authority_cannot_publish_false_required_goal(monkeypatch):
    declared = contract()
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    original = ManifestAssessmentTask.assessment_requests
    def substituted(self, source):
        changed = []
        for name, request in original(self, source):
            view = request.views[0]
            material = json.loads(view.input_json)
            material["source"]["task_evidence"]["initial"]["google_sheets"]["rows"][1]["cells"]["Rank"] = 4
            material.update(capture_obligation_inputs(material["source"], declared))
            replacement = vf.ObservationView.capture(material, snapshot_id=source.snapshot_id,
                builder_revision=view.builder_revision, scope=view.scope, subjects=view.subjects)
            config = json.loads(request.run.configuration_json)
            config["source_digest"] = digest(material["source"])
            changed.append((name, request.model_copy(update={"views": (replacement,), "run": request.run.model_copy(
                update={"configuration_json": canonical_json(config)})})))
        return changed
    monkeypatch.setattr(ManifestAssessmentTask, "assessment_requests", substituted)
    task, _, trace = native_fixture(run_operations(world(rank=2), [create()]))
    asyncio.run(task.score(trace))
    assert any(batch.run.status == "failed" for batch in trace.assessment_batches)
    assert not goals(trace) and not penalties(trace)


def test_native_outcome_trace_subject_and_execution_credit_reload_rescore_once(monkeypatch):
    task, episode, trace = scored(monkeypatch)
    assert not trace.assessment_errors and not trace.credit_errors
    assert goals(trace)[0].subject.kind == "trace" and goals(trace)[0].value == 1
    parts = penalties(trace)
    assert len(parts) == 1 and parts[0].value == 1 and parts[0].recipient.kind == "execution"
    assert parts[0].transformation == "required_effect_identity@1"
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    retained = cast(Any, restored.traces[0])
    retained.state = trace.state
    assert retained.assessment_batches == trace.assessment_batches
    asyncio.run(task.score(retained))
    assert not retained.assessment_errors and not retained.credit_errors
    assert len(penalties(retained)) == 1


def test_revision_only_change_cannot_remint_consumed_obligation(monkeypatch):
    task, _, trace = scored(monkeypatch)
    before = tuple(trace.credit_assignments)
    changed = contract().model_dump(mode="json")
    changed["revision"] = "2"
    revised = load_contract(canonical_json(changed))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: revised)
    asyncio.run(task.score(trace))
    assert trace.credit_errors and tuple(trace.credit_assignments) == before
    assert len(penalties(trace)) == 1


@pytest.mark.parametrize("ending", ["failed", "interrupted"])
def test_partial_native_credit_survives_failure_or_cancel_without_remint(monkeypatch, ending):
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract())
    task, episode, trace = native_fixture(run_operations(world(), [create()]))
    original = manifest_assessments.manifest_obligation_identity

    async def yield_then_stop(task, request):
        contributions = await original(task, request)

        async def stream():
            yield contributions[0]
            if ending == "interrupted":
                raise asyncio.CancelledError
            raise RuntimeError("manufactured failure after valid obligation yield")

        return stream()

    monkeypatch.setattr(manifest_assessments, "manifest_obligation_identity", yield_then_stop)
    if ending == "interrupted":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(task.score(trace))
    else:
        asyncio.run(task.score(trace))
    assert [assignment.status for assignment in trace.credit_assignments] == ["running", "partial", ending]
    valid_ids = {part.contribution_id for assignment in trace.credit_assignments
                 for part in assignment.contributions if part.status == "valid"}
    assert len(valid_ids) == 1
    before = tuple(trace.credit_assignments)
    monkeypatch.setattr(manifest_assessments, "manifest_obligation_identity", original)
    asyncio.run(task.score(trace))
    assert tuple(trace.credit_assignments) == before
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    retained = cast(Any, restored.traces[0])
    retained.state = trace.state
    asyncio.run(task.score(retained))
    assert retained.credit_assignments == trace.credit_assignments


@pytest.mark.parametrize("initial_fulfilled,baseline,expected_credit", [(True, True, 0), (False, False, 0), (False, True, 1)])
def test_baseline_controls_credit_independently_of_witnessed_outcome(monkeypatch, initial_fulfilled, baseline, expected_credit):
    _, _, trace = scored(monkeypatch, material=run_operations(world(fulfilled=initial_fulfilled), [create()]), baseline=baseline)
    assert not trace.assessment_errors and not trace.credit_errors
    assert goals(trace)[0].value == 1 and len(penalties(trace)) == expected_credit


def test_repeated_native_creates_only_one_obligation_credit(monkeypatch):
    _, _, trace = scored(monkeypatch, material=run_operations(world(), [create(), create()]))
    assert not trace.assessment_errors and not trace.credit_errors
    assert len(penalties(trace)) == 1
    assert penalties(trace)[0].recipient.execution.invocation_id == "execution-0"


def test_explicit_new_occurrence_mode_credits_requested_fresh_action_without_state_baseline(monkeypatch):
    _, _, trace = scored(monkeypatch, baseline=False, semantics="new_occurrence",
                         material=run_operations(world(fulfilled=True), [create(), create()]))
    assert not trace.assessment_errors and not trace.credit_errors
    assert goals(trace)[0].value == 1 and len(penalties(trace)) == 1


def test_closed_missing_required_occurrence_is_zero_without_credit(monkeypatch):
    _, _, trace = scored(monkeypatch, material=run_operations(world(), [create(email="other@example.com")]))
    assert not trace.assessment_errors and not trace.credit_errors
    assert goals(trace)[0].value == 0 and not penalties(trace)


def test_known_witness_survives_later_ack_gap(monkeypatch):
    _, _, trace = scored(monkeypatch, material=run_operations(world(), [create(), create()]), missing_ack=1)
    assert not trace.assessment_errors and not trace.credit_errors
    assert goals(trace)[0].value == 1 and len(penalties(trace)) == 1


def test_inapplicable_and_missing_ack_do_not_become_zero_or_credit(monkeypatch):
    _, _, inapplicable = scored(monkeypatch, material=run_operations(world(rank=1), [create()]))
    assert goals(inapplicable)[0].status == "inapplicable" and goals(inapplicable)[0].value is None
    assert not penalties(inapplicable)
    _, _, missing_ack = scored(monkeypatch, missing_ack=0)
    assert goals(missing_ack)[0].status == "abstained" and not penalties(missing_ack)


def test_two_same_channel_obligations_require_explicit_aggregation(monkeypatch):
    _, _, trace = scored(monkeypatch, second=True)
    assert trace.credit_errors and not penalties(trace)


def test_failed_current_run_never_authorizes_stale_outcome(monkeypatch):
    original = ManifestAssessmentTask.plan_credit
    def failed(self, source, assessments, context):
        changed = tuple(batch.model_copy(update={"run": batch.run.model_copy(update={"status": "failed"})})
                        for batch in assessments)
        return original(self, source, changed, context)
    monkeypatch.setattr(ManifestAssessmentTask, "plan_credit", failed)
    _, _, trace = scored(monkeypatch)
    assert not penalties(trace)


@pytest.mark.parametrize("tamper", ["omit", "baseline", "semantics", "input_digest", "candidate_identity"])
def test_credit_rejects_missing_or_altered_receipt(monkeypatch, tamper):
    original = ManifestAssessmentTask.plan_credit
    def altered(self, source, assessments, context):
        changed = []
        for batch in assessments:
            if json.loads(batch.run.configuration_json)["instance_key"] == "scope":
                changed.append(batch)
                continue
            evidence = []
            for receipt in batch.run.execution_evidence:
                if receipt.kind != OBLIGATION_OUTPUT:
                    evidence.append(receipt)
                    continue
                if tamper == "omit":
                    continue
                payload = json.loads(receipt.payload_json)
                if tamper == "baseline":
                    payload["initially_satisfied"] = True
                elif tamper == "semantics":
                    payload["semantics"] = "new_occurrence"
                elif tamper == "input_digest":
                    payload["input_digest"] = "0" * 64
                else:
                    payload["candidate_identity"][-1] = "different-native-id"
                evidence.append(receipt.model_copy(update={"payload_json": canonical_json(payload)}))
            changed.append(batch.model_copy(update={"run": batch.run.model_copy(update={"execution_evidence": tuple(evidence)})}))
        return original(self, source, tuple(changed), context)
    monkeypatch.setattr(ManifestAssessmentTask, "plan_credit", altered)
    _, _, trace = scored(monkeypatch)
    assert trace.credit_errors and not penalties(trace)


def test_scope_output_and_parent_cannot_together_invent_complete_coverage(monkeypatch):
    original = ManifestAssessmentTask.plan_credit
    def altered(self, source, assessments, context):
        changed = []
        for batch in assessments:
            if json.loads(batch.run.configuration_json)["instance_key"] != "scope":
                changed.append(batch)
                continue
            evidence = []
            for receipt in batch.run.execution_evidence:
                if receipt.kind == OBLIGATION_OUTPUT:
                    payload = json.loads(receipt.payload_json)
                    payload.update(status="valid", value=1, reason="invented_closed_scope")
                    receipt = receipt.model_copy(update={"payload_json": canonical_json(payload)})
                evidence.append(receipt)
            parent = batch.assessments[0].model_copy(update={"status": "valid", "value": 1, "reason": "invented_closed_scope"})
            changed.append(batch.model_copy(update={"assessments": (parent,),
                "run": batch.run.model_copy(update={"execution_evidence": tuple(evidence)})}))
        return original(self, source, tuple(changed), context)
    monkeypatch.setattr(ManifestAssessmentTask, "plan_credit", altered)
    _, _, trace = scored(monkeypatch, missing_ack=0)
    assert trace.credit_errors and not penalties(trace)


def test_direct_credit_hook_rejects_retarget_to_other_native_execution(monkeypatch):
    original = ManifestAssessmentTask.plan_credit
    def altered(self, source, assessments, context):
        requests = original(self, source, assessments, context)
        recipient = execution_subject(source, "execution-1")
        assert recipient is not None
        return [(name, request.model_copy(update={"targets": (request.targets[0].model_copy(update={"recipient": recipient}),)}))
                for name, request in requests]
    monkeypatch.setattr(ManifestAssessmentTask, "plan_credit", altered)
    _, _, trace = scored(monkeypatch, material=run_operations(world(), [create(), create()]))
    assert not penalties(trace) and any(assignment.status == "failed" for assignment in trace.credit_assignments)


def test_consumption_identity_survives_changed_allocation_witness(monkeypatch):
    task, _, trace = scored(monkeypatch, material=run_operations(world(), [create(), create()]))
    assert len(penalties(trace)) == 1
    # A retained earlier allocation may select the other genuine qualified
    # witness. The stable obligation identity, not that choice, prevents minting.
    assignment = trace.credit_assignments[-1]
    config = json.loads(assignment.request.rule.configuration_json)
    outputs = [json.loads(receipt.payload_json) for batch in trace.assessment_batches
               for receipt in batch.run.execution_evidence if receipt.kind == OBLIGATION_OUTPUT
               and json.loads(receipt.payload_json)["kind"] == "finding"]
    second = outputs[0]["witnesses"][1]
    config["allocation_witness"] = {"occurrence": second["occurrence"], "effect_id": second["effect_id"]}
    source = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    recipient = execution_subject(source, second["occurrence"])
    assert recipient is not None
    rule = assignment.request.rule.model_copy(update={"configuration_json": canonical_json(config)})
    target = assignment.request.targets[0].model_copy(update={"recipient": recipient})
    contribution = assignment.contributions[0].model_copy(update={"recipient": recipient})
    previous = assignment.model_copy(update={"request": assignment.request.model_copy(update={"rule": rule, "targets": (target,)}),
                                               "contributions": (contribution,)})
    trace.credit_assignments = (*trace.credit_assignments[:-1], previous)
    asyncio.run(task.score(trace))
    assert not trace.credit_errors and len(penalties(trace)) == 1


def test_actual_sha_bound_luna_delivery_check_is_bounded_and_no_unknown_baseline_credit(monkeypatch):
    index = Path("/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate/cross-category-selection.json")
    if not index.exists():
        pytest.skip("retained development source index unavailable")
    selected = next(item for item in json.loads(index.read_text())["tasks"]
                    if item["task_name"] == "simple.email_airtable_customer_welcome")
    path = Path(selected["source_episode_path"])
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == selected["source_episode_sha256"]
    episode = vf.WireEpisode.model_validate_json(raw)
    trace = cast(Any, episode.traces[0])
    data = AutomationBenchData.model_validate(episode.task.data.model_dump(mode="json"))
    trace.state = AutomationBenchState(world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state, assertions=data.assertions)
    # Recipient is explicitly present in the public onboarding message. This
    # checks delivery only, not welcome prose quality or the Airtable obligation.
    body = data.initial_state["gmail"]["messages"][0]["body_plain"]
    declared = load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "recorded-onboarding-delivery", "revision": "1",
        "public_request": "Deliver the requested message to the onboarding customer email.",
        "bindings": [{"path": ["task_evidence", "initial", "gmail", "messages", 0, "body_plain"],
                      "canonical_sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}],
        "sources": {
            "messages": {"adapter": "initial.records@1",
                "path": ["task_evidence", "initial", "gmail", "messages"],
                "fields": {"SourceId": ["id"]}, "key_fields": ["SourceId"]},
            "sends": {"adapter": "gmail.messages@1", "kind": "send"}},
        "checks": [{"check_id": "delivery", "signal_id": "onboarding.delivery", "role": "goal",
            "operator": "effects.required_when@1", "population": "messages", "source": "sends",
            "required_when": comparison("eq", field("request", "SourceId", domain="string"), literal("msg_3183")),
            "effect_match": comparison("in", literal("lucas.grant@pinnacle.example.com"),
                                       field("effect", "to", domain="sequence"))}],
        "credit": [{"check": "delivery", "policy": "required_effect_once@1", "channel": "delivery"}]}))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    records = terminal_records(trace)
    assert next(record for record in records if record.signal.signal_id == "onboarding.delivery").value == 1
    assert not penalties(trace) and path.read_bytes() == raw
