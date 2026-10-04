"""Exact public-rule calculations preserve ambiguity and source provenance."""

from decimal import localcontext

import pytest

from automationbench_v1.contracts.values import evaluate_value, parse_value


def number(value):
    return {"kind": "input", "format": "number", "literal": value}


def decimal(value, format="decimal_string"):
    return {"kind": "input", "format": format, "literal": value}


def field(name, format="usd_string"):
    return {"kind": "input", "format": format, "path": ["request", name]}


def operation(op, left, right):
    return {"kind": "decimal", "op": op, "left": left, "right": right}


def rounded(value, ties="unavailable_on_tie", scale=2):
    return {"kind": "round", "value": value, "scale": scale, "ties": ties}


def calendar(value):
    return {"kind": "input", "format": "iso_date", "literal": value}


def test_policy_formula_preserves_verbatim_inputs_and_explicit_rounding():
    expr = rounded(operation("div", field("Total"), field("Months", "number")))
    result = evaluate_value(expr, {"request": {"Total": "$6,000.00", "Months": 12}})
    assert result.status == "qualified" and result.kind == "decimal" and result.canonical_value == "500"
    assert result.raw_values == ((("request", "Total"), "$6,000.00"), (("request", "Months"), 12))
    assert result.rounding == ((2, "unavailable_on_tie"),)


def test_repeating_division_requires_explicit_rounding_without_ambient_context():
    quotient = operation("div", number(1), number(3))
    assert evaluate_value(quotient, {}).reason == "value_nonterminating_decimal_requires_rounding"
    with localcontext() as context:
        context.prec = 2
        result = evaluate_value(rounded(quotient), {})
        assert result.canonical_value == "0.33"
        assert evaluate_value(operation("mul", decimal("123456.789"), number(1000)), {}).canonical_value == "123456789"


def test_rounding_location_is_preserved_instead_of_algebraically_rewritten():
    quotient = operation("div", number(1), number(3))
    assert evaluate_value(operation("mul", rounded(quotient), number(2)), {}).canonical_value == "0.66"
    assert evaluate_value(rounded(operation("mul", quotient, number(2))), {}).canonical_value == "0.67"


@pytest.mark.parametrize("text,ties,expected", [
    ("1.005", "half_up", "1.01"), ("-1.005", "half_up", "-1.01"),
    ("1.005", "half_even", "1"), ("-1.005", "half_even", "-1"),
    ("1.015", "half_even", "1.02"), ("-1.015", "half_even", "-1.02"),
    ("1.004", "unavailable_on_tie", "1"), ("-1.006", "unavailable_on_tie", "-1.01"),
])
def test_exact_nearest_rounding_is_symmetric_and_tie_policy_explicit(text, ties, expected):
    assert evaluate_value(rounded(decimal(text), ties), {}).canonical_value == expected


@pytest.mark.parametrize("text", ["1.005", "-1.005"])
def test_unspecified_public_rounding_tie_remains_unavailable(text):
    result = evaluate_value(rounded(decimal(text)), {})
    assert result.status == "unavailable" and result.reason == "value_rounding_tie_unavailable"


@pytest.mark.parametrize("text", ["$1,23.00", "$12,34,567", "€123", "(123.00)", "12 USD", " 12", "12 ", "１２", "1e3", "NaN"])
def test_unsupported_or_malformed_money_is_not_coerced(text):
    assert evaluate_value(decimal(text, "usd_string"), {}).status == "unavailable"


@pytest.mark.parametrize("raw", [True, None, float("nan"), float("inf"), "123"])
def test_native_numeric_field_is_strict_and_finite(raw):
    result = evaluate_value(field("Amount", "number"), {"request": {"Amount": raw}})
    assert result.status == "unavailable" and result.canonical_value is None


def test_float_input_uses_serialized_decimal_spelling_without_binary_artifact():
    assert evaluate_value(operation("add", number(0.1), number(0.2)), {}).canonical_value == "0.3"


def test_zero_divisor_and_missing_nested_inputs_remain_unknown_with_source_path():
    assert evaluate_value(operation("div", number(1), number(0)), {}).reason == "value_division_by_zero"
    result = evaluate_value(operation("add", field("Missing"), number(1)), {"request": {}})
    assert result.status == "unavailable" and result.evidence_paths == (("request", "Missing"),)


def test_numeric_and_structure_budgets_bound_untrusted_work():
    assert evaluate_value(decimal("9" * 129), {}).reason == "value_numeric_budget_exceeded"
    assert evaluate_value(number(1e-200), {}).reason == "value_numeric_budget_exceeded"
    expr = number(1)
    for _ in range(40):
        expr = operation("add", expr, number(1))
    with pytest.raises(ValueError, match="structure_budget"):
        parse_value(expr)


def interval(value, start="2026-02-01", end="2026-02-28", **endpoints):
    return {"kind": "within_interval", "value": calendar(value), "start": calendar(start),
            "end": calendar(end), "include_start": endpoints.get("include_start", True),
            "include_end": endpoints.get("include_end", True)}


def test_calendar_arithmetic_and_explicit_interval_edges():
    assert evaluate_value({"kind": "days_between", "start": calendar("2024-02-28"),
                           "end": calendar("2024-03-01")}, {}).canonical_value == 2
    assert evaluate_value({"kind": "days_between", "start": calendar("2026-02-10"),
                           "end": calendar("2026-02-01")}, {}).canonical_value == -9
    assert evaluate_value(interval("2026-02-01"), {}).canonical_value is True
    assert evaluate_value(interval("2026-02-01", include_start=False), {}).canonical_value is False
    assert evaluate_value(interval("2026-02-28", include_end=False), {}).canonical_value is False
    assert evaluate_value(interval("2026-02-10", start="2026-03-01"), {}).status == "unavailable"


@pytest.mark.parametrize("raw", ["02/01/2026", "2026-02-30", "20260201", "February 1, 2026"])
def test_calendar_parser_does_not_guess_format(raw):
    assert evaluate_value(calendar(raw), {}).status == "unavailable"


def test_timestamp_date_conversion_requires_explicit_timezone_and_offset():
    expr = {"kind": "input", "format": "iso_timestamp", "literal": "2026-01-28T00:30:00+02:00",
            "timestamp_timezone": "UTC"}
    assert evaluate_value(expr, {}).canonical_value == "2026-01-27"
    expr["literal"] = "2026-01-28T00:30:00"
    assert evaluate_value(expr, {}).status == "unavailable"
    expr.pop("timestamp_timezone")
    with pytest.raises(ValueError, match="explicit_timezone"):
        parse_value(expr)


def test_interval_flags_and_copied_path_indices_are_strict():
    with pytest.raises(ValueError):
        parse_value(interval("2026-02-01", include_start=1))
    copied = parse_value(field("Amount")).model_copy(update={"path": ("request", True)})
    with pytest.raises(ValueError):
        evaluate_value(copied, {"request": ["1", "2"]})


@pytest.mark.parametrize("offset", ["+00:99", "+01:60", "+24:00", "-00:99", "-24:00"])
def test_invalid_timestamp_offsets_are_unavailable_instead_of_normalized(offset):
    expr = {"kind": "input", "format": "iso_timestamp", "literal": f"2026-01-28T00:00:00{offset}",
            "timestamp_timezone": "UTC"}
    assert evaluate_value(expr, {}).status == "unavailable"


def test_oversized_integer_is_unavailable_before_decimal_string_conversion():
    assert evaluate_value({"kind": "input", "format": "number", "path": ["amount"]},
                          {"amount": 10 ** 5000}).status == "unavailable"


@pytest.mark.parametrize("start,months,policy,expected", [
    ("2025-07-01", 12, "unavailable", "2026-07-01"),
    ("2026-01-01", 1, "unavailable", "2026-02-01"),
    ("2026-01-31", 1, "unavailable", None),
    ("2026-01-31", 1, "clamp", "2026-02-28"),
    ("2024-02-29", 12, "unavailable", None),
    ("2024-02-29", 12, "clamp", "2025-02-28"),
    ("2026-01-01", -1, "unavailable", "2025-12-01"),
    ("0001-01-01", -1, "unavailable", None),
    ("9999-12-01", 1, "unavailable", None),
    ("2026-01-01", 0.5, "unavailable", None),
])
def test_explicit_calendar_month_arithmetic_and_edge_policy(start, months, policy, expected):
    expr = {"kind": "add_calendar_months", "date": calendar(start), "months": number(months),
            "invalid_day": policy}
    result = evaluate_value(expr, {})
    assert result.canonical_value == expected
    assert result.status == ('qualified' if expected is not None else 'unavailable')


def test_calendar_coverage_uses_declared_endpoint_without_host_clock():
    expr = interval('2026-07-01', start='2025-07-01', include_end=False)
    expr['end'] = {'kind': 'add_calendar_months', 'date': calendar('2025-07-01'),
                   'months': number(12), 'invalid_day': 'unavailable'}
    assert evaluate_value(expr, {}).canonical_value is False
    expr['value'] = calendar('2026-02-01')
    assert evaluate_value(expr, {}).canonical_value is True
    del expr['end']['invalid_day']
    with pytest.raises(ValueError):
        parse_value(expr)
