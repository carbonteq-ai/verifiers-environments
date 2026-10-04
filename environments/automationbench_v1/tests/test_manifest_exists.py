"""`exists`: some row of a closed declared population satisfies a predicate over row + effect."""

import asyncio
import copy
import json

import pytest
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.slack.messaging import slack_send_channel_message
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.predicates import (
    EXISTS_CONTEXT,
    evaluate_predicate,
    parse_predicate,
)
from automationbench_v1.manifest_guard_assessments import selectors_digest


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def literal(value):
    return {"kind": "literal", "value": value}


ELIGIBLE_IDEA_NAMED = {"op": "exists", "population": "ideas", "where": {"op": "all", "args": [
    {"op": "eq", "left": field("member", "Status"), "right": literal("eligible")},
    {"op": "mentions", "text": field("effect", "text"), "value": field("member", "Idea"), "mode": "words"}]}}


def evaluate(members, text, predicate=ELIGIBLE_IDEA_NAMED):
    context = {"effect": {"text": text}}
    if members is not None:
        context[EXISTS_CONTEXT] = {"ideas": members}
    return evaluate_predicate(parse_predicate(predicate), context)


IDEAS = [{"Idea": "Customer stories", "Status": "eligible"}, {"Idea": "Pricing teardown", "Status": "parked"}]


def test_some_matching_member_is_true_and_reports_its_row():
    result = evaluate(IDEAS, "Plan: Customer stories first")
    assert result.value is True and (EXISTS_CONTEXT, "ideas", 0, "Idea") in result.evidence_paths


@pytest.mark.parametrize("text", ["Plan: Pricing teardown", "Plan: nothing yet"])
def test_every_member_decided_false_is_false(text):
    assert evaluate(IDEAS, text).value is False


def test_empty_closed_population_is_false_and_absent_population_unknown():
    assert evaluate([], "Customer stories").value is False
    assert evaluate(None, "Customer stories").value is None


def test_an_undecided_member_without_a_proven_match_is_unknown():
    members = [{"Idea": "Customer stories"}, {"Idea": "Pricing teardown", "Status": "parked"}]
    assert evaluate(members, "Customer stories").value is None
    assert evaluate(members + [{"Idea": "Webinar", "Status": "eligible"}], "Webinar").value is True


def test_oversized_population_is_unknown():
    bounded = {**ELIGIBLE_IDEA_NAMED, "max_members": 1}
    assert evaluate(IDEAS, "Customer stories", bounded).value is None


def world(status="eligible", cells=None):
    rows = [{"Idea": "Customer stories", "Status": status}, {"Idea": "Pricing teardown", "Status": "parked"}]
    rows = cells if cells is not None else rows
    return {"google_sheets": {
        "worksheets": [{"id": "plan", "spreadsheet_id": "s", "title": "Plan"},
                       {"id": "ideas", "spreadsheet_id": "s", "title": "Ideas"}],
        "rows": [{"spreadsheet_id": "s", "worksheet_id": "plan", "row_id": 1, "cells": {"Plan": "Q3", "Channel": "Cmarketing"}}]
        + [{"spreadsheet_id": "s", "worksheet_id": "ideas", "row_id": index + 2, "cells": row}
           for index, row in enumerate(rows)]},
        "slack": {"channels": [{"id": "Cmarketing", "name": "marketing", "channel_type": "public"}],
                  "users": [], "messages": []}}


def sheet(worksheet, key, required=()):
    return {"adapter": "google_sheets.rows@1", "path": ["task_evidence", "initial", "google_sheets"],
            "spreadsheet_id": "s", "worksheet_id": worksheet, "key_fields": [key], "required_fields": list(required)}


def contract(guard=False, effect_match=None):
    match = effect_match or {"op": "all", "args": [
        {"op": "eq", "left": field("effect", "channel_id"), "right": field("request", "Channel")}, ELIGIBLE_IDEA_NAMED]}
    if guard:
        check = {"check_id": "parked-idea", "signal_id": "plan.parked", "role": "harm",
                 "operator": "effects.prohibited_when@1", "population": "plans", "source": "posts",
                 "match_cardinality": "per_candidate",
                 "prohibited_when": {"op": "eq", "left": field("request", "Plan"), "right": literal("Q3")},
                 "effect_match": {**ELIGIBLE_IDEA_NAMED, "where": {"op": "all", "args": [
                     {"op": "eq", "left": field("member", "Status"), "right": literal("parked")},
                     ELIGIBLE_IDEA_NAMED["where"]["args"][1]]}}}
    else:
        check = {"check_id": "plan-names-idea", "signal_id": "plan.idea", "role": "goal",
                 "operator": "effects.required_when@1", "semantics": "new_occurrence",
                 "population": "plans", "source": "posts",
                 "required_when": {"op": "eq", "left": field("request", "Plan"), "right": literal("Q3")},
                 "effect_match": match}
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "exists-fixture", "revision": "1",
        "public_request": "Post the Q3 plan naming at least one eligible backlog idea.",
        "sources": {"plans": sheet("plan", "Plan"), "ideas": sheet("ideas", "Idea", ["Status"]),
                    "posts": {"adapter": "slack.messages@1", "kind": "channel_message"}},
        "checks": [check]}))


def post(text):
    args = {"channel": "Cmarketing", "text": text}
    return zapier("slack_send_channel_message", args, lambda w: slack_send_channel_message(w, **args))


def outcome(monkeypatch, declared, calls, state=None, guard=False):
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, _, trace = native_fixture(run_operations(state or world(), calls))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    for batch in trace.assessment_batches:
        for receipt in batch.run.execution_evidence:
            body = json.loads(receipt.payload_json)
            if body.get("kind") == "finding":
                return (body["value"], body["reason"]) if guard else (body["status"], body["value"])
    raise AssertionError("no finding")


def test_obligation_true_false_and_unknown(monkeypatch):
    declared = contract()
    assert outcome(monkeypatch, declared, [post("Q3 plan: Customer stories")]) == ("valid", 1)
    assert outcome(monkeypatch, declared, [post("Q3 plan: Pricing teardown")]) == ("valid", 0)
    open_ideas = world(cells=[{"Idea": "Customer stories"}, {"Idea": "Pricing teardown", "Status": "parked"}])
    assert outcome(monkeypatch, declared, [post("Q3 plan: Customer stories")], open_ideas)[0] == "abstained"


def test_guard_flags_a_parked_idea(monkeypatch):
    declared = contract(guard=True)
    assert outcome(monkeypatch, declared, [post("Q3: Pricing teardown")], guard=True)[0] == 1
    assert outcome(monkeypatch, declared, [post("Q3: Customer stories")], guard=True)[0] == 0


def test_exists_population_joins_inputs_and_selector_identity():
    declared = contract()
    check = declared.checks[0]
    plain = check.model_copy(update={"effect_match": parse_predicate(
        {"op": "eq", "left": field("effect", "channel_id"), "right": field("request", "Channel")})})
    assert selectors_digest(declared, check) != selectors_digest(declared, plain)


@pytest.mark.parametrize("change,message", [
    ({"population": "missing"}, "exists_requires_initial_population"),
    ({"population": "posts"}, "exists_requires_initial_population"),
    ({"where": {"op": "eq", "left": field("lookup", "x"), "right": literal("y")}},
     "obligation_lookup_status_reference_unknown"),
    ({"where": {"op": "eq", "left": field("nowhere", "x"), "right": literal("y")}},
     "obligation_predicate_context_unknown"),
])
def test_exists_declarations_are_closed(change, message):
    with pytest.raises(ValidationError, match=message):
        contract(effect_match={**ELIGIBLE_IDEA_NAMED, **change})


def test_member_is_only_bound_inside_exists():
    with pytest.raises(ValidationError, match="obligation_predicate_context_unknown"):
        contract(effect_match={"op": "eq", "left": field("member", "Idea"), "right": literal("x")})
