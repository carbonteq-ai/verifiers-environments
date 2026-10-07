"""Input constraints validate declared values without inventing task policy."""

import pytest

from automationbench_v1.contracts.values import ValueInput, evaluate_value, parse_value


def term(value, format="decimal_string"):
    return {"kind": "input", "format": format, "literal": value,
            "number_constraints": {"integral": True, "minimum_exclusive": 0}}


@pytest.mark.parametrize("format,value,expected", [
    ("decimal_string", "12", "12"), ("decimal_string", "12.0", "12"),
    ("number", 12, "12"), ("number", 12.0, "12"), ("usd_string", "$12.00", "12"),
])
def test_positive_integral_constraint_accepts_exact_numeric_values(format, value, expected):
    result = evaluate_value(term(value, format), {})
    assert result.status == "qualified" and result.canonical_value == expected


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "invalid"])
def test_invalid_term_is_unavailable_instead_of_zero_or_inapplicable(value):
    result = evaluate_value(term(value), {})
    assert result.status == "unavailable" and result.canonical_value is None


@pytest.mark.parametrize("value,expected", [(0.1, False), (0.11, True), (-1, False)])
def test_numeric_bound_uses_exact_exclusive_comparison(value, expected):
    expression = {"kind": "input", "format": "number", "literal": value,
                  "number_constraints": {"minimum_exclusive": 0.1}}
    assert (evaluate_value(expression, {}).status == "qualified") is expected


@pytest.mark.parametrize("start,expected", [("2026-01-01", True), ("2026-01-15", False),
    ("2024-02-29", False), ("bad", False)])
def test_date_constraint_is_declared_calendar_day(start, expected):
    result = evaluate_value({"kind": "input", "format": "iso_date", "literal": start,
                             "date_constraints": {"day_of_month": 1}}, {})
    assert (result.status == "qualified") is expected
    assert result.canonical_value == (start if expected else None)


@pytest.mark.parametrize("format,constraints", [
    ("iso_date", {"number_constraints": {"integral": True}}),
    ("number", {"date_constraints": {"day_of_month": 1}}),
    ("iso_timestamp", {"date_constraints": {"day_of_month": 1}}),
])
def test_constraints_reject_incompatible_formats(format, constraints):
    raw = {"kind": "input", "format": format, "literal": "2026-01-01", **constraints}
    if format == "iso_timestamp":
        raw["timestamp_timezone"] = "UTC"
    with pytest.raises(ValueError, match="constraints_require"):
        parse_value(raw)


@pytest.mark.parametrize("constraint", [
    {"integral": 1}, {"integral": "true"}, {"minimum_exclusive": True},
    {"minimum_exclusive": "0"}, {"minimum_exclusive": float("inf")},
    {"minimum_exclusive": float("nan")}, {"minimum_exclusive": 10 ** 1000},
    {"unknown": True},
])
def test_number_constraint_shape_is_strict_finite_and_bounded(constraint):
    with pytest.raises(ValueError):
        parse_value({"kind": "input", "format": "number", "literal": 12,
                     "number_constraints": constraint})


@pytest.mark.parametrize("day", [True, 0, 32, "1", 1.0])
def test_date_constraint_rejects_coercion_and_invalid_days(day):
    with pytest.raises(ValueError):
        parse_value({"kind": "input", "format": "iso_date", "literal": "2026-01-01",
                     "date_constraints": {"day_of_month": day}})


@pytest.mark.parametrize("field,value", [("integral", 1), ("minimum_exclusive", True)])
@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings:UserWarning")
def test_nested_copied_number_constraints_are_freshly_admitted(field, value):
    expression = parse_value(term("12"))
    assert isinstance(expression, ValueInput) and expression.number_constraints is not None
    forged = expression.number_constraints.model_copy(update={field: value})
    with pytest.raises(ValueError):
        evaluate_value(expression.model_copy(update={"number_constraints": forged}), {})


def test_nested_copied_date_constraint_is_freshly_admitted():
    expression = parse_value({"kind": "input", "format": "iso_date", "literal": "2026-01-01",
                              "date_constraints": {"day_of_month": 1}})
    assert isinstance(expression, ValueInput) and expression.date_constraints is not None
    forged = expression.date_constraints.model_copy(update={"day_of_month": True})
    with pytest.raises(ValueError):
        evaluate_value(expression.model_copy(update={"date_constraints": forged}), {})


def test_failed_constraint_preserves_raw_input_and_path():
    expression = {"kind": "input", "format": "decimal_string", "path": ["request", "Term"],
                  "number_constraints": {"integral": True, "minimum_exclusive": 0}}
    result = evaluate_value(expression, {"request": {"Term": "0"}})
    assert result.status == "unavailable"
    assert result.evidence_paths == (("request", "Term"),)
    assert result.raw_values == ((("request", "Term"), "0"),)


@pytest.mark.parametrize("value", ["0", "-1", "1.5"])
def test_invalid_term_propagates_unavailable_through_calendar_coverage(value):
    expression = {"kind": "within_interval", "include_start": True, "include_end": False,
        "value": {"kind": "input", "format": "iso_date", "literal": "2026-02-01"},
        "start": {"kind": "input", "format": "iso_date", "literal": "2026-01-01"},
        "end": {"kind": "add_calendar_months", "invalid_day": "unavailable",
            "date": {"kind": "input", "format": "iso_date", "literal": "2026-01-01"},
            "months": term(value)}}
    assert evaluate_value(expression, {}).status == "unavailable"


def test_absent_constraints_preserve_old_wire_shape():
    raw = {"kind": "input", "format": "number", "literal": 12}
    dumped = parse_value(raw).model_dump(mode="json")
    assert "number_constraints" not in dumped and "date_constraints" not in dumped
    assert dumped == {"kind": "input", "format": "number", "literal": 12,
                      "path": None, "timestamp_timezone": None}
