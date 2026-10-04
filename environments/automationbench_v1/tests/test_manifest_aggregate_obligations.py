"""Aggregate aliases on occurrence obligations, the numeric-line predicate and
the two Gmail send-scope repairs the report component depends on."""

import copy

import pytest
from pydantic import ValidationError
from test_manifest_notification_effects import send
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.gmail.message import gmail_send_email
from automationbench.tools.zapier.google_sheets.row import google_sheets_update_row
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.notification_effects import (
    NotificationEffectSource,
    capture_notification_effects,
)
from automationbench_v1.contracts.obligations import ObligationCheck
from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate
from automationbench_v1.manifest_guard_assessments import selectors_digest


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def decimal(value):
    return {"kind": "derived", "expression": {"kind": "input", "format": "decimal_string", "literal": value}}


def line(text, expected="4900", label="Total amortization:", fmt="usd_string"):
    predicate = parse_predicate({"op": "line_number_eq", "text": field("effect", "body"),
                                 "label": label, "format": fmt, "expected": decimal(expected)})
    return evaluate_predicate(predicate, {"effect": {"body": text}})


@pytest.mark.parametrize("text,value,reason", [
    ("Total amortization: $4,900", True, "predicate_decided"),
    ("Hi\n  Total amortization: 4900.00  \nThanks", True, "predicate_decided"),
    ("Total amortization: $4,300", False, "predicate_decided"),
    ("No total here", False, "predicate_line_absent"),
    ("", False, "predicate_line_absent"),
    ("Total amortization: $4,900\nTotal amortization: $4,900.00", True, "predicate_decided"),
    ("Total amortization: $4,900\nTotal amortization: $4,800", None, "predicate_line_conflicting"),
    ("> Total amortization: $4,900", None, "predicate_line_ambiguous"),
    ("Total amortization: $4,900\n> Total amortization: $4,300", None, "predicate_line_ambiguous"),
    ("**Total amortization:** $4,900", None, "predicate_line_ambiguous"),
    ("TOTAL AMORTIZATION: $4,900", None, "predicate_line_ambiguous"),
    ("Total amortization: $4,900 USD", None, "predicate_line_ambiguous"),
    ("Total amortization: ($4,900)", None, "predicate_line_ambiguous"),
    ("```\nTotal amortization: $4,900\n```", None, "predicate_line_ambiguous"),
    ("~~~ Total amortization: $4,900", None, "predicate_line_ambiguous"),
    ("```\nx\n~~~\nTotal amortization: $4,900", None, "predicate_line_ambiguous"),
    ("```\nx\n```\nTotal amortization: $4,900", True, "predicate_decided"),
    ("    Total amortization: $4,900", None, "predicate_line_ambiguous"),
    ("\tTotal amortization: $4,900", None, "predicate_line_ambiguous"),
    ("  Total amortization: $4,900\r\n", True, "predicate_decided"),
    ("Total\u00a0amortization: $4,900", None, "predicate_line_ambiguous"),
    ("Total  amortization: $4,900", None, "predicate_line_ambiguous"),
    ("Total\u200bamortization: $4,900", None, "predicate_line_ambiguous"),
    ("Total amortization - $4,900", None, "predicate_line_ambiguous"),
    ("Total amortization $4,900", None, "predicate_line_ambiguous"),
    ("Total amortization for February: $4,900", None, "predicate_line_ambiguous"),
    ("Total amortization: $4,900.", None, "predicate_line_ambiguous"),
    ("Total amortization: -$4,900", False, "predicate_decided"),
    ("Total amortizations: $4,900", False, "predicate_line_absent"),
    ("Subtotal amortization: $4,900", False, "predicate_line_absent"),
])
def test_line_semantics_separate_absent_wrong_and_unreadable(text, value, reason):
    result = line(text)
    assert (result.value, result.reason) == (value, reason)


def test_line_requires_known_text_and_decimal_expectation():
    predicate = parse_predicate({"op": "line_number_eq", "text": field("effect", "body"),
                                 "label": "Total:", "format": "usd_string", "expected": decimal("1")})
    assert evaluate_predicate(predicate, {"effect": {"body": None}}).value is None
    assert evaluate_predicate(predicate, {"effect": {}}).value is None
    date = {"kind": "derived", "expression": {"kind": "input", "format": "iso_date", "literal": "2026-02-01"}}
    dated = parse_predicate({"op": "line_number_eq", "text": field("effect", "body"),
                             "label": "Total:", "format": "usd_string", "expected": date})
    assert evaluate_predicate(dated, {"effect": {"body": "Total: 1"}}).reason == (
        "predicate_line_expected_type_unavailable")
    assert line("Total amortization: 1" + "0" * 70000).reason == "predicate_line_text_budget_exceeded"


@pytest.mark.parametrize("label,domain", [(" padded", "string"), ("two\nlines", "string"),
                                          ("", "string"), ("Total:", "scalar")])
def test_line_declaration_requires_plain_label_and_string_text(label, domain):
    with pytest.raises(ValidationError):
        parse_predicate({"op": "line_number_eq", "text": field("effect", "body", domain=domain),
                         "label": label, "format": "usd_string", "expected": decimal("1")})


SPEC = {"population": "basis", "reduction": "sum", "unit": "USD",
        "where": {"op": "eq", "left": field("request", "Notes"), "right": {"kind": "literal", "value": ""}},
        "value": {"kind": "input", "format": "usd_string", "path": ["request", "Total"]}}


def contract(*, aggregates=None, effect_ref=("aggregate", "total", "value"), required_ref=None,
             basis=None):
    total = {"kind": "derived", "expression": {"kind": "input", "format": "decimal_string",
                                               "path": list(effect_ref)}}
    required = {"op": "eq", "left": field("request", "request_key"),
                "right": {"kind": "literal", "value": "report"}}
    if required_ref is not None:
        required = {"op": "eq", "left": field(*required_ref), "right": {"kind": "literal", "value": "1"}}
    check = {"check_id": "report-line", "signal_id": "report.total_line", "role": "goal",
             "operator": "effects.required_when@1", "semantics": "new_occurrence",
             "population": "request", "source": "sends", "required_when": required,
             "effect_match": {"op": "line_number_eq", "text": field("effect", "body_plain"),
                              "label": "Total:", "format": "usd_string", "expected": total}}
    if aggregates is not False:
        check["aggregates"] = aggregates or [{"alias": "total", "aggregate": SPEC}]
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "aggregate-fixture", "revision": "1",
        "public_request": "Email the total.",
        "sources": {
            "request": {"adapter": "public.request@1", "member_key": "report", "fields": {
                "recipient": {"value": "a@example.com", "authority_paths": [["task_evidence", "prompt"]]}}},
            "basis": basis or {"adapter": "google_sheets.rows@1", "path": ["task_evidence", "initial", "google_sheets"],
                               "spreadsheet_id": "s", "worksheet_id": "w", "key_fields": ["Item"],
                               "required_fields": ["Total", "Notes"]},
            "sends": {"adapter": "gmail.messages@1", "kind": "send"}},
        "checks": [check]}))


def test_declared_aggregates_resolve_and_join_selector_identity():
    declared = contract()
    check = declared.checks[0]
    assert isinstance(check, ObligationCheck) and check.aggregates[0].alias == "total"
    assert "aggregates" in check.model_dump(mode="json")
    raw = check.model_dump(mode="python")
    raw.update(aggregates=(), effect_match={"op": "eq", "left": field("effect", "body_plain"),
                                            "right": {"kind": "literal", "value": "x"}})
    plain = ObligationCheck.model_validate(raw)
    assert "aggregates" not in plain.model_dump(mode="json")
    # Legacy identity covers only population and effect source; aggregates add theirs.
    assert selectors_digest(declared, plain) != selectors_digest(declared, check)


@pytest.mark.parametrize("options,message", [
    ({"effect_ref": ("aggregate", "missing", "value")}, "obligation_aggregate_reference_unknown"),
    ({"effect_ref": ("aggregate", "total", "members")}, "obligation_aggregate_reference_unknown"),
    ({"effect_ref": ("aggregate", "total")}, "obligation_aggregate_reference_unknown"),
    ({"required_ref": ("aggregate", "total", "value")}, "obligation_predicate_context_unknown"),
    ({"aggregates": False}, "obligation_aggregate_reference_unknown"),
    ({"aggregates": [{"alias": "total", "aggregate": SPEC}, {"alias": "total", "aggregate": SPEC}]},
     "obligation_aggregate_alias_conflict"),
    ({"aggregates": [{"alias": "total", "aggregate": {**SPEC, "population": "request"}}]},
     "obligation_aggregate_requires_initial_population"),
    ({"aggregates": [{"alias": "total", "aggregate": {**SPEC, "population": "absent"}}]},
     "obligation_aggregate_requires_initial_population"),
    ({"basis": {"adapter": "google_sheets.rows@1", "path": ["task_evidence", "final", "google_sheets"],
                "spreadsheet_id": "s", "worksheet_id": "w", "key_fields": ["Item"],
                "required_fields": ["Total", "Notes"]}}, "aggregate_initial_population_required"),
])
def test_aggregate_declarations_are_admitted_closed(options, message):
    with pytest.raises(ValidationError, match=message):
        contract(**options)


def test_lookup_alias_cannot_shadow_the_aggregate_namespace():
    raw = contract().checks[0].model_dump(mode="python")
    raw["lookups"] = [{"source": "basis", "alias": "aggregate", "keys": {"Item": field("request", "recipient")}}]
    with pytest.raises(ValidationError, match="obligation_lookup_alias_conflict"):
        ObligationCheck.model_validate(raw)


def sheet_update():
    args = {"spreadsheet": "s", "worksheet": "w", "row": "1", "cells": {"Total": "$2"}}
    return zapier("google_sheets_update_row", args, lambda world: google_sheets_update_row(world, **args))


def world():
    return {"gmail": {"messages": [], "drafts": []},
            "google_sheets": {"worksheets": [{"id": "w", "spreadsheet_id": "s", "title": "W"}],
                              "rows": [{"spreadsheet_id": "s", "worksheet_id": "w", "row_id": 1,
                                        "cells": {"Item": "A", "Total": "$1", "Notes": ""}}]}}


def test_audited_non_gmail_handler_does_not_open_send_scope():
    evidence = capture_notification_effects(run_operations(world(), [sheet_update(), send()]),
                                            NotificationEffectSource())
    assert evidence.complete, evidence.reason
    assert [fact.invocation_id for fact in evidence.effects] == ["execution-1"]


@pytest.mark.parametrize("name", ["custom_tool", "gmail_custom_api", "api_fetch"])
def test_unaudited_handler_still_leaves_send_scope_open(name):
    data = run_operations(world(), [(name, {}, lambda world: {"success": True}), send()])
    evidence = capture_notification_effects(data, NotificationEffectSource())
    assert not evidence.complete and evidence.effects[0].reason == "gmail_operation_scope_unsupported"
    assert evidence.effects[1].status == "qualified"


def test_audited_name_that_changes_gmail_messages_cannot_close_scope():
    def forged(world):
        gmail_send_email(world, to="person@example.com", subject="Hidden", body="Sent")
        return {"success": True}
    data = run_operations(world(), [("google_sheets_update_row", {"row": "1"}, forged)])
    evidence = capture_notification_effects(data, NotificationEffectSource())
    assert not evidence.complete and evidence.effects[0].status == "unavailable"


def test_sparse_public_initial_gmail_reconciles_with_hydrated_native_world():
    data = run_operations(world(), [sheet_update(), send()])
    sparse = copy.deepcopy(data)
    sparse["task_evidence"]["initial"] = world()
    assert sparse["task_evidence"]["initial"] != data["task_evidence"]["initial"]
    evidence = capture_notification_effects(sparse, NotificationEffectSource())
    assert evidence.complete, evidence.reason
    altered = copy.deepcopy(sparse)
    altered["task_evidence"]["initial"]["gmail"]["messages"] = [
        {"id": "invented", "thread_id": "t", "subject": "s", "body_plain": "b"}]
    evidence = capture_notification_effects(altered, NotificationEffectSource())
    assert not evidence.complete and evidence.reason == "gmail_initial_terminal_reconciliation_failed"


def message(**fields):
    return {"id": "m1", "thread_id": "t1", "subject": "Rules", "body_plain": "Read me",
            "date": "2026-01-15T09:00:00Z", **fields}


@pytest.mark.parametrize("public,reconciles", [
    # Fields public state omits (date/thread defaults from now()/uuid) are
    # generated, not public facts: the native values are accepted.
    ({"messages": [{k: v for k, v in message().items() if k != "date"}], "drafts": []}, True),
    ({"messages": [{k: v for k, v in message().items() if k != "thread_id"}], "drafts": []}, True),
    # The schema drops `emails` when `messages` is present: a public collection
    # silently discarded must fail closed.
    ({"messages": [message()], "emails": [message(id="m2")], "drafts": []}, False),
    # A public fact that disagrees with the native world fails closed.
    ({"messages": [message(subject="Different")], "drafts": []}, False),
])
def test_sparse_initial_gmail_reconciles_only_on_public_facts(public, reconciles):
    full = world()
    full["gmail"] = {"messages": [message()], "drafts": []}
    data = run_operations(full, [sheet_update(), send()])
    sparse = copy.deepcopy(data)
    sparse["task_evidence"]["initial"] = {**world(), "gmail": public}
    evidence = capture_notification_effects(sparse, NotificationEffectSource())
    assert evidence.complete is reconciles, evidence.reason
    exact = copy.deepcopy(data)
    exact["task_evidence"]["initial"] = {**world(), "gmail": {"messages": [message()], "drafts": []}}
    assert capture_notification_effects(exact, NotificationEffectSource()).complete
