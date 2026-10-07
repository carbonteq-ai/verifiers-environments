"""Closed initial membership, exact reductions and raw-source re-admission."""

import copy
import json
from decimal import localcontext
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from automationbench_v1.contracts.aggregates import (
    AggregateEvidence,
    AggregateSpec,
    evaluate_aggregate,
    validate_aggregate_evidence,
)
from automationbench_v1.contracts.populations import InitialCollectionSource
from automationbench_v1.contracts.tables import TableSource


def selector():
    return InitialCollectionSource(
        path=("task_evidence", "initial", "gmail", "messages"),
        fields={"key": ("id",), "eligible": ("from_",), "amount": ("subject",)},
        key_fields=("key",),
        required_fields=("eligible",),
    )


def source(rows=None) -> dict[str, Any]:
    return {
        "task_evidence": {
            "initial": {
                "gmail": {
                    "messages": rows
                    if rows is not None
                    else [
                        {"id": "first", "from_": "include", "subject": "0.1"},
                        {"id": "second", "from_": "include", "subject": "0.2"},
                        {"id": "third", "from_": "exclude"},
                    ]
                }
            }
        }
    }


def spec(**changes):
    return AggregateSpec.model_validate(
        {
            "population": "records",
            "reduction": "sum",
            "unit": "USD",
            "where": {
                "op": "eq",
                "left": {"kind": "field", "path": ["request", "eligible"], "domain": "string"},
                "right": {"kind": "literal", "value": "include"},
            },
            "value": {"kind": "input", "format": "decimal_string", "path": ["request", "amount"]},
            **changes,
        }
    )


def evaluate(raw=None, rule=None, selection=None):
    return evaluate_aggregate(
        source() if raw is None else raw,
        spec() if rule is None else rule,
        population_source=selector() if selection is None else selection,
    )


def test_exact_sum_retains_identity_original_cells_paths_values_and_unit():
    raw = source()
    before = copy.deepcopy(raw)
    with localcontext() as context:
        context.prec = 1
        result = evaluate(raw)
    assert result.status == "qualified" and result.canonical_value == "0.3"
    assert result.selected_count == 2 and result.unit == "USD"
    assert [item.native_record_id for item in result.members] == ["first", "second", "third"]
    assert result.members[0].source_path == ("task_evidence", "initial", "gmail", "messages", 0)
    assert result.members[0].value_evidence_json is not None
    value = json.loads(result.members[0].value_evidence_json)
    assert value["raw_values"] == [[["request", "amount"], "0.1"]]
    assert result.members[-1].selected is False and result.members[-1].value_evidence_json is None
    assert raw == before
    restored = AggregateEvidence.model_validate_json(result.model_dump_json())
    validate_aggregate_evidence(restored, raw, spec(), population_source=selector())


def test_count_uses_members_not_values_business_keys_or_effects():
    raw = source([{"id": "one", "from_": "include"}, {"id": "two", "from_": "include"}])
    raw["tool_execution_events"] = [{"unrelated": "repeated"}, {"unrelated": "repeated"}]
    count = spec(reduction="count", value=None, unit="members")
    result = evaluate(raw, count)
    assert result.canonical_value == "2" and result.selected_count == 2
    assert all(row.value_evidence_json is None for row in result.members)


@pytest.mark.parametrize("reduction,unit", [("count", "members"), ("sum", "USD")])
def test_closed_empty_is_zero_but_absent_collection_is_unknown(reduction, unit):
    rule = spec(reduction=reduction, unit=unit, **({"value": None} if reduction == "count" else {}))
    assert evaluate(source([]), rule).canonical_value == "0"
    absent = evaluate({"task_evidence": {"initial": {"gmail": {}}}}, rule)
    assert absent.status == "unavailable" and absent.canonical_value is None
    assert absent.selected_count is None


@pytest.mark.parametrize("bad", [None, True, 4, "", {}, []])
def test_missing_or_malformed_native_identity_cannot_hide_members(bad):
    raw = source()
    raw["task_evidence"]["initial"]["gmail"]["messages"].append({"id": bad, "from_": "exclude"})
    result = evaluate(raw)
    assert result.status == "unavailable" and result.canonical_value is None
    assert result.members[0].selected is True


def test_duplicate_identity_is_not_silently_deduplicated_even_if_excluded():
    raw = source()
    raw["task_evidence"]["initial"]["gmail"]["messages"].append({"id": "first", "from_": "exclude"})
    result = evaluate(raw)
    assert result.status == "unavailable" and result.canonical_value is None
    assert len(result.members) == 4


@pytest.mark.parametrize("change", [{}, {"from_": None}, {"from_": True}, {"from_": ["include"]}])
def test_unknown_eligibility_never_counts_as_false(change):
    result = evaluate(source([{"id": "missing", "subject": "3", **change}]))
    assert result.reason == "aggregate_eligibility_unavailable"
    assert result.canonical_value is None and result.members[0].selected is None


@pytest.mark.parametrize("value", [None, "", "NaN", "Infinity", "1,000", True, 3, {}, []])
def test_selected_value_requires_declared_parse_and_installed_leaf_type(value):
    result = evaluate(source([{"id": "one", "from_": "include", "subject": value}]))
    assert (
        result.status == "unavailable" and result.reason == "aggregate_selected_value_unavailable"
    )


def test_false_filter_does_not_require_or_validate_sum_operand():
    result = evaluate(source([{"id": "one", "from_": "exclude", "subject": {"not": "a string"}}]))
    assert result.status == "qualified" and result.canonical_value == "0"
    assert result.members[0].value_evidence_json is None


def test_three_valued_filter_can_decide_false_with_an_unknown_other_operand():
    rule = spec(
        where={
            "op": "all",
            "args": [
                spec().where.model_dump(mode="json"),
                {
                    "op": "eq",
                    "left": {"kind": "field", "path": ["request", "amount"], "domain": "string"},
                    "right": {"kind": "literal", "value": "1"},
                },
            ],
        }
    )
    assert evaluate(source([{"id": "one", "from_": "exclude"}]), rule).canonical_value == "0"


def test_nonterminating_member_is_unknown_even_if_cross_row_sum_could_cancel():
    expr = {
        "kind": "decimal",
        "op": "div",
        "left": {"kind": "input", "format": "number", "literal": 1},
        "right": {"kind": "input", "format": "number", "literal": 3},
    }
    raw = source([{"id": str(i), "from_": "include"} for i in range(3)])
    assert evaluate(raw, spec(value=expr)).canonical_value is None
    rounded = {"kind": "round", "value": expr, "scale": 2, "ties": "half_even"}
    result = evaluate(raw, spec(value=rounded))
    assert result.canonical_value == "0.99"
    assert result.members[0].value_evidence_json is not None
    assert json.loads(result.members[0].value_evidence_json)["rounding"] == [[2, "half_even"]]


def test_exact_large_signed_values_ignore_decimal_context():
    raw = source(
        [
            {"id": "a", "from_": "include", "subject": "100000000000000000000.01"},
            {"id": "b", "from_": "include", "subject": "-100000000000000000000.02"},
        ]
    )
    with localcontext() as context:
        context.prec = 2
        assert evaluate(raw).canonical_value == "-0.01"


def test_member_budget_refuses_instead_of_truncating_total():
    result = evaluate(rule=spec(max_members=1))
    assert result.reason == "aggregate_member_budget_exceeded"
    assert not result.members and result.canonical_value is None


def test_reordering_changes_source_receipt_but_not_result_or_member_identity_set():
    raw = source()
    first = evaluate(raw)
    raw["task_evidence"]["initial"]["gmail"]["messages"].reverse()
    second = evaluate(raw)
    assert first.canonical_value == second.canonical_value
    assert {row.identity for row in first.members} == {row.identity for row in second.members}
    assert first.source_digest != second.source_digest


@pytest.mark.parametrize(
    "change", ["source", "selector", "unit", "filter", "total", "member", "closure"]
)
def test_receipt_is_recomputed_not_authenticated_by_its_claims(change):
    raw, rule, selection = source(), spec(), selector()
    evidence = evaluate(raw)
    if change == "source":
        raw["task_evidence"]["initial"]["gmail"]["messages"][0]["subject"] = "100"
    elif change == "selector":
        selection = selector().model_copy(update={"required_fields": ("eligible", "amount")})
    elif change == "unit":
        rule = spec(unit="EUR")
    elif change == "filter":
        rule = spec(
            where={
                "op": "eq",
                "left": {"kind": "literal", "value": True},
                "right": {"kind": "literal", "value": True},
            }
        )
    elif change == "total":
        evidence = evidence.model_copy(update={"canonical_value": "999"})
    elif change == "member":
        evidence = evidence.model_copy(
            update={
                "members": (
                    evidence.members[0].model_copy(
                        update={
                            "source_path": ("task_evidence", "initial", "gmail", "messages", True)
                        }
                    ),
                    *evidence.members[1:],
                )
            }
        )
    else:
        evidence = evidence.model_copy(update={"membership_closed": 1})
    with pytest.raises(ValueError):
        validate_aggregate_evidence(evidence, raw, rule, population_source=selection)


@pytest.mark.parametrize(
    "changes",
    [
        {"max_members": True},
        {"reduction": "avg"},
        {"unit": ""},
        {"reduction": "count"},
        {"reduction": "count", "value": None, "unit": "USD"},
        {"value": None},
        {"unexpected": True},
    ],
)
def test_spec_is_closed_strict_and_bounded(changes):
    with pytest.raises(ValidationError):
        spec(**changes)


@pytest.mark.parametrize(
    "path", [["effect", "amount"], ["retained", "amount"], ["candidate", "identity", 0]]
)
def test_no_effect_final_or_positional_context(path):
    with pytest.raises(ValidationError):
        spec(value={"kind": "input", "format": "number", "path": path})


def test_copied_specs_and_arbitrary_protocols_are_not_trusted():
    with pytest.raises(ValidationError):
        evaluate(rule=spec().model_copy(update={"max_members": True}))
    with pytest.raises(TypeError, match="installed_population_source"):
        evaluate(selection=SimpleNamespace(closed=True, rows=()))
    with pytest.raises(ValueError, match="initial_population"):
        evaluate(
            selection=TableSource(
                path=("task_evidence", "final", "google_sheets"),
                spreadsheet_id="ss",
                worksheet_id="ws",
                key_fields=("name",),
            )
        )


def sheet_source():
    return TableSource(
        path=("task_evidence", "initial", "google_sheets"),
        spreadsheet_id="ss",
        worksheet_id="ws",
        key_fields=("name",),
    )


def sheet(rows):
    return {
        "task_evidence": {
            "initial": {
                "google_sheets": {
                    "worksheets": [{"spreadsheet_id": "ss", "id": "ws"}],
                    "rows": [{"spreadsheet_id": "ss", "worksheet_id": "ws", **row} for row in rows],
                }
            }
        }
    }


def test_sheet_declared_row_id_is_scoped_typed_membership_not_array_position():
    raw = sheet(
        [
            {"row_id": 5, "cells": {"name": "a", "eligible": "include", "amount": "$4,000"}},
            {"row_id": "5", "cells": {"name": "b", "eligible": "include", "amount": "$300"}},
        ]
    )
    rule = spec(value={"kind": "input", "format": "usd_string", "path": ["request", "amount"]})
    result = evaluate(raw, rule, sheet_source())
    assert result.canonical_value == "4300" and result.selected_count == 2
    assert [row.identity for row in result.members] == [
        ("ss", "ws", "int", 5),
        ("ss", "ws", "str", "5"),
    ]
    assert all(row.native_record_id is None for row in result.members)


@pytest.mark.parametrize(
    "mutation",
    ["missing-id", "bool-id", "duplicate-row", "duplicate-native", "missing-sheet", "unknown-row"],
)
def test_sheet_incomplete_or_duplicate_membership_never_yields_total(mutation):
    row = {
        "row_id": 2,
        "id": "native",
        "cells": {"name": "a", "eligible": "include", "amount": "1"},
    }
    raw = sheet([row])
    service = raw["task_evidence"]["initial"]["google_sheets"]
    if mutation == "missing-id":
        del service["rows"][0]["row_id"]
    elif mutation == "bool-id":
        service["rows"][0]["row_id"] = True
    elif mutation == "duplicate-row":
        service["rows"].append(copy.deepcopy(service["rows"][0]))
    elif mutation == "duplicate-native":
        service["rows"].append({**copy.deepcopy(service["rows"][0]), "row_id": 3})
    elif mutation == "missing-sheet":
        service["worksheets"] = []
    else:
        service["rows"].append({"unknown": "scope"})
    assert evaluate(raw, selection=sheet_source()).canonical_value is None


def test_missing_unused_columns_do_not_block_qualified_sheet_count():
    raw = sheet([{"row_id": 2, "cells": {"eligible": "include"}}])
    result = evaluate(raw, spec(reduction="count", value=None, unit="members"), sheet_source())
    assert result.canonical_value == "1"


def test_duplicate_business_key_is_not_duplicate_native_membership():
    selection = selector().model_copy(update={"key_fields": ("eligible",)})
    result = evaluate(rule=spec(reduction="count", value=None, unit="members"), selection=selection)
    assert result.canonical_value == "2"


def test_aggregate_overflow_is_unknown_instead_of_rounded_or_truncated():
    raw = source(
        [
            {"id": "a", "from_": "include", "subject": "9" * 128},
            {"id": "b", "from_": "include", "subject": "9" * 128},
        ]
    )
    result = evaluate(raw)
    assert result.status == "unavailable" and result.canonical_value is None
    assert result.reason == "value_numeric_budget_exceeded"
    assert all(member.selected is True for member in result.members)


def test_date_or_boolean_values_are_not_summed_as_numeric_units():
    rule = spec(value={"kind": "input", "format": "iso_date", "literal": "2026-01-01"})
    assert evaluate(rule=rule).reason == "aggregate_selected_value_unavailable"
