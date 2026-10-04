"""Eligibility-first selections relative to the current obligation candidate."""

import asyncio
import json

import pytest
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.gmail.message import gmail_send_email
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def date(*path):
    return {"kind": "input", "format": "iso_date", "path": list(path)}


EMPLOYEES = [
    ("Ana", "Sales", "2020-03-01", "ana@example.com"),
    ("Ben", "Sales", "2018-06-01", "ben@example.com"),
    ("Cy", "Engineering", "2019-01-01", "cy@example.com"),
    ("Dee", "Engineering", "2019-01-01", "dee@example.com"),
]
HIRES = [("Hal", "Sales"), ("Ivy", "Engineering"), ("Jo", "Legal")]


def initial(employees=EMPLOYEES):
    rows = [{"spreadsheet_id": "s", "worksheet_id": "staff", "row_id": i + 1,
             "cells": {"Name": n, "Department": d, "Hire Date": h, "Email": e}}
            for i, (n, d, h, e) in enumerate(employees)]
    rows += [{"spreadsheet_id": "s", "worksheet_id": "hires", "row_id": 100 + i,
              "cells": {"Name": n, "Department": d}} for i, (n, d) in enumerate(HIRES)]
    return {"gmail": {"messages": [], "drafts": []},
            "google_sheets": {"worksheets": [{"id": "staff", "spreadsheet_id": "s", "title": "Staff"},
                                             {"id": "hires", "spreadsheet_id": "s", "title": "Hires"}],
                              "rows": rows}}


BUDDY = {"alias": "buddy", "population": "staff",
         "where": {"op": "eq", "left": field("member", "Department"), "right": field("request", "Department")},
         "order_by": [{"value": date("member", "Hire Date"), "direction": "asc"}]}


def contract(checks, selections=(BUDDY,)):
    def table(tab, required):
        return {"adapter": "google_sheets.rows@1", "path": ["task_evidence", "initial", "google_sheets"],
                "spreadsheet_id": "s", "worksheet_id": tab, "key_fields": ["Name"], "required_fields": required}
    built = []
    for check_id, required_when, effect_match in checks:
        built.append({"check_id": check_id, "signal_id": "buddy." + check_id, "role": "goal",
                      "operator": "effects.required_when@1", "semantics": "new_occurrence",
                      "population": "hires", "source": "sends", "required_when": required_when,
                      "effect_match": effect_match, "selections": list(selections),
                      "match_cardinality": "per_candidate"})
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "buddy-fixture", "revision": "1",
        "public_request": "Assign each new hire the longest-tenured buddy in their department.",
        "sources": {"staff": table("staff", ["Department", "Hire Date", "Email"]),
                    "hires": table("hires", ["Department"]),
                    "sends": {"adapter": "gmail.messages@1", "kind": "send"}},
        "checks": built}))


NOTIFY = ("notify-buddy",
          {"op": "eq", "left": field("selection", "buddy"), "right": {"kind": "literal", "value": "selected"}},
          {"op": "all", "args": [
              {"op": "in", "left": field("selected", "buddy", "Email"),
               "right": field("effect", "recipients", domain="sequence")},
              {"op": "mentions", "text": field("effect", "body_plain"), "mode": "words",
               "value": field("request", "Name")}]})
FALLBACK = ("fallback-head",
            {"op": "eq", "left": field("selection", "buddy"), "right": {"kind": "literal", "value": "none"}},
            {"op": "in", "left": {"kind": "literal", "value": "head@example.com"},
             "right": field("effect", "recipients", domain="sequence")})


def send(to, body):
    args = {"to": to, "subject": "Buddy", "body": body}
    return zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))


def outcomes(monkeypatch, declared, calls, state=None):
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, _, trace = native_fixture(run_operations(state or initial(), calls))
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    found = {}
    for batch in trace.assessment_batches:
        for receipt in batch.run.execution_evidence:
            payload = json.loads(receipt.payload_json)
            if payload.get("kind") == "finding":
                found[payload["check_id"], payload["candidate_identity"][-1]] = (
                    payload["status"], payload["value"], payload["reason"])
    return found


def test_longest_tenure_same_department_buddy_is_selected(monkeypatch):
    found = outcomes(monkeypatch, contract([NOTIFY]), [send("ben@example.com", "Please welcome Hal")])
    assert found["notify-buddy", 100][:2] == ("valid", 1)  # Ben (2018) beats Ana (2020)


def test_wrong_buddy_is_a_known_zero(monkeypatch):
    found = outcomes(monkeypatch, contract([NOTIFY]), [send("ana@example.com", "Please welcome Hal")])
    assert found["notify-buddy", 100][:2] == ("valid", 0)


def test_tie_leaves_selection_unknown(monkeypatch):
    found = outcomes(monkeypatch, contract([NOTIFY]), [send("cy@example.com", "Please welcome Ivy")])
    assert found["notify-buddy", 101][:3] == ("abstained", None, "obligation_requirement_unavailable")


def test_no_eligible_member_publishes_none_for_fallback(monkeypatch):
    found = outcomes(monkeypatch, contract([NOTIFY, FALLBACK]), [send("head@example.com", "Jo needs a buddy")])
    assert found["notify-buddy", 102][0] == "inapplicable"
    assert found["fallback-head", 102][:2] == ("valid", 1)
    assert found["fallback-head", 100][0] == "inapplicable"


def test_unknown_eligibility_or_order_key_is_unknown(monkeypatch):
    staff = list(EMPLOYEES)
    staff[0] = ("Ana", "Sales", "March 2020", "ana@example.com")  # unreadable order key
    found = outcomes(monkeypatch, contract([NOTIFY]), [send("ben@example.com", "Hal")], initial(staff))
    assert found["notify-buddy", 100][0] == "abstained"
    assert found["notify-buddy", 101][0] == "abstained"  # Engineering still tied


def test_chained_selection_reads_the_earlier_choice(monkeypatch):
    mentor = {"alias": "mentor", "population": "staff",
              "where": {"op": "all", "args": [
                  {"op": "eq", "left": field("member", "Department"), "right": field("selected", "buddy", "Department")},
                  {"op": "ne", "left": field("member", "Name"), "right": field("selected", "buddy", "Name")}]},
              "order_by": [{"value": date("member", "Hire Date"), "direction": "asc"}]}
    check = ("notify-mentor",
             {"op": "eq", "left": field("selection", "mentor"), "right": {"kind": "literal", "value": "selected"}},
             {"op": "in", "left": field("selected", "mentor", "Email"),
              "right": field("effect", "recipients", domain="sequence")})
    found = outcomes(monkeypatch, contract([check], (BUDDY, mentor)), [send("ana@example.com", "Hal")])
    assert found["notify-mentor", 100][:2] == ("valid", 1)  # second-longest in Sales


@pytest.mark.parametrize("selections,message", [
    ([{**BUDDY, "where": {"op": "eq", "left": field("selected", "later", "x"), "right": field("member", "Name")}}],
     "obligation_selection_reference_unknown"),
    ([{**BUDDY, "where": {"op": "eq", "left": field("effect", "to"), "right": field("member", "Name")}}],
     "obligation_selection_context_unknown"),
    ([BUDDY, BUDDY], "obligation_selection_alias_conflict"),
    ([{**BUDDY, "order_by": []}], "too_short"),
])
def test_selection_declarations_are_closed(selections, message):
    with pytest.raises(ValidationError, match=message):
        contract([NOTIFY], selections)


def test_predicates_cannot_read_undeclared_selection():
    with pytest.raises(ValidationError, match="obligation_selection_reference_unknown"):
        contract([NOTIFY], ())


def test_selection_population_joins_selector_identity():
    from automationbench_v1.manifest_guard_assessments import required_tables

    declared = contract([NOTIFY])
    assert "staff" in required_tables(declared.checks[0])
