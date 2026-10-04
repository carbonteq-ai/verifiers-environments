"""Report fact coverage: the mentions predicate and per-candidate obligations."""

import asyncio
import copy
import json

import pytest
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture, terminal_records
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.gmail.message import gmail_send_email
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def mentions(text, value, mode="words", fmt=None, excluding=()):
    raw = {"op": "mentions", "text": field("effect", "body"), "mode": mode,
           "value": value if isinstance(value, dict) else {"kind": "literal", "value": value}}
    if fmt:
        raw["format"] = fmt
    if excluding:
        raw["excluding"] = list(excluding)
    result = evaluate_predicate(parse_predicate(raw), {"effect": {"body": text}})
    return result.value, result.reason


@pytest.mark.parametrize("text,value,expected", [
    ("Assigned Li Wei as buddy", "Li Wei", True),
    ("assigned LI WEI today", "Li Wei", True),
    ("Assigned Li\u200bWei", "Li Wei", True),
    ("Assigned Li Wei-Chen as buddy", "Li Wei", None),  # hyphen near-miss: unknown
    ("O'Brien approved", "Brien", None),
    ("Welcome Nora Lindgren-new hire", "Nora Lindgren", None),
    ("Engineering, Sales and Ops", "Sales", True),
    ("Salesforce sync", "Sales", False),
    ("No mention here", "Sales", False),
    ("> Sales was escalated", "Sales", None),
    ("```\nSales\n```", "Sales", None),
    ("Not Sales this time", "Sales", True),  # presence, not assertion
])
def test_word_mentions(text, value, expected):
    assert mentions(text, value)[0] is expected


def test_listed_hyphenated_longer_name_makes_the_near_miss_absent():
    assert mentions("Buddy Li Wei-Chen", "Li Wei", excluding=["Li Wei-Chen"])[0] is False


def test_longer_listed_names_do_not_count():
    assert mentions("Buddy: Li Wei Chen", "Li Wei", excluding=["Li Wei Chen"])[0] is False
    assert mentions("Li Wei Chen and Li Wei", "Li Wei", excluding=["Li Wei Chen"])[0] is True
    assert mentions("Li Wei", "Li Wei", excluding=["Li Wei"])[0] is True


@pytest.mark.parametrize("text,expected", [
    ("Engineering owes $4,000.", True),
    ("Engineering owes 4000.00 today", True),
    ("Engineering owes $14,000", False),
    ("Engineering owes $4,000.50", False),
    ("Engineering owes $40,00", False),
    ("Engineering owes $4k", True),
    ("Engineering owes $4.0k", True),
    ("Engineering owes $5k", False),
    ("> Engineering owes $4,000", None),
    ("Version 4000x", False),
    ("Owes $4,000,000", False),
    ("Ref PMT-4000-01", False),
    ("Due at 40:00", False),
    ("Owes $4,000 b/c of the lease", True),
])
def test_amount_mentions(text, expected):
    assert mentions(text, "$4,000", "amount", "usd_string")[0] is expected


@pytest.mark.parametrize("text,value,expected", [
    ("Break at 11:30 AM, 15 minutes", "30", False),
    ("Break at 11:30 AM, 30 minutes", "30", True),
    ("Ref PMT-2026-0402", "2026", False),
    ("Due 2026-02-01", "2", False),
])
def test_clock_times_dates_and_references_are_not_amounts(text, value, expected):
    assert mentions(text, value, "amount", "decimal_string")[0] is expected




def test_amount_from_derived_decimal():
    total = {"kind": "derived", "expression": {"kind": "decimal", "op": "add",
             "left": {"kind": "input", "format": "decimal_string", "literal": "2500"},
             "right": {"kind": "input", "format": "decimal_string", "literal": "1500"}}}
    assert mentions("Total $4,000", total, "amount", "usd_string")[0] is True
    date = {"kind": "derived", "expression": {"kind": "input", "format": "iso_date", "literal": "2026-02-01"}}
    assert mentions("Total $4,000", date, "amount", "usd_string")[0] is None


@pytest.mark.parametrize("text,expected", [
    ("Ref PMT-2026-0405 settled", True),
    ("Ref PMT-2026-04051 settled", False),
    ("Ref pmt-2026-0405 settled", False),
    ("Ref PMT-2026-0405.", True),
])
def test_verbatim_mentions(text, expected):
    assert mentions(text, "PMT-2026-0405", "verbatim")[0] is expected


def test_unknown_inputs_and_oversized_text_stay_unknown():
    assert mentions("x" * 70000, "Sales")[0] is None
    raw = {"op": "mentions", "text": field("effect", "body"), "value": field("request", "name"), "mode": "words"}
    assert evaluate_predicate(parse_predicate(raw), {"effect": {"body": "Sales"}}).value is None


@pytest.mark.parametrize("raw,message", [
    ({"mode": "amount"}, "predicate_mentions_amount_requires_format"),
    ({"mode": "words", "format": "usd_string"}, "predicate_mentions_amount_requires_format"),
    ({"mode": "verbatim", "excluding": ["x"]}, "predicate_mentions_excluding_requires_words"),
])
def test_mentions_declaration_is_closed(raw, message):
    with pytest.raises(ValidationError, match=message):
        parse_predicate({"op": "mentions", "text": field("effect", "body"),
                         "value": {"kind": "literal", "value": "x"}, **raw})


ROWS = [("Engineering", "eng@example.com", "$4,000"), ("Sales", "sales@example.com", "$1,500"),
        ("Operations", "ops@example.com", "$900")]


def initial():
    return {"gmail": {"messages": [], "drafts": []},
            "google_sheets": {"worksheets": [{"id": "w", "spreadsheet_id": "s", "title": "Charges"}],
                              "rows": [{"spreadsheet_id": "s", "worksheet_id": "w", "row_id": index + 1,
                                        "cells": {"Department": dept, "Head": head, "Charge": charge}}
                                       for index, (dept, head, charge) in enumerate(ROWS)]}}


def contract(cardinality="per_candidate", credit=False):
    check = {"check_id": "department-charge-reported", "signal_id": "report.department_charge",
             "role": "goal", "operator": "effects.required_when@1", "semantics": "new_occurrence",
             "population": "charges", "source": "sends", "match_cardinality": cardinality,
             "required_when": {"op": "ne", "left": field("request", "Department"),
                               "right": {"kind": "literal", "value": ""}},
             "effect_match": {"op": "all", "args": [
                 {"op": "in", "left": {"kind": "literal", "value": "controller@example.com"},
                  "right": field("effect", "recipients", domain="sequence")},
                 {"op": "mentions", "text": field("effect", "body_plain"), "mode": "words",
                  "value": field("request", "Department")},
                 {"op": "mentions", "text": field("effect", "body_plain"), "mode": "amount",
                  "format": "usd_string", "value": field("request", "Charge")}]}}
    declaration = {"schema_version": 1, "manifest_id": "charges-fixture", "revision": "1",
                   "public_request": "Email the controller each department's charge.",
                   "sources": {"charges": {"adapter": "google_sheets.rows@1",
                                           "path": ["task_evidence", "initial", "google_sheets"],
                                           "spreadsheet_id": "s", "worksheet_id": "w",
                                           "key_fields": ["Department"], "required_fields": ["Charge"]},
                               "sends": {"adapter": "gmail.messages@1", "kind": "send"}},
                   "checks": [check],
                   "credit": [{"check": check["check_id"], "policy": "required_effect_once@1",
                               "channel": "goal"}] if credit else []}
    return load_contract(canonical_json(declaration))


def report(body, to="controller@example.com"):
    args = {"to": to, "subject": "Charges", "body": body}
    return zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))


def scored(monkeypatch, calls, cardinality="per_candidate", missing_ack=None):
    selected = contract(cardinality)
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: selected)
    task, _, trace = native_fixture(run_operations(initial(), calls), missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    return trace


def outcomes(trace):
    found = {}
    for batch in trace.assessment_batches:
        for receipt in batch.run.execution_evidence:
            payload = json.loads(receipt.payload_json)
            if payload.get("kind") == "finding":
                found[payload["candidate_identity"][-1]] = (payload["status"], payload["value"])
    return found


def test_one_report_covers_each_department_independently(monkeypatch):
    body = "Engineering: $4,000\nSales: $1,500.00\nOperations: $950"
    found = outcomes(scored(monkeypatch, [report(body)]))
    assert found == {1: ("valid", 1), 2: ("valid", 1), 3: ("valid", 0)}


def test_unique_candidate_mode_cannot_use_a_shared_report(monkeypatch):
    body = "Engineering: $4,000\nSales: $1,500\nOperations: $900"
    found = outcomes(scored(monkeypatch, [report(body)], cardinality="unique_candidate"))
    assert all(status == "abstained" for status, _ in found.values())


def test_wrong_recipient_and_missing_ack(monkeypatch):
    body = "Engineering: $4,000\nSales: $1,500\nOperations: $900"
    assert set(outcomes(scored(monkeypatch, [report(body, to="cfo@example.com")])).values()) == {("valid", 0)}
    assert {status for status, _ in outcomes(scored(monkeypatch, [report(body)], missing_ack=0)).values()} == {
        "abstained"}


def test_per_candidate_obligation_rejects_once_only_credit():
    with pytest.raises(ValidationError, match="per_candidate_obligation_credit_requires_aggregation"):
        contract(credit=True)
    assert contract("unique_candidate", credit=True).credit


def test_terminal_records_publish_one_signal_per_department(monkeypatch):
    trace = scored(monkeypatch, [report("Engineering $4,000; Sales $1,500; Operations $900")])
    records = [r for r in terminal_records(trace) if r.signal.signal_id == "report.department_charge"]
    assert sorted(r.value for r in records) == [1, 1, 1]


BANK = [("PMT-1", "$500"), ("PMT-2", "$700"), ("PMT-3", "$900")]
LEDGER = [("PMT-1", "$500"), ("PMT-2", "$650")]


def reconciliation_initial(ledger=LEDGER, extra=()):
    rows = [{"spreadsheet_id": "s", "worksheet_id": "bank", "row_id": i + 1, "cells": {"Ref": ref, "Amount": amount}}
            for i, (ref, amount) in enumerate(BANK)]
    rows += [{"spreadsheet_id": "s", "worksheet_id": "ledger", "row_id": 10 + i, "cells": {"Ref": ref, "Amount": amount}}
             for i, (ref, amount) in enumerate([*ledger, *extra])]
    return {"gmail": {"messages": [], "drafts": []},
            "google_sheets": {"worksheets": [{"id": "bank", "spreadsheet_id": "s", "title": "Bank"},
                                             {"id": "ledger", "spreadsheet_id": "s", "title": "Ledger"}],
                              "rows": rows}}


def reconciliation_contract():
    def table(tab):
        return {"adapter": "google_sheets.rows@1", "path": ["task_evidence", "initial", "google_sheets"],
                "spreadsheet_id": "s", "worksheet_id": tab, "key_fields": ["Ref"], "required_fields": ["Amount"]}
    check = {"check_id": "bank-only-reported", "signal_id": "recon.bank_only_reported", "role": "goal",
             "operator": "effects.required_when@1", "semantics": "new_occurrence", "population": "bank",
             "source": "sends", "match_cardinality": "per_candidate",
             "lookups": [{"source": "ledger", "alias": "ledger", "keys": {"Ref": field("request", "Ref")}}],
             "required_when": {"op": "eq", "left": field("lookup", "ledger"),
                               "right": {"kind": "literal", "value": "not_found"}},
             "effect_match": {"op": "mentions", "text": field("effect", "body_plain"), "mode": "verbatim",
                              "value": field("request", "Ref")}}
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "recon-fixture", "revision": "1",
        "public_request": "Report bank payments missing from the ledger.",
        "sources": {"bank": table("bank"), "ledger": table("ledger"),
                    "sends": {"adapter": "gmail.messages@1", "kind": "send"}},
        "checks": [check]}))


def reconciled(monkeypatch, body, initial):
    selected = reconciliation_contract()
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: selected)
    task, _, trace = native_fixture(run_operations(initial, [report(body)]))
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    found = {}
    for batch in trace.assessment_batches:
        for receipt in batch.run.execution_evidence:
            payload = json.loads(receipt.payload_json)
            if payload.get("kind") == "finding":
                found[payload["candidate_identity"][-1]] = (payload["status"], payload["value"], payload["reason"])
    return found


def test_lookup_outcome_selects_bank_only_payments(monkeypatch):
    found = reconciled(monkeypatch, "Missing from ledger: PMT-3", reconciliation_initial())
    assert found[1][0] == found[2][0] == "inapplicable"
    assert found[3][:2] == ("valid", 1)
    found = reconciled(monkeypatch, "All payments reconciled.", reconciliation_initial())
    assert found[3][:2] == ("valid", 0)


def test_duplicate_ledger_reference_is_ambiguous_not_missing(monkeypatch):
    found = reconciled(monkeypatch, "Missing: PMT-3", reconciliation_initial(extra=[("PMT-1", "$500")]))
    # Ambiguous is neither matched nor missing: the requirement is unknown.
    assert found[1][:3] == ("abstained", None, "obligation_requirement_unavailable")
    assert found[2][0] == "inapplicable" and found[3][:2] == ("valid", 1)


@pytest.mark.parametrize("path,message", [
    (["lookup", "unknown"], "obligation_lookup_status_reference_unknown"),
    (["lookup", "ledger", "status"], "obligation_lookup_status_reference_unknown"),
])
def test_lookup_status_references_are_closed(path, message):
    raw = reconciliation_contract().model_dump(mode="json")
    raw["checks"][0]["required_when"]["left"]["path"] = path
    with pytest.raises(ValidationError, match=message):
        load_contract(canonical_json(raw))


def test_lookup_alias_is_reserved():
    raw = reconciliation_contract().model_dump(mode="json")
    raw["checks"][0]["lookups"][0]["alias"] = "lookup"
    with pytest.raises(ValidationError, match="lookup_alias_reserved"):
        load_contract(canonical_json(raw))


@pytest.mark.parametrize("text,expected", [
    ("Owes $36,000", True), ("Owes $36,000.", True),
    ("Owes $36,000,000", False), ("Owes $36,000.50", False),
])
def test_verbatim_amount_boundaries(text, expected):
    assert mentions(text, "$36,000", "verbatim")[0] is expected


def together(text, *terms):
    raw = {"op": "mentions_together", "text": field("effect", "body"), "terms": [
        {"value": {"kind": "literal", "value": value}, "mode": mode, **({"format": fmt} if fmt else {})}
        for value, mode, fmt in terms]}
    return evaluate_predicate(parse_predicate(raw), {"effect": {"body": text}}).value


@pytest.mark.parametrize("text,expected", [
    ("Training: $3,000\nSecurity: $2,000", True),
    ("Training — Engineering $3,000", True),
    ("Training: $2,000\nSecurity: $3,000", False),  # amounts swapped between lines
    ("Training\n$3,000", False),  # not beside each other
    ("Training: $3k", True),
    ("Training: 0.003m", None),
    ("> Training: $3,000", None),
])
def test_amount_must_sit_beside_its_item(text, expected):
    assert together(text, ("Training", "words", None), ("$3,000", "amount", "usd_string")) is expected


def test_together_needs_every_term_on_one_line():
    assert together("Hal → Ben\nIvy → Cy", ("Hal", "words", None), ("Ben", "words", None)) is True
    assert together("Hal → Cy\nIvy → Ben", ("Hal", "words", None), ("Ben", "words", None)) is False
    with pytest.raises(ValidationError):
        parse_predicate({"op": "mentions_together", "text": field("effect", "body"),
                         "terms": [{"value": {"kind": "literal", "value": "x"}, "mode": "words"}]})


@pytest.mark.parametrize("text,expected", [
    ("Your break is at 2:30 PM today", True),
    ("Your break is at 2:30pm", True),
    ("Your break is at 14:30", True),
    ("Your break is at 2:30 p.m.", True),
    ("Your break is at 3:00 PM", False),
    ("Your break is at 2:30", None),  # meridiem-less one-digit hour
    ("Ticket 12:30-A only", False),
    ("Break at 02:30 PM", True),
])
def test_clock_time_mentions(text, expected):
    assert mentions(text, "2:30 PM", "clock_time")[0] is expected


def test_clock_time_value_must_parse():
    assert mentions("At 2:30 PM", "half past two", "clock_time")[0] is None


@pytest.mark.parametrize("text,value,expected", [
    ("You are Hal's buddy", "Hal", True),
    ("You are Hal’s buddy", "Hal", True),
    ("Sarah Jones's team", "Sarah Jones", True),
    ("O'Brien approved", "O'Brien", True),
])
def test_possessives_mention_the_name(text, value, expected):
    assert mentions(text, value)[0] is expected


@pytest.mark.parametrize("text,value,expected", [
    ("Break 10:00-10:30 PM", "10:00 PM", True),
    ("Break 10:00-10:30 PM", "10:00 AM", False),
    ("Break 1:00–1:15 PM", "1:00 PM", True),
    ("Break 10:30", "10:30 AM", None),
    ("Lunch at noon", "12:00 PM", True),
    ("Lunch at 12 noon", "12:00 PM", True),
])
def test_clock_ranges_named_times_and_ambiguous_hours(text, value, expected):
    assert mentions(text, value, "clock_time")[0] is expected


@pytest.mark.parametrize("text,expected", [
    ("Charge: $36,000", False),          # verbatim copy only
    ("Charge: 36000 USD", True),         # same amount, reformatted
    ("Charge: $36,000.00", True),
    ("Charge: $36,000 and later 36000", True),
    ("Charge: $35,000", False),
    ("Charge: $36k", True),             # exact magnitude reading
    ("Charge: $36.1k", False),
    ("Charge: 0.036m", None),           # bare m: unit reading stays open
])
def test_amount_reformatted_flags_non_verbatim_copies(text, expected):
    assert mentions(text, "$36,000", "amount_reformatted", "usd_string")[0] is expected


def test_block_scope_pairs_terms_within_a_paragraph():
    def block(text):
        raw = {"op": "mentions_together", "text": field("effect", "body"), "scope": "block", "terms": [
            {"value": {"kind": "literal", "value": "PMT-2026-0403"}, "mode": "verbatim"},
            {"value": {"kind": "literal", "value": "BANK_ONLY"}, "mode": "words"}]}
        return evaluate_predicate(parse_predicate(raw), {"effect": {"body": text}}).value
    assert block("PMT-2026-0403\nCategory: BANK_ONLY\n\nPMT-2026-0404\nCategory: QB_ONLY") is True
    assert block("PMT-2026-0403\nCategory: QB_ONLY\n\nPMT-2026-0404\nCategory: BANK_ONLY") is False
    assert block("> PMT-2026-0403\n> BANK_ONLY") is None


@pytest.mark.parametrize("text,expected", [("Share $1,200", True), ("Share 1,200 sq ft", False), ("Share 1200", False)])
def test_usd_marked_requires_the_dollar_sign(text, expected):
    assert mentions(text, "$1,200", "amount", "usd_marked")[0] is expected


def test_numeric_values_can_be_matched_verbatim():
    assert mentions("CTR 0.6 today", 0.6, "verbatim")[0] is True
    assert mentions("CTR 0.60 today", 0.6, "verbatim")[0] is False
    assert mentions("Count 4900", 4900, "verbatim")[0] is True


def test_proven_turns_unknown_into_false_only():
    def proven(row):
        raw = {"op": "proven", "arg": {"op": "gt", "left": {"kind": "derived", "expression": {
            "kind": "input", "format": "decimal_string", "path": ["row", "shares"]}},
            "right": {"kind": "derived", "expression": {"kind": "input", "format": "number", "literal": 100}}}}
        return evaluate_predicate(parse_predicate(raw), {"row": row}).value
    assert proven({"shares": "150"}) is True
    assert proven({"shares": "50"}) is False
    assert proven({"shares": "Noise Value 3"}) is False
