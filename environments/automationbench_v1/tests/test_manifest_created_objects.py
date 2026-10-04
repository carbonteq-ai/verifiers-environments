"""Fresh Jira object outcomes and separately selected completion transitions."""

import copy
import json
from typing import Any

import pytest
from test_manifest_guards import comparison, field, literal
from test_notification_evidence import run_operations, zapier

from automationbench.schema.world import WorldState
from automationbench.tools.zapier.hubspot.crm import (
    hubspot_add_contact_to_deal,
    hubspot_create_contact,
    hubspot_create_deal,
)
from automationbench.tools.zapier.jira.actions import jira_create_issue, jira_update_issue
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.created_objects import (
    CreatedRetainedCheck,
    evaluate_created_completion,
    evaluate_created_retained,
)
from automationbench_v1.contracts.hubspot_objects import (
    HubSpotObjectSource,
    capture_hubspot_evidence,
)
from automationbench_v1.contracts.jira_effects import JiraIssueSource, capture_jira_evidence
from automationbench_v1.contracts.requests import RequestSource, capture_request_population

PROMPT = [{"role": "user", "content": "Create a QA Task named Exact audit."}]

HUBSPOT_PROMPT = [
    {
        "role": "user",
        "content": (
            "Create a new contact new@example.com named Jo. Create a new Renewal deal "
            "with amount 0 at qualifiedtobuy and associate it with existing contact contact-1."
        ),
    }
]


def hubspot_initial():
    return {
        "hubspot": {"contacts": [{"id": "contact-1", "email": "existing@example.com"}], "deals": []}
    }


def hubspot_create(collection):
    if collection == "contacts":
        args = {"email": "new@example.com", "first_name": "Jo"}
        return zapier(
            "hubspot_create_contact", args, lambda world: hubspot_create_contact(world, **args)
        )
    args = {"dealname": "Renewal", "dealstage": "qualifiedtobuy", "amount": 0}
    return zapier("hubspot_create_deal", args, lambda world: hubspot_create_deal(world, **args))


def hubspot_associate(contact_id="contact-1"):
    args = {"contact_id": contact_id}
    outer = {"tool_name": "hubspot_add_contact_to_deal", "arguments": canonical_json(args)}

    def apply(world):
        args["deal_id"] = world.hubspot.deals[0].id
        outer["arguments"] = canonical_json(args)
        return hubspot_add_contact_to_deal(world, **args)

    # run_operations captures the actual arguments after this handler resolves
    # the freshly returned native ID; no guessed display identity is retained.
    return "execute_tool", outer, apply


def hubspot_spec(collection):
    name, value = (
        ("email", "new@example.com") if collection == "contacts" else ("dealname", "Renewal")
    )
    return RequestSource.model_validate(
        {
            "member_key": "requested-object",
            "fields": {name: {"value": value, "authority_paths": [["task_evidence", "prompt"]]}},
        }
    )


def hubspot_bindings():
    import hashlib

    return [
        {
            "path": ["task_evidence", "prompt"],
            "canonical_sha256": hashlib.sha256(canonical_json(HUBSPOT_PROMPT).encode()).hexdigest(),
        }
    ]


def hubspot_check(collection, *, associated=False):
    name = "email" if collection == "contacts" else "dealname"
    args = [comparison("eq", field("retained", "fields", name), field("request", name))]
    if collection == "deals":
        args.append(comparison("eq", field("retained", "fields", "amount"), literal(0)))
    if associated:
        sequence = {
            "kind": "field",
            "path": ["retained", "fields", "associated_contact_ids"],
            "domain": "sequence",
        }
        args.append(comparison("in", literal("contact-1"), sequence))
    return CreatedRetainedCheck.model_validate(
        {
            "check_id": "requested-object",
            "signal_id": "request.created",
            "role": "goal",
            "population": "request",
            "source": "objects",
            "required_when": comparison(
                "eq", field("request", "request_key"), literal("requested-object")
            ),
            "retained_when": {"op": "all", "args": args},
        }
    )


def hubspot_raw(collection, calls=None):
    source = run_operations(
        hubspot_initial(), calls if calls is not None else [hubspot_create(collection)]
    )
    source["task_evidence"]["prompt"] = copy.deepcopy(HUBSPOT_PROMPT)
    return source


def hubspot_evaluate(
    source, collection, *, associated=False, completion=False, evidence=None
) -> Any:
    object_source, population_source = (
        HubSpotObjectSource(collection=collection),
        hubspot_spec(collection),
    )
    population = capture_request_population(source, population_source, hubspot_bindings())
    evidence = evidence or capture_hubspot_evidence(source, object_source)
    function = evaluate_created_completion if completion else evaluate_created_retained
    fields = (
        ("associated_contact_ids",)
        if associated
        else (("email",) if collection == "contacts" else ("dealname", "amount"))
    )
    extra: dict[str, Any] = {"goal_fields": fields} if completion else {}
    return function(
        source,
        hubspot_check(collection, associated=associated),
        population,
        evidence,
        population_source=population_source,
        object_source=object_source,
        bindings=hubspot_bindings(),
        **extra,
    )


@pytest.mark.parametrize("collection", ["contacts", "deals"])
def test_hubspot_fresh_native_object_and_receipt_completion(collection):
    source = hubspot_raw(collection)
    result = hubspot_evaluate(source, collection, completion=True)
    assert result.outcome.findings[0].value == 1
    assert result.findings[0].selection.occurrence == "execution-0"
    assert result.findings[0].selection.effect_id == "execution-0"
    assert result.findings[0].selection.native_record_id != "execution-0"
    evidence = capture_hubspot_evidence(source, HubSpotObjectSource(collection=collection))
    assert "fields" not in json.loads(evidence.final.objects[-1].object_json)


def test_hubspot_association_credits_same_fresh_deal_and_ignores_repeated_noop():
    source = hubspot_raw(
        "deals", [hubspot_create("deals"), hubspot_associate(), hubspot_associate()]
    )
    result = hubspot_evaluate(source, "deals", associated=True, completion=True)
    assert result.outcome.findings[0].value == 1
    assert result.findings[0].selection.occurrence == "execution-1"
    assert (
        result.findings[0].selection.native_record_id
        == source["task_evidence"]["final"]["hubspot"]["deals"][0]["id"]
    )


@pytest.mark.parametrize("collection", ["contacts", "deals"])
def test_hubspot_missing_receipt_keeps_goal_without_action_credit(collection):
    source = hubspot_raw(collection)
    receipt = json.loads(source["tool_execution_events"][0]["receipt_json"])
    receipt.update(state_write_revision=None, state_persistence="unknown", state_conflict=None)
    source["tool_execution_events"][0]["receipt_json"] = canonical_json(receipt)
    source["state_write_receipts"] = []
    result = hubspot_evaluate(source, collection, completion=True)
    assert result.outcome.findings[0].value == 1
    assert result.findings[0].selection is None


def test_hubspot_initial_identity_gap_blocks_fresh_goal_and_copied_receipt_rejects():
    source = hubspot_raw("deals")
    del source["task_evidence"]["initial"]["hubspot"]["deals"]
    result = hubspot_evaluate(source, "deals", completion=True)
    assert result.outcome.findings[0].status == "abstained"
    assert result.findings[0].selection is None
    source = hubspot_raw("deals")
    evidence = capture_hubspot_evidence(source, HubSpotObjectSource(collection="deals"))
    forged = evidence.model_copy(update={"complete": False})
    with pytest.raises(ValueError):
        hubspot_evaluate(source, "deals", evidence=forged)


def test_hubspot_final_damage_and_existing_object_cannot_complete_new_request():
    source = hubspot_raw("deals")
    source["task_evidence"]["final"]["hubspot"]["deals"][0]["dealname"] = "Other"
    assert hubspot_evaluate(source, "deals", completion=True).findings[0].selection is None
    source = hubspot_raw("deals")
    source["task_evidence"]["initial"]["hubspot"]["deals"] = copy.deepcopy(
        source["task_evidence"]["final"]["hubspot"]["deals"]
    )
    assert hubspot_evaluate(source, "deals").findings[0].value == 0


def initial():
    return {
        "jira": {
            "actions": {},
            "projects": [{"id": "proj_qa", "key": "QA", "name": "QA"}],
            "issues": [],
        }
    }


def create(**changes):
    args: dict[str, Any] = {
        "project": "proj_qa",
        "issuetype": "Task",
        "summary": "Exact audit",
        **changes,
    }
    return zapier("jira_create_issue", args, lambda world: jira_create_issue(world, **args))


def status(value):
    # The target is only known after create; execution capture must retain the
    # real argument, so this helper uses the first issue's deterministic key.
    args = {"issueKey": "QA-1", "transition": value}
    return zapier("jira_update_issue", args, lambda world: jira_update_issue(world, **args))


def raw(calls=None, data=None):
    source = run_operations(data or initial(), calls if calls is not None else [create()])
    source["task_evidence"]["prompt"] = copy.deepcopy(PROMPT)
    return source


def spec():
    return RequestSource.model_validate(
        {
            "member_key": "requested-task",
            "fields": {
                "summary": {
                    "value": "Exact audit",
                    "authority_paths": [("task_evidence", "prompt")],
                },
                "project": {"value": "proj_qa", "authority_paths": [("task_evidence", "prompt")]},
                "type": {"value": "Task", "authority_paths": [("task_evidence", "prompt")]},
            },
        }
    )


def bindings():
    import hashlib

    return [
        {
            "path": ["task_evidence", "prompt"],
            "canonical_sha256": hashlib.sha256(canonical_json(PROMPT).encode()).hexdigest(),
        }
    ]


def check(*, done=False):
    args = [
        comparison("eq", field("retained", "fields", "summary"), field("request", "summary")),
        comparison("eq", field("retained", "fields", "project", "id"), field("request", "project")),
        comparison(
            "eq", field("retained", "fields", "issuetype", "name"), field("request", "type")
        ),
    ]
    if done:
        args.append(
            comparison("eq", field("retained", "fields", "status", "name"), literal("Done"))
        )
    return CreatedRetainedCheck.model_validate(
        {
            "check_id": "requested-object",
            "signal_id": "request.created",
            "role": "goal",
            "population": "request",
            "source": "issues",
            "required_when": comparison(
                "eq", field("request", "request_key"), literal("requested-task")
            ),
            "retained_when": {"op": "all", "args": args},
        }
    )


def evaluate(
    source,
    *,
    done=False,
    declaration=None,
    evidence=None,
    population=None,
    completion=False,
    goal_fields=None,
) -> Any:
    population_source, object_source = spec(), JiraIssueSource(project_id="proj_qa")
    population = population or capture_request_population(source, population_source, bindings())
    evidence = evidence or capture_jira_evidence(source, object_source)
    function = evaluate_created_completion if completion else evaluate_created_retained
    kwargs: dict[str, Any] = (
        {
            "goal_fields": goal_fields
            or (("status",) if done else ("summary", "project", "issuetype"))
        }
        if completion
        else {}
    )
    return function(
        source,
        declaration or check(done=done),
        population,
        evidence,
        population_source=population_source,
        object_source=object_source,
        bindings=bindings(),
        **kwargs,
    )


def test_genuine_created_retained_goal_and_birth_completion_are_distinct_from_audit_identity():
    source = raw()
    outcome = evaluate(source)
    assert outcome.findings[0].value == 1 and outcome.findings[0].required is True
    completion = evaluate(source, completion=True)
    selection = completion.findings[0].selection
    assert selection is not None and selection.occurrence == "execution-0"
    issue = source["task_evidence"]["final"]["jira"]["issues"][0]
    assert (
        selection.native_record_id == issue["id"]
        and selection.effect_id == issue["creation_action_id"]
    )
    assert selection.native_record_id != selection.effect_id


def test_two_distinct_matching_objects_do_not_invent_exactly_one_guard_or_duplicate_goal():
    source = raw([create(), create()])
    outcome = evaluate(source)
    assert len(outcome.findings) == 1 and outcome.findings[0].value == 1
    assert len(outcome.findings[0].native_record_ids) == 2
    assert evaluate(source, completion=True).findings[0].selection.occurrence == "execution-0"


def test_existing_matching_initial_object_never_discharges_new_creation_request():
    world = WorldState.model_validate(initial())
    jira_create_issue(world, project="proj_qa", issuetype="Task", summary="Exact audit")
    source = raw([create(summary="Unrelated")], world.model_dump(mode="json"))
    outcome = evaluate(source)
    assert outcome.findings[0].value == 0
    assert evaluate(source, completion=True).findings[0].selection is None


def test_action_log_alone_is_zero_and_legacy_issue_shape_is_unknown():
    source = raw([])
    source["task_evidence"]["final"]["jira"]["actions"] = {
        "create_issue": [
            {
                "id": "audit-only",
                "action_key": "create_issue",
                "params": {"summary": "Exact audit", "project": "proj_qa", "issuetype": "Task"},
            }
        ]
    }
    assert evaluate(source).findings[0].value == 0
    source["task_evidence"]["final"]["jira"]["issues"] = [
        {"id": "legacy", "summary": "Exact audit", "project": "proj_qa"}
    ]
    assert evaluate(source).findings[0].status == "abstained"


def test_terminal_goal_without_ack_can_pass_but_cannot_project_credit():
    source = raw()
    receipt = json.loads(source["tool_execution_events"][0]["receipt_json"])
    receipt.update(state_write_revision=None, state_persistence="unknown", state_conflict=None)
    source["tool_execution_events"][0]["receipt_json"] = canonical_json(receipt)
    source["state_write_receipts"] = []
    assert evaluate(source).findings[0].value == 1
    completion = evaluate(source, completion=True)
    assert (
        completion.findings[0].status == "unavailable" and completion.findings[0].selection is None
    )


def test_late_qualified_birth_does_not_prove_episode_new_identity_when_initial_ids_are_unknown():
    source = raw([zapier("unknown_read", {}, lambda world: "unchanged"), create()])
    del source["task_evidence"]["initial"]["jira"]["issues"]
    receipt = json.loads(source["tool_execution_events"][0]["receipt_json"])
    receipt.update(state_write_revision=None, state_persistence="unknown", state_conflict=None)
    source["tool_execution_events"][0]["receipt_json"] = canonical_json(receipt)
    source["state_write_receipts"] = source["state_write_receipts"][1:]
    evidence = capture_jira_evidence(source, JiraIssueSource(project_id="proj_qa"))
    assert any(
        item.kind == "create" and item.status == "qualified" for item in evidence.transitions
    )
    assert not evidence.initial.identities_complete
    result = evaluate(source)
    assert result.findings[0].status == "abstained" and result.findings[0].value is None
    assert evaluate(source, completion=True).findings[0].selection is None


def test_later_damage_removes_success_and_supported_status_repair_can_complete():
    damaged = raw([create(), status("Done"), status("Broken")])
    assert evaluate(damaged, done=True).findings[0].value == 0
    assert evaluate(damaged, done=True, completion=True).findings[0].selection is None
    repaired = raw([create(), status("Done"), status("Broken"), status("Done")])
    assert evaluate(repaired, done=True).findings[0].value == 1
    # Policy is explicitly earliest observed qualified completion, not latest.
    assert (
        evaluate(repaired, done=True, completion=True).findings[0].selection.occurrence
        == "execution-1"
    )


def test_noop_and_unrelated_goal_field_cannot_claim_status_completion():
    source = raw([create(), status("To Do"), status("Done"), status("Done")])
    completion = evaluate(source, done=True, completion=True)
    assert completion.findings[0].selection.occurrence == "execution-2"
    assert (
        evaluate(source, done=True, completion=True, goal_fields=("summary",)).findings[0].selection
        is None
    )


def test_missing_before_status_is_unknown_not_false_for_completion():
    def remove_status(world):
        del world.jira.issues[0]["fields"]["status"]
        return "removed"

    source = raw([create(), zapier("custom_mutation", {}, remove_status), status("Done")])
    assert evaluate(source, done=True).findings[0].value == 1
    assert evaluate(source, done=True, completion=True).findings[0].selection is None


def test_unrelated_unknown_object_does_not_erase_proven_fresh_retained_positive():
    source = raw()
    source["task_evidence"]["final"]["jira"]["issues"].append({"id": "unknown", "fields": {}})
    outcome = evaluate(source)
    assert outcome.findings[0].value == 1 and not outcome.scope_complete


@pytest.mark.parametrize("complete", [False, None, 1])
def test_unfinished_episode_cannot_hide_finalization_gap_behind_unrelated_partial_object(complete):
    source = raw()
    source["task_evidence"]["complete"] = complete
    source["task_evidence"]["final"]["jira"]["issues"].append({"id": "unknown", "fields": {}})
    result = evaluate(source)
    assert result.findings[0].status == "abstained" and result.findings[0].value is None
    assert result.findings[0].reason == "created_terminal_finalization_unavailable"
    assert evaluate(source, completion=True).findings[0].selection is None


def test_duplicate_same_native_id_invalidates_only_that_object_proof():
    source = raw([create(), create()])
    final = source["task_evidence"]["final"]["jira"]["issues"]
    duplicate_id = final[0]["id"]
    final.append(copy.deepcopy(final[0]))
    outcome = evaluate(source)
    assert (
        outcome.findings[0].value == 1 and duplicate_id not in outcome.findings[0].native_record_ids
    )
    source = raw()
    final = source["task_evidence"]["final"]["jira"]["issues"]
    final.append(copy.deepcopy(final[0]))
    assert evaluate(source).findings[0].status == "abstained"


def test_equal_qualified_revision_witnesses_are_explicitly_ambiguous_not_array_tiebroken():
    first, second = raw(), raw()
    receipt = json.loads(second["tool_execution_events"][0]["receipt_json"])
    receipt["invocation_id"] = "execution-1"
    second["tool_execution_events"][0]["receipt_json"] = canonical_json(receipt)
    second["state_write_receipts"][0]["write_id"] = "execution-1"
    source = copy.deepcopy(first)
    source["tool_execution_events"] += second["tool_execution_events"]
    source["state_write_receipts"] += second["state_write_receipts"]
    source["task_evidence"]["final"]["jira"]["issues"] += second["task_evidence"]["final"]["jira"][
        "issues"
    ]
    source["task_evidence"]["final"]["jira"]["actions"]["create_issue"] += second["task_evidence"][
        "final"
    ]["jira"]["actions"]["create_issue"]
    result = evaluate(source, completion=True)
    assert result.outcome.findings[0].value == 1
    assert result.findings[0].reason == "created_completion_revision_order_ambiguous"
    assert result.findings[0].selection is None


def test_missing_request_authority_preserves_one_unavailable_goal():
    source = raw()
    source["task_evidence"]["prompt"][0]["content"] = "Other public request"
    result = evaluate(source)
    assert len(result.findings) == 1 and result.findings[0].status == "abstained"
    assert result.findings[0].required is None


def test_source_receipt_projection_and_copied_check_forgeries_reject():
    source = raw()
    evidence = capture_jira_evidence(source, JiraIssueSource(project_id="proj_qa"))
    forged = evidence.model_copy(update={"complete": 1})
    with pytest.raises(ValueError):
        evaluate(source, evidence=forged)
    population = capture_request_population(source, spec(), bindings())
    forged_population = population.model_copy(update={"closed": 1})
    with pytest.raises(ValueError):
        evaluate(source, population=forged_population)
    changed = copy.deepcopy(source)
    changed["task_evidence"]["final"]["jira"]["issues"][0]["fields"]["summary"] = "Foreign"
    with pytest.raises(ValueError):
        evaluate(changed, evidence=evidence)
    predicate = check().retained_when.model_copy(
        update={"args": ({"op": "eq", "left": field("effect", "invented"), "right": literal("x")},)}
    )
    with pytest.raises(ValueError):
        evaluate(source, declaration=check().model_copy(update={"retained_when": predicate}))


def test_budget_overflow_keeps_the_authored_member_unavailable_and_goal_field_metadata_is_strict():
    source = raw([create(), create()])
    result = evaluate(source, declaration=check().model_copy(update={"max_instances": 1}))
    assert (
        len(result.findings) == 1
        and result.findings[0].reason == "created_instance_budget_exceeded"
    )
    for fields in ((True,), ("summary", "summary"), ("unread",)):
        with pytest.raises(ValueError):
            evaluate(source, completion=True, goal_fields=fields)
