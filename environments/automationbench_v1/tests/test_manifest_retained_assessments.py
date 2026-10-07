"""Native retained outcomes: real simulator states and a bounded Luna replay."""

import asyncio
import copy
import json
from dataclasses import replace
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
from test_manifest_retained import check, table
from test_manifest_sheet_effects import initial, spec, update
from test_notification_evidence import run_operations
from test_prepaid_manifest_guard import contract as prepaid_guard_contract
from test_prepaid_manifest_guard import recorded

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_guard_assessments import digest
from automationbench_v1.manifest_retained_assessments import (
    RETAINED_OUTPUT,
    assess_retained,
    capture_retained_inputs,
)
from automationbench_v1.taskset import AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState


def declared(selected=None):
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "manufactured-native-retained-row", "revision": "1",
        "public_request": "Retain the requested balance in the original schedule row.",
        "sources": {"rows": table().model_dump(mode="json"), "writes": spec().model_dump(mode="json")},
        "checks": [(selected or check()).model_dump(mode="json")], "credit": [],
    }))


def scored(monkeypatch, *, material=None, selected=None, missing_ack=None, contract=None):
    contract = contract or declared(selected)
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    task, episode, trace = native_fixture(material or run_operations(initial(), [update()]), missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar
    return task, episode, trace


def failed_runs(trace):
    return [batch for batch in trace.assessment_batches if batch.run.status in {"failed", "interrupted"}]


def findings(trace):
    return [record for record in terminal_records(trace) if record.signal.signal_id == "balance.retained"]


def test_native_retained_outcome_reload_rescore_without_invented_credit(monkeypatch):
    task, episode, trace = scored(monkeypatch)
    assert not trace.assessment_errors and not trace.credit_errors
    assert not failed_runs(trace)
    assert findings(trace)[0].value == 1 and findings(trace)[0].subject.kind == "trace"
    assert not penalties(trace)
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    assert replay.assessment_batches == trace.assessment_batches
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors and not penalties(replay)
    assert findings(replay)[-1].value == 1


@pytest.mark.parametrize("amounts,expected", [(["$20", "$30"], 0), (["$20", "$30", "$20"], 1), ([], 0)])
def test_terminal_state_controls_outcome_after_damage_or_repair(monkeypatch, amounts, expected):
    _, _, trace = scored(monkeypatch, material=run_operations(initial(), [update(cells={"Amount": amount}) for amount in amounts]))
    assert not trace.assessment_errors and not trace.credit_errors
    assert findings(trace)[0].value == expected and not penalties(trace)


def test_split_and_combined_native_updates_share_one_retained_goal(monkeypatch):
    selected = check(retained_when={"op": "all", "args": [check().retained_when.model_dump(mode="json"),
        {"op": "eq", "left": {"kind": "field", "path": ["retained", "Name"], "domain": "string"},
         "right": {"kind": "literal", "value": "Renamed"}}]})
    for calls in ([update(cells={"Amount": "$20", "Name": "Renamed"})], [update(), update(cells={"Name": "Renamed"})]):
        _, _, trace = scored(monkeypatch, selected=selected, material=run_operations(initial(), calls))
        assert findings(trace)[0].value == 1 and not penalties(trace)


def test_missing_action_ack_does_not_erase_known_final_state_or_invent_credit(monkeypatch):
    _, _, trace = scored(monkeypatch, missing_ack=0)
    assert not trace.assessment_errors and not trace.credit_errors
    assert findings(trace)[0].value == 1 and not penalties(trace)


def test_initially_correct_state_is_an_outcome_without_action_credit(monkeypatch):
    public = initial()
    public["google_sheets"]["rows"][0]["cells"]["Amount"] = "$20"
    _, _, trace = scored(monkeypatch, material=run_operations(public, []))
    assert findings(trace)[0].value == 1 and not penalties(trace)


@pytest.mark.parametrize("mutation,expected", [("delete", 0), ("replace", 0), ("rename", 1)])
def test_original_native_identity_survives_rename_but_not_same_position_replacement(monkeypatch, mutation, expected):
    def mutate(world):
        if mutation == "delete":
            world.google_sheets.rows.clear()
        elif mutation == "replace":
            world.google_sheets.rows[0].id = "different-native-record"
        else:
            world.google_sheets.rows[0].cells["Name"] = "Renamed"
        return {"success": True}
    material = run_operations(initial(), [update(), ("custom-state-fixture", {}, mutate)])
    _, _, trace = scored(monkeypatch, material=material)
    assert findings(trace)[0].value == expected and not penalties(trace)


@pytest.mark.parametrize("unknown", ["final-field", "identity-proof"])
def test_unknown_fields_or_original_identity_are_unavailable(monkeypatch, unknown):
    material = run_operations(initial(), [update()])
    if unknown == "final-field":
        del material["task_evidence"]["final"]["google_sheets"]["rows"][0]["cells"]["Amount"]
    else:
        del material["task_evidence"]["initial"]["google_sheets"]["rows"][0]["id"]
    _, _, trace = scored(monkeypatch, material=material, missing_ack=0 if unknown == "identity-proof" else None)
    assert findings(trace)[0].status == "abstained" and findings(trace)[0].value is None
    assert not penalties(trace)


def test_inapplicable_status_is_preserved(monkeypatch):
    selected = check(required_when={"op": "eq", "left": {"kind": "literal", "value": True},
                                  "right": {"kind": "literal", "value": False}})
    _, _, trace = scored(monkeypatch, selected=selected)
    assert findings(trace)[0].status == "inapplicable" and findings(trace)[0].value is None


def test_instance_budget_reports_unavailable_scope_without_silent_extra_rows(monkeypatch):
    material = initial()
    other = copy.deepcopy(material["google_sheets"]["rows"][0])
    other.update(id="second", row_id=3)
    other["cells"]["Name"] = "Second"
    material["google_sheets"]["rows"].append(other)
    _, _, trace = scored(monkeypatch, selected=check(max_instances=1), material=run_operations(material, [update()]))
    assert not findings(trace)
    scope = next(record for record in terminal_records(trace) if record.signal.signal_id.endswith(".coverage"))
    assert scope.status == "abstained" and not penalties(trace)


@pytest.mark.parametrize("tamper", ["retention", "population", "boolean-budget", "candidate"])
def test_native_handler_rejects_coherent_projection_and_configuration_tamper(monkeypatch, tamper):
    original = ManifestAssessmentTask.assessment_requests
    def altered(self, source):
        changed = []
        for name, request in original(self, source):
            if tamper in {"retention", "population"}:
                view = request.views[0]
                material = json.loads(view.input_json)
                key = "retained_row_evidence_json" if tamper == "retention" else "retained_population_evidence_json"
                data = json.loads(material[key])
                row = next(iter(data.values()))["rows"][0]
                row["cells_json"] = canonical_json({"Name": "Item", "Amount": "$999"})
                material[key] = canonical_json(data)
                new_view = vf.ObservationView.capture(material, snapshot_id=source.snapshot_id,
                    builder_revision=view.builder_revision, scope=view.scope, subjects=view.subjects)
                request = request.model_copy(update={"views": (new_view,)})
            else:
                config = json.loads(request.run.configuration_json)
                if tamper == "boolean-budget":
                    config["potential_instances"] = True
                elif config["candidate_identity"] is not None:
                    config["candidate_identity"][-1] = 999
                request = request.model_copy(update={"run": request.run.model_copy(update={"configuration_json": canonical_json(config)})})
            changed.append((name, request))
        return changed
    monkeypatch.setattr(ManifestAssessmentTask, "assessment_requests", altered)
    _, _, trace = scored(monkeypatch)
    assert failed_runs(trace) and not penalties(trace)


def test_changed_bound_public_source_abstains_instead_of_reusing_valid_terminal_state(monkeypatch):
    contract = declared().model_dump(mode="json")
    contract["bindings"] = [{"path": ["task_evidence", "initial", "google_sheets", "rows", 0, "cells", "Amount"],
                             "canonical_sha256": digest("$10")}]
    material = initial()
    material["google_sheets"]["rows"][0]["cells"]["Amount"] = "$11"
    _, _, trace = scored(monkeypatch, contract=load_contract(canonical_json(contract)), material=run_operations(material, [update()]))
    assert not failed_runs(trace) and not trace.credit_errors
    assert findings(trace)[0].status == "abstained" and findings(trace)[0].value is None
    assert not penalties(trace)


def test_self_consistent_alternate_source_cannot_publish_forged_retained_success(monkeypatch):
    contract = declared()
    original = ManifestAssessmentTask.assessment_requests
    def substituted(self, source):
        result = []
        for name, request in original(self, source):
            view = request.views[0]
            material = json.loads(view.input_json)
            material["source"]["task_evidence"]["final"]["google_sheets"]["rows"][0]["cells"]["Amount"] = "$20"
            material.update(capture_retained_inputs(material["source"], contract))
            replacement = vf.ObservationView.capture(material, snapshot_id=source.snapshot_id,
                builder_revision=view.builder_revision, scope=view.scope, subjects=view.subjects)
            config = json.loads(request.run.configuration_json)
            config["source_digest"] = digest(material["source"])
            request = request.model_copy(update={"views": (replacement,), "run": request.run.model_copy(
                update={"configuration_json": canonical_json(config)})})
            result.append((name, request))
        return result
    monkeypatch.setattr(ManifestAssessmentTask, "assessment_requests", substituted)
    _, _, trace = scored(monkeypatch, material=run_operations(initial(), []), contract=contract)
    assert failed_runs(trace)
    assert not findings(trace), "forged success must be rejected before any assessment is retained"
    assert not penalties(trace)


@pytest.mark.parametrize("wire", ["input_json", "source_json"])
def test_admission_cache_hit_checks_exact_wire_before_reusing_evaluation(monkeypatch, wire):
    calls = []
    def altered(task, request, context):
        cache = task.__dict__.get("_manifest_source_admission_cache", {})
        if cache:
            key, admission = next(iter(cache.items()))
            # The second member/scope uses this exact sealed view. A corrupted
            # private cache entry cannot replace either authenticated wire body.
            cache[key] = replace(admission, **{wire: getattr(admission, wire) + " "})
        calls.append(bool(cache))
        return assess_retained(task, request, context)
    monkeypatch.setattr(manifest_assessments, "assess_retained", altered)
    _, _, trace = scored(monkeypatch, material=run_operations(initial(), []))
    assert calls == [False, True]
    assert failed_runs(trace)
    assert findings(trace)[0].value == 0 and not penalties(trace)


@pytest.mark.parametrize("tamper", ["scope", "goal", "omit"])
def test_current_outcome_validation_rejects_false_or_missing_receipts_without_credit(monkeypatch, tamper):
    original = ManifestAssessmentTask.plan_credit
    def altered(self, source, batches, context):
        changed = []
        for batch in batches:
            config = json.loads(batch.run.configuration_json)
            scope = config["instance_key"] == "scope"
            if scope != (tamper == "scope"):
                changed.append(batch)
                continue
            receipts = []
            parent = batch.assessments[0]
            for receipt in batch.run.execution_evidence:
                if receipt.kind != RETAINED_OUTPUT:
                    receipts.append(receipt)
                    continue
                if tamper == "omit":
                    continue
                payload = json.loads(receipt.payload_json)
                payload.update(status="valid", value=0, reason="invented-current-result")
                receipts.append(vf.ExecutionEvidence.capture(RETAINED_OUTPUT, payload, invocation_id=batch.run.invocation_id))
                parent = parent.model_copy(update={"status": "valid", "value": 0, "reason": "invented-current-result"})
            changed.append(batch.model_copy(update={"run": batch.run.model_copy(update={"execution_evidence": tuple(receipts)}),
                                                    "assessments": (parent,)}))
        return original(self, source, tuple(changed), context)
    monkeypatch.setattr(ManifestAssessmentTask, "plan_credit", altered)
    _, _, trace = scored(monkeypatch)
    assert trace.credit_errors and not penalties(trace)


def test_actual_sha_bound_luna_prepaid_outcome_only_public_ineligible_preservation(monkeypatch):
    path, original_bytes, episode, trace, data = recorded("finance.prepaid_amortization")
    public = prepaid_guard_contract().model_dump(mode="json")
    guard = public["checks"][0]
    public.update(manifest_id="development-prepaid-ineligible-retained-component", credit=[])
    public["checks"] = [{"check_id": "ineligible-balances-retained", "signal_id": "development.prepaid_ineligible_retained",
        "role": "goal", "operator": "sheets.retained_when@1", "population": guard["population"], "source": guard["source"],
        "required_when": copy.deepcopy(guard["prohibited_when"]), "retained_when": {"op": "all", "args": [
            {"op": "eq", "left": {"kind": "derived", "expression": {"kind": "input", "format": "usd_string", "path": ["retained", field]}},
             "right": {"kind": "derived", "expression": {"kind": "input", "format": "usd_string", "path": ["request", field]}}}
            for field in ("Amortized to Date", "Remaining")]} }]
    contract = load_contract(canonical_json(public))
    assert contract.bindings and not contract.credit
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    trace.state = AutomationBenchState(world=trace.info["automationbench"]["end_state"], initial_state=data.initial_state,
                                      assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors and not penalties(trace)
    records = [record for record in terminal_records(trace) if record.signal.signal_id == "development.prepaid_ineligible_retained"]
    assert sum(record.value == 1 for record in records) == 2
    assert sum(record.status == "inapplicable" for record in records) == 3
    replay_episode = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, replay_episode.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors and not penalties(replay)
    assert path.read_bytes() == original_bytes
