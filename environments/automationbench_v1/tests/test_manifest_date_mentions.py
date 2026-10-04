"""Calendar-date mentions (``mode: "date"``), ``within`` intervals and the ``date_text`` value format."""

import asyncio
import copy
import json

import pytest
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.gmail.message import gmail_send_email
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate
from automationbench_v1.contracts.values import evaluate_value


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def literal(value):
    return {"kind": "literal", "value": value}


def states(text, day, assume_year: int | None = None):
    raw = {"op": "mentions", "text": field("t"), "mode": "date", "value": literal(day)}
    if assume_year is not None:
        raw["assume_year"] = assume_year
    return evaluate_predicate(parse_predicate(raw), {"t": text}).value


def within(text, start="2026-02-01", end="2026-02-28", assume_year: int | None = 2026):
    raw = {"op": "mentions", "text": field("t"), "mode": "date",
           "within": {"start": literal(start), "end": literal(end)}}
    if assume_year is not None:
        raw["assume_year"] = assume_year
    return evaluate_predicate(parse_predicate(raw), {"t": text}).value


@pytest.mark.parametrize("text", [
    "Your interview is on 2026-03-05.",
    "Date: 2026/03/05",
    "Starts 2026-03-05T10:00:00Z",
    "Due 3/25/2026",          # only the month-first reading is a date
    "Due 25/03/2026",         # only the day-first reading is a date
    "on March 5, 2026",
    "on Mar 5 2026",
    "on Mar. 5th, 2026 at 2pm",
    "on 5 March 2026",
    "on the 5th of March, 2026",
    "on Thursday, March 5, 2026",
    "on Thu, Mar 5, 2026",
])
def test_explicit_renderings_state_the_date(text):
    day = "2026-03-25" if "25" in text else "2026-03-05"
    assert states(text, day) is True


def test_identical_readings_are_one_date():
    assert states("Due 05/05/2026", "2026-05-05") is True


@pytest.mark.parametrize("text", ["Due 03/05/2026", "Due 3/5/2026", "Due 3.5.2026"])
def test_month_first_and_day_first_both_valid_is_unknown(text):
    assert states(text, "2026-03-05") is None
    assert states(text, "2026-05-03") is None
    assert states(text, "2026-07-14") is False  # neither reading is that date


def test_a_stated_weekday_disambiguates_or_contradicts():
    assert states("Thursday, 3/5/2026", "2026-03-05") is True    # 2026-03-05 is a Thursday
    assert states("Friday, March 5, 2026", "2026-03-05") is None  # contradictory weekday


def test_year_less_dates_need_a_declared_year():
    assert states("Thursday, March 5", "2026-03-05") is None
    assert states("Thursday, March 5", "2026-03-05", assume_year=2026) is True
    assert states("See you Mar 5th", "2026-03-05", assume_year=2026) is True
    assert states("See you Mar 5th", "2027-03-05", assume_year=2026) is False
    assert states("See you March 6", "2026-03-05") is False       # month/day rules it out in any year
    assert states("Wednesday, March 5", "2026-03-05") is False    # weekday rules it out


@pytest.mark.parametrize("text,day,expected", [
    ("Available March 5–7, 2026", "2026-03-05", True),
    ("Available March 5–7, 2026", "2026-03-07", True),
    ("Available March 5–7, 2026", "2026-03-06", None),   # interior: covered, not stated
    ("Available March 5–7, 2026", "2026-03-09", False),
    ("Mar 5 - Mar 7, 2026", "2026-03-07", True),
    ("March 5, 2026 – March 7, 2026", "2026-03-06", None),
    ("Dec 30 – Jan 2, 2027", "2026-12-30", True),
    ("5–7 March 2026", "2026-03-07", True),
    ("March 5 - 7pm", "2026-03-07", False),               # a time, not a range
    ("between March 5 and 7", "2026-03-06", None),
    ("between March 5 and 7", "2026-03-07", True),
    ("2026-03-05 to 2026-03-07", "2026-03-06", None),
])
def test_ranges_state_their_endpoints(text, day, expected):
    assert states(text, day, assume_year=2026) is expected


@pytest.mark.parametrize("text,day,expected", [
    ("Reminder: tomorrow at 10am", "2026-03-05", None),
    ("Let's meet next Friday", "2026-03-06", None),
    ("Let's meet next Friday", "2026-03-05", False),      # 2026-03-05 is not a Friday
    ("in 3 business days", "2026-03-05", None),
    ("Score was 3/5", "2026-03-05", None),                # year-less slash: maybe a date
    ("Score was 3/5", "2026-07-14", False),
    ("on the 5th", "2026-03-05", None),
    ("we may 5 times", "2026-05-05", None),               # lowercase "may" may be a verb
])
def test_relative_and_near_miss_tokens_stay_unknown(text, day, expected):
    assert states(text, day) is expected


@pytest.mark.parametrize("text", [
    "Your interview is on April 20, 2026.",
    "Ref PMT-2026-03-05 was paid",            # a reference code, not a date
    "Release v1.3.26 shipped",
    "We will review this in March 2026.",     # a month names no day
    "No dates at all.",
])
def test_clear_other_dates_or_none_are_false(text):
    assert states(text, "2026-03-05") is False


def test_listed_days_share_the_month():
    assert states("Posts on Feb 3, 10 and 17", "2026-02-03", assume_year=2026) is True
    assert states("Posts on Feb 3, 10 and 17", "2026-02-10", assume_year=2026) is None
    assert states("Posts on Feb 3, 10 and 17", "2026-02-11", assume_year=2026) is False


def test_quoted_lines_and_derived_dates():
    assert states("> Meeting on March 5, 2026", "2026-03-05") is None
    derived = {"kind": "derived", "expression": {
        "kind": "add_business_days", "date": {"kind": "input", "format": "iso_date", "literal": "2026-04-27"},
        "days": {"kind": "input", "format": "number", "literal": -5}, "holidays": []}}
    raw = {"op": "mentions", "text": field("t"), "mode": "date", "value": derived}
    assert evaluate_predicate(parse_predicate(raw), {"t": "Your exit interview: Monday, April 20, 2026"}).value is True
    assert evaluate_predicate(parse_predicate(raw), {"t": "Your exit interview: April 21, 2026"}).value is False


def test_date_value_must_be_iso():
    assert states("March 5, 2026", "March 5, 2026") is None
    assert states("March 5, 2026", "2026-3-5") is None


def test_date_mentions_together_pair_a_date_with_a_name():
    raw = {"op": "mentions_together", "text": field("t"), "terms": [
        {"value": literal("Olivia"), "mode": "words"},
        {"value": literal("2026-04-20"), "mode": "date", "assume_year": 2026}]}
    check = lambda text: evaluate_predicate(parse_predicate(raw), {"t": text}).value
    assert check("Olivia: Monday, April 20\nKaren: April 17") is True
    assert check("Olivia: April 17\nKaren: April 20") is False


@pytest.mark.parametrize("text,expected", [
    ("Posts: Feb 3, Feb 10, Feb 17", True),
    ("Posts: Feb 3, 2026 and 2026-02-27", True),
    ("Posts: Feb 3 and March 3", False),
    ("No dates here", False),
    ("Feb 3 and tomorrow", None),
    ("Feb 3\n> Mar 9", None),
    ("Feb 3 and 03/02/2026", None),         # Mar 2 or Feb 3: may lie outside
    ("Feb 3 and 02/03/2026", None),
    ("Feb 3 and 3/5", None),
])
def test_within_requires_every_stated_date_inside(text, expected):
    assert within(text) is expected


def test_within_year_less_needs_a_year_unless_clearly_outside():
    assert within("Posts: Feb 3, Feb 10", assume_year=None) is None
    assert within("Posts: Feb 3, March 10", assume_year=None) is False


@pytest.mark.parametrize("raw,message", [
    ({"mode": "date"}, "predicate_mentions_requires_value_or_within"),
    ({"mode": "words", "within": {"start": literal("2026-02-01"), "end": literal("2026-02-28")}},
     "predicate_mentions_within_requires_date"),
    ({"mode": "date", "value": literal("2026-02-01"),
      "within": {"start": literal("2026-02-01"), "end": literal("2026-02-28")}},
     "predicate_mentions_requires_value_or_within"),
    ({"mode": "words", "value": literal("x"), "assume_year": 2026}, "predicate_mentions_assume_year_requires_date"),
])
def test_date_declarations_are_closed(raw, message):
    with pytest.raises(ValidationError, match=message):
        parse_predicate({"op": "mentions", "text": field("t"), **raw})


def test_new_fields_stay_out_of_existing_dumps():
    raw = {"op": "mentions", "text": field("t"), "mode": "words", "value": literal("x")}
    dumped = parse_predicate(raw).model_dump(mode="json")
    assert "within" not in dumped and "assume_year" not in dumped
    assert parse_predicate(dumped).model_dump(mode="json") == dumped


@pytest.mark.parametrize("text,expected", [
    ("February 3, 2026", "2026-02-03"), ("Feb 3 2026", "2026-02-03"), ("Tuesday, February 3, 2026", "2026-02-03"),
    ("3 February 2026", "2026-02-03"), ("3rd of February, 2026", "2026-02-03"), ("2026-02-03", "2026-02-03"),
    ("2/13/2026", "2026-02-13"), ("13/2/2026", "2026-02-13"),
    ("2/3/2026", None), ("February 3", None), ("Monday, February 3, 2026", None), ("Feb 30, 2026", None),
    ("tomorrow", None), ("on February 3, 2026", None),
])
def test_date_text_value_format(text, expected):
    result = evaluate_value({"kind": "input", "format": "date_text", "literal": text}, {})
    assert (result.canonical_value if result.status == "qualified" else None) == expected
    assert result.kind == ("calendar_date" if expected else None)


# End to end: each event row's human date must be stated in the invitation email.
ROWS = [("Kickoff", "kickoff@example.com", "February 3, 2026"),
        ("Review", "review@example.com", "Feb 10, 2026"),
        ("Retro", "retro@example.com", "February 17, 2026")]


def initial():
    return {"gmail": {"messages": [], "drafts": []},
            "google_sheets": {"worksheets": [{"id": "w", "spreadsheet_id": "s", "title": "Events"}],
                              "rows": [{"spreadsheet_id": "s", "worksheet_id": "w", "row_id": index + 1,
                                        "cells": {"Event": event, "Owner": owner, "Date": day}}
                                       for index, (event, owner, day) in enumerate(ROWS)]}}


def contract():
    stated_date = {"kind": "derived", "expression": {"kind": "input", "format": "date_text", "path": ["request", "Date"]}}
    check = {"check_id": "event-date-stated", "signal_id": "invite.event_date",
             "role": "goal", "operator": "effects.required_when@1", "semantics": "new_occurrence",
             "population": "events", "source": "sends", "match_cardinality": "per_candidate",
             "required_when": {"op": "ne", "left": field("request", "Event"), "right": literal("")},
             "effect_match": {"op": "all", "args": [
                 {"op": "in", "left": field("request", "Owner"), "right": field("effect", "recipients", domain="sequence")},
                 {"op": "mentions", "text": field("effect", "body_plain"), "mode": "date",
                  "value": stated_date, "assume_year": 2026}]}}
    declaration = {"schema_version": 1, "manifest_id": "event-dates-fixture", "revision": "1",
                   "public_request": "Email each event owner the event date.",
                   "sources": {"events": {"adapter": "google_sheets.rows@1",
                                          "path": ["task_evidence", "initial", "google_sheets"],
                                          "spreadsheet_id": "s", "worksheet_id": "w",
                                          "key_fields": ["Event"], "required_fields": ["Date"]},
                               "sends": {"adapter": "gmail.messages@1", "kind": "send"}},
                   "checks": [check], "credit": []}
    return load_contract(canonical_json(declaration))


def invite(to, body):
    args = {"to": to, "subject": "Event date", "body": body}
    return zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))


def test_native_scoring_reads_stated_dates(monkeypatch):
    selected = contract()
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: selected)
    calls = [invite("kickoff@example.com", "Kickoff is on Tuesday, February 3."),
             invite("review@example.com", "Review moved to Feb 11, 2026."),
             invite("retro@example.com", "Retro is 2/17 or so - will confirm tomorrow.")]
    task, _, trace = native_fixture(run_operations(initial(), calls))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    found = {}
    for batch in trace.assessment_batches:
        for receipt in batch.run.execution_evidence:
            payload = json.loads(receipt.payload_json)
            if payload.get("kind") == "finding":
                found[payload["candidate_identity"][-1]] = (payload["status"], payload["value"])
    assert found[1] == ("valid", 1)       # year-less date with a declared year
    assert found[2] == ("valid", 0)       # a clear different date
    assert found[3][0] == "abstained"     # "2/17" and "tomorrow" cannot be decided
