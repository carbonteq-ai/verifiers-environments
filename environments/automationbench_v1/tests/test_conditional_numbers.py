"""Source policy branches produce exact numbers without first-match defaults."""

import asyncio
import copy

import pytest

from automationbench_v1.contracts.predicates import context_paths
from automationbench_v1.contracts.values import evaluate_value, parse_value


def field(name, domain="string"):
    return {"kind": "field", "path": ["member", name], "domain": domain}


def condition(name, value, domain="string", op="eq"):
    return {"op": op, "left": field(name, domain), "right": {"kind": "literal", "value": value}}


def number(value):
    return {"kind": "input", "format": "number", "literal": value}


def branches(*pairs):
    return {"kind": "conditional_number", "branches": [{"when": when, "value": number(value)}
        for when, value in pairs]}


def test_exact_category_mapping_and_source_paths():
    expr = branches((condition("tier", "Enterprise"), 4), (condition("tier", "Mid-Market"), 2))
    result = evaluate_value(expr, {"member": {"tier": "Enterprise"}})
    assert result.canonical_value == "4" and result.status == "qualified"
    assert result.evidence_paths == (("member", "tier"),)
    assert result.raw_values == ((("member", "tier"), "Enterprise"),) * 2
    assert tuple(context_paths(parse_value(expr).model_dump(mode="python"))) == (("member", "tier"),) * 2


@pytest.mark.parametrize("member,reason", [({}, "input_unavailable"), ({"tier": None}, "input_unavailable"),
    ({"tier": "Unknown"}, "unmapped"), ({"tier": 4}, "input_unavailable")])
def test_missing_wrong_type_and_unmapped_do_not_become_zero(member, reason):
    result = evaluate_value(branches((condition("tier", "Enterprise"), 4)), {"member": member})
    assert result.status == "unavailable" and result.reason.endswith(reason)


def test_ambiguous_and_unknown_other_branch_are_not_first_match():
    expr = branches((condition("tier", "Enterprise"), 4), (condition("tier", "Enterprise"), 2))
    assert evaluate_value(expr, {"member": {"tier": "Enterprise"}}).reason.endswith("ambiguous")
    expr["branches"][1]["when"] = condition("missing", "other")
    assert evaluate_value(expr, {"member": {"tier": "Enterprise"}}).reason.endswith("input_unavailable")


def test_boolean_mapping_is_strict_and_zero_requires_explicit_branch():
    expr = branches((condition("opened", True, "boolean"), 2), (condition("opened", False, "boolean"), 0))
    assert evaluate_value(expr, {"member": {"opened": False}}).canonical_value == "0"
    assert evaluate_value(expr, {"member": {"opened": 0}}).status == "unavailable"


def test_numeric_ranges_and_exact_arithmetic():
    expr = branches((condition("days", 15, "integer", "lt"), 0),
        ({"op": "all", "args": [condition("days", 15, "integer", "gte"),
                                   condition("days", 30, "integer", "lt")]}, -1),
        (condition("days", 30, "integer", "gte"), -2))
    assert [evaluate_value(expr, {"member": {"days": d}}).canonical_value for d in (14, 15, 29, 30)] == ["0", "-1", "-1", "-2"]
    arithmetic = {"kind": "decimal", "op": "add", "left": number(4), "right": expr}
    assert evaluate_value(arithmetic, {"member": {"days": 30}}).canonical_value == "2"


def test_non_numeric_result_and_invalid_predicate_are_rejected_or_unavailable():
    expr = branches((condition("tier", "Enterprise"), 4))
    expr["branches"][0]["value"] = {"kind": "input", "format": "iso_date", "literal": "2026-01-01"}
    assert evaluate_value(expr, {"member": {"tier": "Enterprise"}}).reason.endswith("result_type_unavailable")
    expr["branches"][0]["when"] = {"op": "arbitrary_python", "code": "pass"}
    with pytest.raises(ValueError):
        parse_value(expr)


def test_branch_and_recursive_structure_budgets():
    expr = branches(*[(condition("tier", str(i)), i) for i in range(17)])
    with pytest.raises(ValueError):
        parse_value(expr)
    nested = number(1)
    for _ in range(40):
        nested = {"kind": "conditional_number", "branches": [{"when": condition("tier", "Enterprise"), "value": nested}]}
    with pytest.raises(ValueError, match="structure_budget"):
        parse_value(nested)
    copied = parse_value(branches((condition("tier", "Enterprise"), 4)))
    bad = copied.model_copy(update={"branches": (copied.branches[0].model_copy(update={"when": {"op": "bad"}}),)})
    with pytest.raises(ValueError):
        parse_value(bad)


def test_source_weighted_score_counterexample():
    def mapped(name, choices, domain="string"):
        return branches(*[(condition(name, key, domain), value) for key, value in choices])
    terms = [mapped("industry", [("Enterprise", 4), ("Mid-Market", 2)]),
        mapped("title", [("VP of Engineering", 2), ("Senior VP of Sales", 3)]),
        mapped("lead_source", [("Referral", 3), ("Demo Request", 2)]),
        mapped("has_opened_email", [(True, 2), (False, 0)], "boolean"),
        branches((condition("days_since_activity", 15, "integer", "lt"), 0))]
    expr = terms[0]
    for term in terms[1:]:
        expr = {"kind": "decimal", "op": "add", "left": expr, "right": term}
    first = {"industry": "Enterprise", "title": "VP of Engineering", "lead_source": "Referral",
             "has_opened_email": True, "days_since_activity": 5}
    second = dict(first, industry="Mid-Market", title="Senior VP of Sales", lead_source="Demo Request", days_since_activity=3)
    assert [evaluate_value(expr, {"member": row}).canonical_value for row in (first, second)] == ["11", "9"]
    missing = copy.deepcopy(second)
    del missing["title"]
    assert evaluate_value(expr, {"member": missing}).status == "unavailable"
    from automationbench_v1.contracts.selections import SelectionAlias, _select
    from automationbench_v1.contracts.tables import TableSource, capture_table

    first.update(id="PRI1", status="Hot", lead_score=85)
    second.update(id="PRI3", status="Hot", lead_score=90)
    source = {"task_evidence": {"initial": {"google_sheets": {
        "worksheets": [{"id": "leads", "spreadsheet_id": "s", "title": "Leads"}], "rows": [
        {"spreadsheet_id": "s", "worksheet_id": "leads", "row_id": i, "cells": row}
        for i, row in enumerate((first, second), 1)]}}}}
    table = TableSource(path=("task_evidence", "initial", "google_sheets"), spreadsheet_id="s",
        worksheet_id="leads", key_fields=("id",), required_fields=tuple(k for k in first if k != "id"))
    selection = SelectionAlias.model_validate({"alias": "winner", "population": "leads",
        "where": condition("status", "Hot"), "order_by": [{"value": expr, "direction": "desc"},
        {"value": {"kind": "input", "format": "number", "path": ["member", "lead_score"]}, "direction": "desc"}]})
    status, winner = _select(selection, {}, capture_table(source, table))
    assert status == "selected" and winner["id"] == "PRI1"
    source["task_evidence"]["initial"]["google_sheets"]["rows"][1]["cells"]["title"] = "Unmapped Title"
    assert _select(selection, {}, capture_table(source, table)) is None


def test_native_conditional_selection_and_reload(monkeypatch):
    import verifiers.v1 as vf
    from test_manifest_guard_assessments import native_fixture, terminal_records
    from test_manifest_selections import BUDDY, NOTIFY, contract, initial, send
    from test_notification_evidence import run_operations

    from automationbench_v1 import manifest_assessments
    from automationbench_v1.capture import canonical_json
    from automationbench_v1.contracts import load_contract

    chosen = copy.deepcopy(BUDDY)
    chosen["order_by"] = [{"value": branches(*[(condition("Name", name), points)
        for name, points in (("Ana", 1), ("Ben", 2), ("Cy", 3), ("Dee", 4))]), "direction": "desc"}]
    raw = contract([NOTIFY], selections=(chosen,)).model_dump(mode="json")
    raw["public_request"] = "Assign the eligible buddy with the highest explicitly declared policy score."
    declared = load_contract(canonical_json(raw))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, episode, trace = native_fixture(run_operations(initial(), [send("ben@example.com", "Buddy for Hal")]))
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    records = terminal_records(trace)
    assert any(r.signal.signal_id == "buddy.notify-buddy" and r.value == 1 for r in records)
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    retained = restored.traces[0]
    retained.state = trace.state
    asyncio.run(task.score(retained))
    assert not retained.assessment_errors
    # Compare semantic findings, excluding run/assessment identities.
    facts = lambda rows: {(r.signal.signal_id, r.status, r.value, r.reason) for r in rows}
    assert facts(terminal_records(retained)) == facts(records)
