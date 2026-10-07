"""Real Jira mutations, adversarial captures and manufactured native envelopes.

These are local simulator fixtures, not policy rollouts or whole-task scoring.
"""

import copy
import hashlib
import json
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from pydantic import ValidationError
from test_notification_evidence import run_operations, zapier
from verifiers.v1.mcp.execution import ToolServerReceipt
from verifiers.v1.trace import StateWriteReceipt, ToolServerExecutionEvent

from automationbench.schema.world import WorldState
from automationbench.tools.api.fetch import api_fetch
from automationbench.tools.zapier.jira.actions import (
    jira_create_issue,
    jira_project,
    jira_update_issue,
)
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.jira_effects import (
    JiraEvidence,
    JiraIssueSource,
    capture_jira_evidence,
    validate_jira_evidence,
)


def initial():
    return {"jira": {"actions": {"project": [{"id": "project-wrapper", "action_key": "project",
        "params": {"project": "QA", "project_id": "qa_id", "searchByParameter": "QA"}}]}}}


def create(**changes):
    args = {"project": "QA", "issuetype": "Task", "summary": "Audit dashboard", **changes}
    return zapier("jira_create_issue", args, lambda world: jira_create_issue(world, **args))


def update(status):
    args = {"issueKey": "QA-1", "transition": status}
    return zapier("jira_update_issue", args, lambda world: jira_update_issue(world, **args))


def lookup():
    return zapier("jira_project", {"searchByParameter": "QA"}, lambda world: jira_project(world, "QA"))


def evidence(source, project=None):
    return capture_jira_evidence(source, JiraIssueSource(project_id=project))


def qualified(result):
    return [item for item in result.transitions if item.status == "qualified"]


def mutate_capture(source, index, transform):
    source = copy.deepcopy(source)
    event = source["tool_execution_events"][index]
    receipt = json.loads(event["receipt_json"])
    envelope = json.loads(receipt["evidence_json"][0])
    action = envelope["action"]
    before = json.loads(envelope["snapshots"][action["before_digest"]])
    after = json.loads(envelope["snapshots"][action["after_digest"]])
    result = json.loads(action["result_json"])
    if isinstance(result, str):
        result = json.loads(result)
    transform(action, before, after, result)
    action["result_json"] = canonical_json(json.dumps(result))
    for field, world in (("before_digest", before), ("after_digest", after)):
        text = canonical_json(world)
        digest = hashlib.sha256(text.encode()).hexdigest()
        envelope["snapshots"][digest] = text
        action[field] = digest
    receipt["evidence_json"] = [canonical_json(envelope)]
    event["receipt_json"] = canonical_json(receipt)
    return source


def test_real_create_and_status_repair_keep_separate_issue_audit_identities():
    source = run_operations(initial(), [create(), update("Cancelled"), update("To Do")])
    result = evidence(source)
    assert result.complete and result.initial.closed and result.final.closed
    assert result.initial.all_issue_ids == ()
    creates, damage, repair = qualified(result)
    assert [item.kind for item in (creates, damage, repair)] == ["create", "status_update", "status_update"]
    assert creates.before_issue_json is None and creates.issue_id != creates.audit_id
    assert creates.issue_id == damage.issue_id == repair.issue_id
    assert (creates.expected_revision, repair.applied_revision) == (0, 3)
    assert damage.changed_fields == repair.changed_fields == ("status",)
    assert repair.requested_fields == ("status",)
    assert repair.before_issue_json is not None
    assert json.loads(repair.before_issue_json)["fields"]["status"]["name"] == "Cancelled"
    assert json.loads(result.final.issues[0].issue_json)["fields"]["status"]["name"] == "To Do"
    validate_jira_evidence(result, source, JiraIssueSource())


@pytest.mark.parametrize("project", ["QA", "qa_id"])
def test_public_omitted_collections_and_generated_timestamp_bind_native_initial_anchor(project):
    public = initial()
    source = run_operations(public, [create(project=project)])
    source["task_evidence"]["initial"] = public
    assert evidence(source).complete
    source["task_evidence"]["initial"]["jira"]["actions"]["project"][0]["params"]["project"] = "Other"
    result = evidence(source)
    assert not result.initial.closed and not result.complete
    assert len(qualified(result)) == 1


@pytest.mark.parametrize("missing", ["service", "actions", "final", "complete", "initial_anchor"])
def test_missing_capture_is_not_empty_or_whole_inventory_qualification(missing):
    source = run_operations(initial(), [create()])
    if missing == "service":
        del source["task_evidence"]["initial"]["jira"]
    elif missing == "actions":
        del source["task_evidence"]["final"]["jira"]["actions"]
    elif missing == "initial_anchor":
        source["state_write_receipts"] = []
    else:
        del source["task_evidence"][missing]
    result = evidence(source)
    assert not result.complete
    assert not result.final.closed if missing in {"actions", "final", "complete"} else not result.initial.closed


def test_missing_later_ack_preserves_known_birth_but_opens_history():
    source = run_operations(initial(), [create(), lookup()])
    source["state_write_receipts"].pop()
    result = evidence(source)
    assert not result.complete and len(qualified(result)) == 1
    assert result.final.closed  # final source inventory is separate from attribution history


@pytest.mark.parametrize("fault", ["no_issue", "wrong_type", "wrong_project", "wrong_result_id", "wrong_audit_id", "wrong_audit_params", "bad_timestamp", "local_raised", "local_error"])
def test_ack_and_log_cannot_replace_matching_native_issue_and_operation(fault):
    def damage(action, _before, after, result):
        issue = after["jira"]["issues"][0]
        record = after["jira"]["actions"]["create_issue"][0]
        if fault == "no_issue":
            after["jira"]["issues"] = []
        elif fault == "wrong_type":
            issue["fields"]["issuetype"]["name"] = "Bug"
            result["results"][0]["fields"] = issue["fields"]
        elif fault == "wrong_project":
            issue["fields"]["project"]["id"] = "other"
            result["results"][0]["fields"] = issue["fields"]
        elif fault == "wrong_result_id":
            result["results"][0]["id"] = "not-the-issue"
        elif fault == "wrong_audit_id":
            result["results"][0]["action_record_id"] = issue["id"]
        elif fault == "wrong_audit_params":
            record["params"]["summary"] = "Other"
        elif fault == "bad_timestamp":
            record["created_at"] = 42
        elif fault == "local_raised":
            action["status"] = "raised"
        else:
            action["error_json"] = '{"error":"local"}'
    source = mutate_capture(run_operations(initial(), [create()]), 0, damage)
    assert not qualified(evidence(source))


def test_issue_without_ack_has_state_fact_but_no_qualified_birth():
    source = run_operations(initial(), [create()])
    source["state_write_receipts"] = []
    result = evidence(source)
    assert not qualified(result) and result.final.closed and len(result.final.issues) == 1
    assert not result.initial.closed
    assert result.initial.identities_complete and result.initial.all_issue_ids == ()


def test_missing_initial_issue_list_without_anchor_does_not_prove_empty():
    source = run_operations(initial(), [create()])
    source["task_evidence"]["initial"] = initial()
    source["state_write_receipts"] = []
    assert not evidence(source).initial.identities_complete


def test_explicit_no_action_membership_remains_available_without_hydration():
    source = run_operations(initial(), [])
    result = evidence(source)
    assert result.initial.identities_complete and result.initial.all_issue_ids == ()
    assert result.final.closed and result.final.issues == ()
    assert not result.complete  # no captured history asserted


def test_unfinished_inventory_has_explicit_terminal_flag_even_with_other_gaps():
    source = run_operations(initial(), [create()])
    source["task_evidence"]["complete"] = False
    source["task_evidence"]["final"]["jira"]["issues"].append({"id": "partial", "fields": {}})
    result = evidence(source)
    assert result.final.issues and not result.final.finalized and not result.final.closed


def test_unknown_initial_fields_do_not_erase_global_membership():
    source = run_operations(initial(), [])
    source["task_evidence"]["initial"]["jira"]["issues"] = [{"id": "old", "fields": {}}]
    result = evidence(source)
    assert result.initial.identities_complete and result.initial.all_issue_ids == ("old",)


@pytest.mark.parametrize("fault", ["competing_anchors", "reconciliation_mismatch"])
@pytest.mark.parametrize("rows", [[], [{"id": "already-existing", "fields": {}}], [{"id": True}]])
def test_public_membership_survives_unavailable_initial_field_hydration(fault, rows):
    source = run_operations(initial(), [create()])
    source["task_evidence"]["initial"]["jira"]["issues"] = rows
    if fault == "competing_anchors":
        event = copy.deepcopy(source["tool_execution_events"][0])
        receipt = json.loads(event["receipt_json"])
        receipt["invocation_id"] = "competing-initial-anchor"
        event["receipt_json"] = canonical_json(receipt)
        source["tool_execution_events"].append(event)
        write = copy.deepcopy(source["state_write_receipts"][0])
        write["write_id"] = receipt["invocation_id"]
        source["state_write_receipts"].append(write)
    else:
        source["task_evidence"]["initial"]["jira"]["projects"] = [{"id": "other", "key": "OTHER"}]
    result = evidence(source)
    assert result.initial.status == "partial" and not result.initial.closed
    assert result.initial.issues == ()
    assert result.initial.identities_complete is (not rows or type(rows[0]["id"]) is str)
    assert result.initial.all_issue_ids == (("already-existing",) if rows and rows[0]["id"] == "already-existing" else ())
    assert not result.complete


def test_historical_action_log_is_not_hydrated_into_a_real_issue():
    world = WorldState.model_validate(initial())
    world.jira.record_action("create_issue", {"project": "QA", "summary": "Audit dashboard", "issuetype": "Task"})
    source = run_operations(world.model_dump(mode="json"), [lookup()])
    result = evidence(source)
    assert result.complete and not result.initial.issues and not result.final.issues
    assert not qualified(result)


@pytest.mark.parametrize("mutation", ["damage", "delete"])
def test_known_creation_survives_later_unknown_mutation_without_retention_claim(mutation):
    def change(world):
        if mutation == "delete":
            world.jira.issues.clear()
        else:
            world.jira.issues[0]["fields"]["summary"] = "Damaged"
        return {"success": True}
    source = run_operations(initial(), [create(), ("custom_mutator", {}, change)])
    result = evidence(source)
    assert not result.complete and len(qualified(result)) == 1
    if mutation == "delete":
        assert result.final.closed and result.final.issues == ()
    else:
        assert json.loads(result.final.issues[0].issue_json)["fields"]["summary"] == "Damaged"


def test_repeated_create_and_status_noop_keep_occurrences_distinct():
    result = evidence(run_operations(initial(), [create(), create(), update("To Do")]))
    assert result.complete and len(result.final.issues) == 2
    assert len(qualified(result)) == 3
    assert qualified(result)[-1].changed_fields == ()


def test_all_initial_ids_precede_project_projection():
    world = WorldState.model_validate(initial())
    world.jira.projects.append({"id": "other_id", "key": "OTHER"})
    jira_create_issue(world, project="OTHER", issuetype="Task", summary="Already exists")
    initial_id = world.jira.issues[0]["id"]
    result = evidence(run_operations(world.model_dump(mode="json"), [create()]), "qa_id")
    assert result.complete and result.initial.issues == ()
    assert result.initial.all_issue_ids == (initial_id,)


def test_unrelated_invalid_fields_preserve_unique_final_proof_and_global_ids():
    source = run_operations(initial(), [create()])
    source["task_evidence"]["final"]["jira"]["issues"].append({"id": "unrelated", "fields": {}})
    result = evidence(source)
    assert result.final.status == "partial" and result.final.identities_complete
    assert len(result.final.issues) == 1 and "unrelated" in result.final.all_issue_ids


def test_duplicate_id_invalidates_only_that_identity():
    source = run_operations(initial(), [create(), create()])
    rows = source["task_evidence"]["final"]["jira"]["issues"]
    rows.append(copy.deepcopy(rows[0]))
    result = evidence(source)
    assert not result.final.closed and result.final.identities_complete
    assert result.final.duplicate_ids == (rows[0]["id"],)
    assert [item.issue_id for item in result.final.issues] == [rows[1]["id"]]


def test_real_api_handler_and_nested_field_forms_produce_birth():
    args = {"method": "POST", "url": "https://example.atlassian.net/rest/api/3/issue",
            "body": json.dumps({"fields": {"project": {"id": "qa_id"}, "issuetype": {"name": "Bug"}, "summary": "API bug"}})}
    source = run_operations(initial(), [("api_fetch", args, lambda world: api_fetch(world, **args))])
    result = evidence(source)
    assert result.complete and len(qualified(result)) == 1
    after = qualified(result)[0].after_issue_json
    assert after is not None
    assert json.loads(after)["fields"]["issuetype"] == {"name": "Bug"}


@pytest.mark.parametrize("fault", ["boolean_revision", "orphan_ack", "foreign_origin", "wrong_selector", "source_tamper", "model_copy"])
def test_receipt_scope_and_recapture_defend_evidence(fault):
    source = run_operations(initial(), [create()])
    result = evidence(source)
    if fault == "boolean_revision":
        source["state_write_receipts"][0]["applied_revision"] = True
    elif fault == "orphan_ack":
        source["state_write_receipts"].append({"write_id": "orphan", "expected_revision": 1, "applied_revision": 2})
    elif fault == "foreign_origin":
        source["tool_execution_events"][0]["source"] = "assistant"
    elif fault == "source_tamper":
        source["task_evidence"]["final"]["jira"]["issues"][0]["fields"]["summary"] = "Changed"
    elif fault == "model_copy":
        result = result.model_copy(update={"complete": 1})
    selector = JiraIssueSource(project_id="other") if fault == "wrong_selector" else JiraIssueSource()
    with pytest.raises((ValueError, ValidationError)):
        validate_jira_evidence(result, source, selector)
    if fault in {"boolean_revision", "foreign_origin"}:
        assert not qualified(evidence(source))
    if fault == "orphan_ack":
        assert not evidence(source).complete


def test_native_trace_archive_reload_keeps_exact_receipts_and_projection():
    source = run_operations(initial(), [create()])
    events, writes = [], []
    for reduced in source["tool_execution_events"]:
        raw = json.loads(reduced["receipt_json"])
        action = json.loads(raw["evidence_json"][0])["action"]
        common = {"invocation_id": raw["invocation_id"], "tool_name": action["tool_name"],
                  "arguments_json": canonical_json({"args": [], "kwargs": json.loads(action["arguments_json"])}),
                  "state_read_revision": 0}
        for receipt in (ToolServerReceipt(**common, phase="dispatch", event_index=0),
                        ToolServerReceipt(**common, phase="returned", event_index=1,
                            result_json=action["result_json"], evidence_json=tuple(raw["evidence_json"]),
                            state_write_revision=1, state_persistence="applied", state_conflict=False)):
            events.append(ToolServerExecutionEvent(invocation_id=receipt.invocation_id,
                event_index=receipt.event_index, phase=receipt.phase, receipt_seq=len(events),
                state_revision=receipt.event_index, receipt_json=canonical_json(receipt.model_dump(mode="json"))))
        writes.append(StateWriteReceipt(write_id=raw["invocation_id"], body_digest="a" * 64,
                                        expected_revision=0, applied_revision=1, conflict=False))
    trace = vf.Trace(episode_id="manufactured-native-jira", agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type="Task", data=cast(Any, {})), tool_execution_events=tuple(events),
        state_write_receipts=tuple(writes), tool_state_revision=1, is_completed=True, ok=True)
    restored = vf.Trace.model_validate_json(trace.model_dump_json())
    native = {**source, "tool_execution_events": [item.model_dump(mode="json") for item in restored.tool_execution_events],
              "state_write_receipts": [item.model_dump(mode="json") for item in restored.state_write_receipts]}
    result = evidence(native)
    assert result.complete and len(qualified(result)) == 1
    validate_jira_evidence(JiraEvidence.model_validate_json(result.model_dump_json()), native, JiraIssueSource())
