"""Conditional policy semantics over public facts, without task-specific code."""

import pytest
from pydantic import ValidationError

from automationbench_v1.contracts.predicates import (
    Negation,
    evaluate_conditional,
    evaluate_predicate,
    parse_predicate,
)


def field(*path):
    return {"kind": "field", "path": path}


def literal(value):
    return {"kind": "literal", "value": value}


def compare(op, left, right):
    return {"op": op, "left": left, "right": right}


def derived(expression):
    return {"kind": "derived", "expression": expression}


@pytest.mark.parametrize("op,truth,reverse,expected", [
    ("eq", True, False, True), ("eq", False, False, False),
    ("ne", True, False, False), ("ne", False, False, True),
    ("eq", True, True, True), ("eq", False, True, False),
    ("gt", True, False, None), ("eq", 1, False, None),
    ("eq", "true", False, None),
])
def test_calendar_coverage_boolean_is_explicit_truth_not_numeric_coercion(op, truth, reverse, expected):
    date = lambda value: {"kind": "input", "format": "iso_date", "literal": value}
    coverage = derived({"kind": "within_interval", "value": date("2026-02-01"),
        "start": date("2026-01-01"), "end": date("2026-03-01"),
        "include_start": True, "include_end": False})
    left, right = (literal(truth), coverage) if reverse else (coverage, literal(truth))
    assert evaluate_predicate(parse_predicate(compare(op, left, right)), {}).value is expected


def test_public_formula_and_sheet_amount_compare_exactly_with_source_paths():
    formula = {"kind": "round", "scale": 2, "ties": "unavailable_on_tie", "value": {
        "kind": "decimal", "op": "div",
        "left": {"kind": "input", "format": "usd_string", "path": ["request", "total"]},
        "right": {"kind": "input", "format": "number", "path": ["request", "months"]}}}
    row = {"kind": "input", "format": "decimal_string", "path": ["effect", "amount"]}
    rule = parse_predicate(compare("eq", derived(row), derived(formula)))
    context = {"request": {"total": "$6,000.00", "months": 12}, "effect": {"amount": "500.00"}}
    assert evaluate_predicate(rule, context).value is True
    context["effect"]["amount"] = "501.00"
    assert evaluate_predicate(rule, context).value is False
    context["request"]["months"] = 0
    result = evaluate_predicate(rule, context)
    assert result.value is None
    assert result.evidence_paths == (("effect", "amount"), ("request", "total"), ("request", "months"))


@pytest.mark.parametrize("left,right,op,expected", [
    ({"kind": "input", "format": "iso_date", "literal": "2026-02-01"},
     {"kind": "input", "format": "iso_date", "literal": "2026-02-02"}, "lt", True),
    ({"kind": "input", "format": "decimal_string", "literal": "1.00"},
     {"kind": "input", "format": "number", "literal": 1}, "eq", True),
    ({"kind": "input", "format": "iso_date", "literal": "2026-02-01"},
     {"kind": "input", "format": "number", "literal": 1}, "eq", None),
    ({"kind": "input", "format": "decimal_string", "literal": "1.00"},
     {"kind": "input", "format": "number", "literal": 1}, "in", None),
])
def test_derived_values_require_compatible_explicit_types(left, right, op, expected):
    rule = parse_predicate(compare(op, derived(left), derived(right)))
    assert evaluate_predicate(rule, {}).value is expected
    assert parse_predicate(rule.model_dump(mode="json")) == rule


def test_derived_operand_does_not_silently_coerce_untyped_literals():
    rule = parse_predicate(compare("eq", derived({"kind": "input", "format": "number", "literal": 1}), literal(1)))
    assert evaluate_predicate(rule, {}).value is None


@pytest.mark.parametrize("op,known,expected", [
    ("all", True, None), ("all", False, False),
    ("any", True, True), ("any", False, None),
])
def test_independent_known_fact_can_settle_unknown_other_clause(op, known, expected):
    rule = parse_predicate({"op": op, "args": [
        compare("eq", field("request", "processed"), literal(True)),
        compare("eq", field("directory", "approved"), literal(True)),
    ]})
    result = evaluate_predicate(rule, {"request": {"processed": known}})
    assert result.value is expected
    assert result.evidence_paths == (("request", "processed"), ("directory", "approved"))


def test_processed_request_guard_can_be_proven_without_unknown_manager():
    rule = parse_predicate({"op": "any", "args": [
        compare("eq", field("request", "Status"), literal("Processed")),
        compare("lt", field("directory", "rank"), field("policy", "minimum")),
    ]})
    assert evaluate_predicate(rule, {"request": {"Status": "Processed"}}).value is True
    assert evaluate_predicate(rule, {"request": {"Status": "Pending"}}).value is None


@pytest.mark.parametrize("condition,status,value", [
    (None, "unavailable", None), (False, "inapplicable", None), (True, "valid", True),
])
def test_when_has_three_distinct_results(condition, status, value):
    predicate = parse_predicate(compare("eq", field("request", "Status"), literal("Processed")))
    when = parse_predicate(compare("eq", field("effect", "qualified"), literal(True)))
    context = {"request": {"Status": "Processed"}}
    if condition is not None:
        context["effect"] = {"qualified": condition}
    result = evaluate_conditional(predicate, context, when=when)
    assert (result.status, result.value) == (status, value)


@pytest.mark.parametrize("value,expected", [(False, True), (True, False), (None, None)])
def test_negation_never_turns_missing_approval_into_denial(value, expected):
    rule = parse_predicate({"op": "not", "arg": compare("eq", field("approved"), literal(True))})
    context = {} if value is None else {"approved": value}
    assert evaluate_predicate(rule, context).value is expected


@pytest.mark.parametrize("op,left,right,expected", [
    ("eq", True, 1, False), ("eq", 1, 1.0, True),
    ("ne", "1", 1, True), ("eq", None, None, True),
    ("in", True, [1, 2], False), ("in", "org.example", ["org.example"], True),
    ("in", "notorg.example", ["org.example"], False),
    ("gte", 100, 100, True), ("gte", 99, 100, False),
    ("gt", 100, 100, False), ("lt", 100, 101, True),
])
def test_exact_typed_comparisons_and_threshold_boundaries(op, left, right, expected):
    rule = parse_predicate(compare(op, field("value"), literal(right)))
    assert evaluate_predicate(rule, {"value": left}).value is expected


@pytest.mark.parametrize("value", [True, "100", float("inf"), float("nan"), {}])
def test_ordered_comparison_refuses_unsupported_or_nonfinite_evidence(value):
    rule = parse_predicate(compare("gte", field("amount"), literal(100)))
    assert evaluate_predicate(rule, {"amount": value}).value is None


def test_explicit_null_is_distinct_from_missing():
    rule = parse_predicate(compare("eq", field("approval"), literal(None)))
    assert evaluate_predicate(rule, {"approval": None}).value is True
    assert evaluate_predicate(rule, {}).value is None


@pytest.mark.parametrize("path", [[True], [-1], [], [""], ["rows", False]])
def test_unsafe_or_empty_paths_rejected(path):
    with pytest.raises(ValidationError):
        parse_predicate(compare("eq", field(*path), literal("x")))


def test_nested_field_and_missing_index():
    rule = parse_predicate(compare("eq", field("rows", 0, "Status"), literal("Pending")))
    assert evaluate_predicate(rule, {"rows": [{"Status": "Pending"}]}).value is True
    assert evaluate_predicate(rule, {"rows": []}).value is None


@pytest.mark.parametrize("raw", [
    {"op": "python", "code": "return True"}, {"op": "all", "args": []},
    compare("eq", literal(float("inf")), literal(0)),
    {"op": "eq", "left": literal("x"), "right": literal("x"), "task": "special"},
])
def test_unregistered_operations_extra_fields_and_invalid_literals_rejected(raw):
    with pytest.raises(ValidationError):
        parse_predicate(raw)


def test_structural_budget_checked_before_recursive_validation():
    raw = compare("eq", literal(1), literal(1))
    for _ in range(40):
        raw = {"op": "not", "arg": raw}
    with pytest.raises(ValueError, match="structure_budget"):
        parse_predicate(raw)


def test_manifest_roundtrip_and_changed_policy_need_no_python_change():
    rule = parse_predicate(compare("gte", field("manager", "rank"), literal(3)))
    original = {"manager": {"rank": 2}}
    assert evaluate_predicate(rule, original).value is False
    changed = rule.model_dump(mode="json")
    changed["right"]["value"] = 2
    restored = parse_predicate(changed)
    assert evaluate_predicate(restored, original).value is True


@pytest.mark.parametrize("status", [None, True, 1, "Cancelled", {}, ""])
def test_unqualified_status_domain_never_selects_inapplicable_branch(status):
    selected = field("request", "Status") | {
        "domain": "string", "allowed": ["Pending", "Processed"],
    }
    when = parse_predicate(compare("eq", selected, literal("Pending")))
    predicate = parse_predicate(compare("eq", literal(1), literal(1)))
    result = evaluate_conditional(predicate, {"request": {"Status": status}}, when=when)
    assert result.status == "unavailable" and result.value is None


def test_known_processed_status_is_legitimately_inapplicable():
    selected = field("Status") | {"domain": "string", "allowed": ["Pending", "Processed"]}
    when = parse_predicate(compare("eq", selected, literal("Pending")))
    rule = parse_predicate(compare("eq", literal(1), literal(1)))
    assert evaluate_conditional(rule, {"Status": "Processed"}, when=when).status == "inapplicable"


def test_direct_model_construction_cannot_bypass_evaluation_budget():
    rule = parse_predicate(compare("eq", literal(1), literal(1)))
    for _ in range(40):
        rule = Negation(op="not", arg=rule)
    with pytest.raises(ValueError, match="structure_budget"):
        evaluate_predicate(rule, {})


def test_field_membership_uses_explicit_sequence_domain():
    right = field("excluded") | {"domain": "sequence"}
    rule = parse_predicate(compare("in", field("email"), right))
    assert evaluate_predicate(rule, {"email": "a@example.com", "excluded": ["a@example.com"]}).value is True
    assert evaluate_predicate(rule, {"email": "a@example.com", "excluded": []}).value is False
    assert evaluate_predicate(rule, {"email": "a@example.com"}).value is None


def test_whole_effect_purpose_template_preserves_dynamic_source_identity():
    expected = {"kind": "text", "parts": ["Provision ", field("request", "email"), " access"]}
    rule = parse_predicate(compare("eq", field("effect", "name"), expected))
    for email in ("alice@example.com", "different@example.com"):
        assert evaluate_predicate(rule, {
            "request": {"email": email}, "effect": {"name": f"Provision {email} access"},
        }).value is True
    assert evaluate_predicate(rule, {
        "request": {"email": "alice@example.com"},
        "effect": {"name": "Cancel Provision alice@example.com access"},
    }).value is False
    assert evaluate_predicate(rule, {
        "request": {"email": "alice@example.com"},
        "effect": {"name": "Quoted: Provision alice@example.com access"},
    }).value is False
    assert evaluate_predicate(rule, {"effect": {"name": "Provision access"}}).value is None


def test_template_does_not_execute_format_expressions_or_coerce_unknown_values():
    expected = {"kind": "text", "parts": ["{request.__class__}", field("name")]}
    rule = parse_predicate(compare("eq", field("effect"), expected))
    assert evaluate_predicate(rule, {"name": 123, "effect": "{request.__class__}123"}).value is None
    assert evaluate_predicate(rule, {"name": "literal", "effect": "{request.__class__}literal"}).value is True
