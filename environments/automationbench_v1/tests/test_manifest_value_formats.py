"""Clock time, duration and instant value formats."""

import pytest

from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate
from automationbench_v1.contracts.values import evaluate_value


def value(fmt, literal):
    result = evaluate_value({"kind": "input", "format": fmt, "literal": literal}, {})
    return result.canonical_value if result.status == "qualified" else None


@pytest.mark.parametrize("literal,expected", [
    ("2:30 PM", "870"), ("2pm", "840"), ("12:15 a.m.", "15"), ("12:00 PM", "720"), ("14:30", "870"),
    ("02:30", "150"), ("2:30", None), ("13:00 PM", None), ("25:00", None), ("tea time", None),
])
def test_clock_time(literal, expected):
    assert value("clock_time", literal) == expected


@pytest.mark.parametrize("literal,expected", [
    ("15 minutes", "15"), ("1 hour 30 min", "90"), ("1 hour and 15 minutes", "75"), ("1.5 hours", "90"),
    ("90m", "90"), ("1h30m", "90"), ("2 hrs", "120"), ("30", None), ("15 minutes break", None), ("soon", None),
])
def test_duration_text(literal, expected):
    assert value("duration_text", literal) == expected


@pytest.mark.parametrize("literal,expected", [
    ("2:45", "165"), ("0:59", "59"), ("1:02:45", "3765"), ("2:75", None), ("245", None),
])
def test_duration_clock(literal, expected):
    assert value("duration_clock", literal) == expected


@pytest.mark.parametrize("literal,expected", [
    ("2026-03-02T15:00:00Z", "1772463600"), ("2026-03-02T10:00:00-05:00", "1772463600"),
    ("2026-03-02T15:00:00.500000Z", "1772463600.5"), ("2026-03-02T15:00Z", "1772463600"),
    ("2026-03-02T15:00:00", None), ("March 2", None),
])
def test_iso_instant(literal, expected):
    assert value("iso_instant", literal) == expected


def test_break_must_end_before_meeting_using_clock_and_duration_arithmetic():
    def ends_before(start, duration):
        raw = {"op": "lte", "left": {"kind": "derived", "expression": {
            "kind": "decimal", "op": "add",
            "left": {"kind": "input", "format": "clock_time", "path": ["row", "start"]},
            "right": {"kind": "input", "format": "duration_text", "path": ["row", "duration"]}}},
            "right": {"kind": "derived", "expression": {"kind": "input", "format": "clock_time", "literal": "2:00 PM"}}}
        return evaluate_predicate(parse_predicate(raw), {"row": {"start": start, "duration": duration}}).value
    assert ends_before("1:30 PM", "30 minutes") is True
    assert ends_before("1:45 PM", "30 minutes") is False
    assert ends_before("1:45", "30 minutes") is None


def test_number_constraints_apply_to_decimal_formats():
    raw = {"kind": "input", "format": "duration_text", "literal": "15 minutes",
           "number_constraints": {"minimum_exclusive": 20}}
    assert evaluate_value(raw, {}).status == "unavailable"


@pytest.mark.parametrize("literal,expected", [
    ("10:30", None), ("12:15", None), ("09:30", "570"), ("13:05", "785"), ("noon", "720"), ("midnight", "0"),
])
def test_ambiguous_morning_evening_and_named_times(literal, expected):
    assert value("clock_time", literal) == expected


def business(start, days, holidays=()):
    raw = {"kind": "add_business_days", "date": {"kind": "input", "format": "iso_date", "literal": start},
           "days": {"kind": "input", "format": "number", "literal": days}, "holidays": list(holidays)}
    result = evaluate_value(raw, {})
    return result.canonical_value if result.status == "qualified" else None


def test_business_days_skip_weekends_and_declared_holidays():
    assert business("2026-03-06", 1) == "2026-03-09"  # Friday + 1 -> Monday
    assert business("2026-03-13", -5) == "2026-03-06"  # five business days before
    assert business("2026-03-06", 1, ["2026-03-09"]) == "2026-03-10"
    assert business("2026-03-06", 0) == "2026-03-06"
    assert business("2026-03-06", 1.5) is None


def test_business_days_require_an_explicit_holiday_list():
    from pydantic import ValidationError

    from automationbench_v1.contracts.values import parse_value

    with pytest.raises(ValidationError):
        parse_value({"kind": "add_business_days", "date": {"kind": "input", "format": "iso_date", "literal": "2026-03-06"},
                     "days": {"kind": "input", "format": "number", "literal": 1}})
    with pytest.raises(ValidationError, match="value_business_day_holiday_invalid"):
        parse_value({"kind": "add_business_days", "date": {"kind": "input", "format": "iso_date", "literal": "2026-03-06"},
                     "days": {"kind": "input", "format": "number", "literal": 1}, "holidays": ["March 9"]})


@pytest.mark.parametrize("literal,expected", [("10:00", "600"), ("9:05", "545"), ("23:59", "1439"), ("24:00", None), ("10:00 PM", None)])
def test_clock_24h_for_declared_24_hour_data(literal, expected):
    assert value("clock_24h", literal) == expected
