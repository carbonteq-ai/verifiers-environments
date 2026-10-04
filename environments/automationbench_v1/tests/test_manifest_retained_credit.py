"""Native completion credit: manufactured simulator policy, not benchmark claims."""

import asyncio
import copy
import json
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import native_fixture, penalties
from test_manifest_retained import check
from test_manifest_retained_assessments import declared, findings
from test_manifest_sheet_effects import initial, update
from test_notification_evidence import run_operations

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_guard_assessments import execution_subject
from automationbench_v1.manifest_retained_assessments import (
    RETAINED_OUTPUT,
    manifest_retained_identity,
)


def contract(selected=None, fields=("Amount",), channel="completion"):
    raw = declared(selected).model_dump(mode="json")
    raw["credit"] = [{"check": "balance", "policy": "retained_completion_once@1",
                      "channel": channel, "goal_fields": fields}]
    return load_contract(canonical_json(raw))


def scored(monkeypatch, *, calls=None, public=None, selected=None, missing_ack=None, declaration=None):
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declaration or contract(selected))
    task, episode, trace = native_fixture(run_operations(public or initial(), calls if calls is not None else [update()]),
                                         missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar
    return task, episode, trace


def assert_clean(trace):
    assert not trace.assessment_errors and not trace.credit_errors
    assert not [batch for batch in trace.assessment_batches if batch.run.status in {"failed", "interrupted"}]


def test_completion_uses_exact_execution_and_reload_consumes_once(monkeypatch):
    task, episode, trace = scored(monkeypatch)
    assert_clean(trace)
    contribution = penalties(trace)[0]
    assert contribution.value == 1 and contribution.transformation == "retained_completion_identity@1"
    assert contribution.recipient.execution.invocation_id == "execution-0"
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert_clean(replay)
    assert len(penalties(replay)) == 1


@pytest.mark.parametrize("calls,witness", [([update(), update(cells={"Name": "Renamed"})], "execution-1"),
    ([update(cells={"Amount": "$20", "Name": "Renamed"})], "execution-0")])
def test_split_or_combined_completes_one_goal(monkeypatch, calls, witness):
    selected = check(retained_when={"op": "all", "args": [check().retained_when.model_dump(mode="json"),
        {"op": "eq", "left": {"kind": "field", "path": ["retained", "Name"], "domain": "string"},
         "right": {"kind": "literal", "value": "Renamed"}}]})
    _, _, trace = scored(monkeypatch, calls=calls, declaration=contract(selected, fields=("Amount", "Name")))
    assert_clean(trace)
    assert len(penalties(trace)) == 1
    assert penalties(trace)[0].recipient.execution.invocation_id == witness


@pytest.mark.parametrize("amounts,count,witness", [(["$20", "$30"], 0, None),
    (["$20", "$30", "$20"], 1, "execution-2"), (["$20", "$20"], 1, "execution-0"), ([], 0, None)])
def test_damage_repair_noop_and_empty_history(monkeypatch, amounts, count, witness):
    _, _, trace = scored(monkeypatch, calls=[update(cells={"Amount": value}) for value in amounts])
    assert_clean(trace)
    assert len(penalties(trace)) == count
    if witness:
        assert penalties(trace)[0].recipient.execution.invocation_id == witness


def test_initially_correct_break_restore_never_mints_progress(monkeypatch):
    public = initial()
    public["google_sheets"]["rows"][0]["cells"]["Amount"] = "$20"
    _, _, trace = scored(monkeypatch, public=public, calls=[update(cells={"Amount": "$30"}), update()])
    assert_clean(trace)
    assert findings(trace)[0].value == 1 and not penalties(trace)


def test_notes_write_after_completion_cannot_steal_recipient(monkeypatch):
    _, _, trace = scored(monkeypatch, calls=[update(), update(cells={"Notes": "Reviewed"})])
    assert_clean(trace)
    assert penalties(trace)[0].recipient.execution.invocation_id == "execution-0"


def test_missing_ack_outcome_success_has_no_completion_recipient(monkeypatch):
    _, _, trace = scored(monkeypatch, missing_ack=0)
    assert_clean(trace)
    assert findings(trace)[0].value == 1 and not penalties(trace)


def test_missing_unrelated_later_ack_preserves_known_completion(monkeypatch):
    _, _, trace = scored(monkeypatch, calls=[update(), update(cells={"Notes": "Reviewed"})], missing_ack=1)
    assert_clean(trace)
    assert findings(trace)[0].value == 1
    assert penalties(trace)[0].recipient.execution.invocation_id == "execution-0"


def test_unknown_initial_goal_is_not_laundered_through_break_restore(monkeypatch):
    public = initial()
    del public["google_sheets"]["rows"][0]["cells"]["Amount"]
    _, _, trace = scored(monkeypatch, public=public, calls=[update(cells={"Amount": "$30"}), update()])
    assert_clean(trace)
    assert findings(trace)[0].value == 1 and not penalties(trace)


@pytest.mark.parametrize("mutation,expected", [("move", 1), ("replace", 0)])
def test_completion_requires_original_record_even_after_position_change(monkeypatch, mutation, expected):
    def changed(world):
        if mutation == "move":
            world.google_sheets.rows[0].row_id = 3
        else:
            world.google_sheets.rows[0].id = "replacement"
        return {"success": True}
    _, _, trace = scored(monkeypatch, calls=[update(), ("custom_mutation_fixture", {}, changed)])
    assert_clean(trace)
    assert len(penalties(trace)) == expected


def test_failed_current_outcome_attempt_cannot_reuse_successful_parent(monkeypatch):
    original = ManifestAssessmentTask.plan_credit
    def failed(self, source, assessments, context):
        changed = tuple(batch.model_copy(update={"run": batch.run.model_copy(update={"status": "failed"})})
                        for batch in assessments)
        return original(self, source, changed, context)
    monkeypatch.setattr(ManifestAssessmentTask, "plan_credit", failed)
    _, _, trace = scored(monkeypatch)
    assert not penalties(trace)


def test_changed_witness_does_not_reset_stable_consumption(monkeypatch):
    _, _, prefix = scored(monkeypatch)
    task, _, extended = native_fixture(run_operations(initial(), [update(), update(cells={"Amount": "$30"}), update()]))
    extended.id = prefix.id
    extended.credit_assignments = prefix.credit_assignments
    asyncio.run(task.score(extended))
    assert_clean(extended)
    assert len(penalties(extended)) == 1
    assert penalties(extended)[0].recipient.execution.invocation_id == "execution-0"


def test_direct_projector_retarget_to_other_existing_execution_rejected(monkeypatch):
    _, _, trace = scored(monkeypatch, calls=[update(), update(cells={"Notes": "Reviewed"})])
    request = trace.credit_assignments[0].request
    other = request.targets[0].recipient.execution.model_copy(update={"invocation_id": "execution-1"})
    target = request.targets[0].model_copy(update={"recipient": request.targets[0].recipient.model_copy(update={"execution": other})})
    with pytest.raises(ValueError, match="credit_request_invalid"):
        asyncio.run(manifest_retained_identity(None, request.model_copy(update={"targets": (target,)})))


def test_coherent_config_and_target_retarget_cannot_credit_notes_execution(monkeypatch):
    task, _, trace = scored(monkeypatch, calls=[update(), update(cells={"Notes": "Reviewed"})])
    request = trace.credit_assignments[0].request
    config = json.loads(request.rule.configuration_json)
    config["allocation_witness"].update(occurrence="execution-1", expected_revision=1, applied_revision=2)
    other = execution_subject(request.source, "execution-1")
    altered = request.model_copy(update={
        "rule": request.rule.model_copy(update={"configuration_json": canonical_json(config)}),
        "targets": (request.targets[0].model_copy(update={"recipient": other}),)})
    with pytest.raises(ValueError, match="allocation_proof_mismatch"):
        asyncio.run(manifest_retained_identity(task, altered))


@pytest.mark.parametrize("tamper", ["missing", "native_record_id", "value"])
def test_completion_rejects_altered_current_outcome_receipt(monkeypatch, tamper):
    original = ManifestAssessmentTask.plan_credit
    def altered(self, source, assessments, context):
        changed = []
        for batch in assessments:
            receipts = []
            for receipt in batch.run.execution_evidence:
                payload = json.loads(receipt.payload_json)
                if receipt.kind == RETAINED_OUTPUT and payload.get("kind") == "finding":
                    if tamper == "missing":
                        continue
                    payload[tamper] = "foreign" if tamper == "native_record_id" else 0
                    receipt = receipt.model_copy(update={"payload_json": canonical_json(payload)})
                receipts.append(receipt)
            changed.append(batch.model_copy(update={"run": batch.run.model_copy(update={"execution_evidence": tuple(receipts)})}))
        return original(self, source, tuple(changed), context)
    monkeypatch.setattr(ManifestAssessmentTask, "plan_credit", altered)
    _, _, trace = scored(monkeypatch)
    assert trace.credit_errors and not penalties(trace)


def test_two_instances_same_execution_channel_requires_explicit_aggregation(monkeypatch):
    selected = check()
    duplicate = selected.model_dump(mode="json")
    duplicate["check_id"] = "balance-again"
    raw = contract().model_dump(mode="json")
    raw["checks"].append(duplicate)
    raw["credit"].append({"check": "balance-again", "policy": "retained_completion_once@1",
                          "channel": "completion", "goal_fields": ["Amount"]})
    _, _, trace = scored(monkeypatch, declaration=load_contract(canonical_json(raw)))
    assert trace.credit_errors and not penalties(trace)


@pytest.mark.parametrize("channel,expected", [("completion", 0), ("occurrence", 2)])
def test_cross_planner_channels_are_checked_together(monkeypatch, channel, expected):
    raw = contract().model_dump(mode="json")
    raw["checks"].append({"check_id": "update-occurrence", "signal_id": "update.observed", "role": "goal",
        "operator": "effects.required_when@1", "semantics": "new_occurrence", "population": "rows", "source": "writes",
        "required_when": check().required_when.model_dump(mode="json"),
        "effect_match": {"op": "eq", "left": {"kind": "field", "path": ["effect", "native_record_id"], "domain": "string"},
            "right": {"kind": "field", "path": ["candidate", "native_record_id"], "domain": "string"}}})
    raw["credit"].append({"check": "update-occurrence", "policy": "required_effect_once@1", "channel": channel})
    _, _, trace = scored(monkeypatch, declaration=load_contract(canonical_json(raw)))
    assert len(penalties(trace)) == expected
    if expected:
        assert_clean(trace)
    else:
        assert trace.credit_errors


@pytest.mark.parametrize("field,value", [("expected_revision", True), ("applied_revision", True), ("value", True)])
def test_direct_projector_rejects_bool_witness_metadata(monkeypatch, field, value):
    _, _, trace = scored(monkeypatch)
    request = trace.credit_assignments[0].request
    config = json.loads(request.rule.configuration_json)
    config["allocation_witness"][field] = value
    altered = request.model_copy(update={"rule": request.rule.model_copy(update={"configuration_json": canonical_json(config)})})
    with pytest.raises(ValueError):
        asyncio.run(manifest_retained_identity(None, altered))
