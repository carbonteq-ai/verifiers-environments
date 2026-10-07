"""Bounded exact scalar derivations; public manifests own formulas and policy.

No row selection, totals, currency conversion semantics or host clock lives here.
Decimal arithmetic is rational internally, so no ambient precision rounds a
value before a manifest explicitly requests rounding.
"""

from __future__ import annotations

import math
import re
from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import Annotated, Literal

from pydantic import (
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_validator,
    model_validator,
)

from .base import FrozenModel

type Path = tuple[StrictStr | StrictInt, ...]


class NumberInputConstraints(FrozenModel):
    integral: StrictBool = False
    minimum_exclusive: StrictInt | StrictFloat | None = None

    @model_validator(mode="after")
    def finite_bound(self):
        value = self.minimum_exclusive
        if (type(value) is float and not math.isfinite(value)
                or type(value) is int and value.bit_length() > 426):
            raise ValueError("value_number_constraint_bound_invalid")
        return self


class DateInputConstraints(FrozenModel):
    day_of_month: StrictInt = Field(ge=1, le=31)


class ValueInput(FrozenModel):
    kind: Literal["input"]
    format: Literal[
        "number", "decimal_string", "percent_points_string", "usd_string", "usd_marked", "iso_date", "iso_timestamp",
        "clock_time", "clock_24h", "duration_text", "duration_clock", "iso_instant", "date_text",
        "iso_civil_datetime_date",
    ]
    path: Path | None = None
    literal: StrictStr | StrictInt | StrictFloat | None = None
    timestamp_timezone: Literal["UTC"] | None = None
    number_constraints: NumberInputConstraints | None = Field(default=None, exclude_if=lambda value: value is None)
    date_constraints: DateInputConstraints | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def input_shape(self):
        if (self.path is None) == (self.literal is None):
            raise ValueError("value_requires_exactly_one_field_or_literal")
        if self.path is not None and (not self.path or any(
            type(part) is int and part < 0 or type(part) is str and not part
            for part in self.path
        )):
            raise ValueError("value_path_invalid")
        if (self.format == "iso_timestamp") != (self.timestamp_timezone is not None):
            raise ValueError("value_timestamp_requires_explicit_timezone")
        if self.number_constraints is not None and self.format not in _DECIMAL_FORMATS:
            raise ValueError("value_number_constraints_require_numeric_format")
        if self.date_constraints is not None and self.format != "iso_date":
            raise ValueError("value_date_constraints_require_iso_date")
        return self


# Formats that evaluate to exact decimals: clock times are minutes since
# midnight, text durations are minutes, clock durations are seconds and ISO
# instants are UTC epoch seconds.
_DECIMAL_FORMATS = frozenset({
    "number", "decimal_string", "percent_points_string", "usd_string", "usd_marked", "clock_time", "clock_24h", "duration_text",
    "duration_clock", "iso_instant",
})
_CLOCK_12 = re.compile(r"(\d{1,2})(?::([0-5]\d)(?::([0-5]\d))?)?\s*([ap])\.?\s*m\.?", re.IGNORECASE)
# 24-hour forms are unambiguous only for 00–09 with a leading zero and 13–23;
# a meridiem-less 10:00–12:59 could be morning or evening.
_CLOCK_24 = re.compile(r"(0\d|1[3-9]|2[0-3]):([0-5]\d)(?::([0-5]\d))?")
# An ISO timestamp's time of day is 24-hour as written ("2026-02-03T10:00:00Z").
_CLOCK_ISO = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d)(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?",
    re.IGNORECASE,
)
_DURATION_PART = re.compile(
    r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)(?![a-z])", re.IGNORECASE
)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def clock_minutes(text) -> Fraction:
    """Minutes since midnight; a meridiem-less one-digit hour is ambiguous.

    Seconds ("14:00:00", "2:00:30 PM") are read; an ISO timestamp's time of
    day is taken as written (24-hour), whatever its offset.
    """
    if type(text) is not str or len(text) > 32:
        raise _Unavailable("value_clock_time_unavailable")
    raw = text.strip()
    if raw.lower() in {"noon", "12 noon"}:
        return Fraction(720)
    if raw.lower() in {"midnight", "12 midnight"}:
        return Fraction(0)
    match = _CLOCK_12.fullmatch(raw)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        if not 1 <= hour <= 12:
            raise _Unavailable("value_clock_time_unavailable")
        hour = hour % 12 + (12 if match.group(4).lower() == "p" else 0)
        return Fraction(hour * 60 + minute) + Fraction(int(match.group(3) or 0), 60)
    match = _CLOCK_24.fullmatch(raw) or _CLOCK_ISO.fullmatch(raw)
    if match:
        return Fraction(int(match.group(1)) * 60 + int(match.group(2))) + Fraction(int(match.group(3) or 0), 60)
    raise _Unavailable("value_clock_time_unavailable")


def clock_24h_minutes(text) -> Fraction:
    """Minutes since midnight for data declared 24-hour (e.g. a UTC "10:00")."""
    if type(text) is not str:
        raise _Unavailable("value_clock_time_unavailable")
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", text.strip())
    if match is None:
        raise _Unavailable("value_clock_time_unavailable")
    return Fraction(int(match.group(1)) * 60 + int(match.group(2)))


def duration_minutes(text) -> Fraction:
    """Minutes from unit-bearing text ("1 hour 30 min"); a bare number is unknown."""
    if type(text) is not str or len(text) > 64:
        raise _Unavailable("value_duration_unavailable")
    raw = text.strip().lower()
    total, position, parts = Fraction(0), 0, 0
    for match in _DURATION_PART.finditer(raw):
        between = raw[position:match.start()].strip(" ,")
        if between not in {"", "and"}:
            raise _Unavailable("value_duration_unavailable")
        amount = Fraction(Decimal(match.group(1)))
        total += amount * 60 if match.group(2).startswith("h") else amount
        position, parts = match.end(), parts + 1
    if not parts or raw[position:].strip(" .") not in {"", "long"}:
        raise _Unavailable("value_duration_unavailable")
    return total


def duration_seconds(text) -> Fraction:
    """Seconds from m:ss or h:mm:ss."""
    if type(text) is not str:
        raise _Unavailable("value_duration_clock_unavailable")
    match = re.fullmatch(r"(\d{1,4}):([0-5]\d)(?::([0-5]\d))?", text.strip())
    if match is None:
        raise _Unavailable("value_duration_clock_unavailable")
    first, second, third = int(match.group(1)), int(match.group(2)), match.group(3)
    if third is None:
        return Fraction(first * 60 + second)
    return Fraction(first * 3600 + second * 60 + int(third))


def instant_seconds(text) -> Fraction:
    """Exact UTC epoch seconds from an ISO timestamp with an explicit offset."""
    if type(text) is not str or len(text) > 64 or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,6})?)?"
        r"(?:Z|[+-](?:[01][0-9]|2[0-3]):?[0-5][0-9])", text) is None:
        raise _Unavailable("value_instant_unavailable")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise _Unavailable("value_instant_unavailable") from exc
    delta = moment - _EPOCH
    return Fraction(delta.days * 86400 + delta.seconds) + Fraction(delta.microseconds, 1_000_000)


# Month and weekday names shared with prose date mentions (predicates.py).
MONTH_NUMBERS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
WEEKDAY_NUMBERS = {
    "mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1, "wed": 2, "wednesday": 2, "thu": 3,
    "thur": 3, "thurs": 3, "thursday": 3, "fri": 4, "friday": 4, "sat": 5, "saturday": 5, "sun": 6,
    "sunday": 6,
}
_MONTH_NAME = r"([a-z]+)\.?"
_DATE_TEXT_FORMS = (
    # [Weekday,] Month D[st], YYYY
    re.compile(r"(?:([a-z]+)\.?,?\s+)?" + _MONTH_NAME + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})"),
    # [Weekday,] D[st] [of] Month[,] YYYY
    re.compile(r"(?:([a-z]+)\.?,?\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTH_NAME
               + r",?\s+(\d{4})"),
)


def calendar_day(year, month, day, weekday=None):
    """A valid date whose weekday, when stated, agrees; otherwise None."""
    try:
        value = date(year, month, day)
    except (ValueError, OverflowError):
        return None
    return value if weekday is None or value.weekday() == weekday else None


def date_from_text(text) -> date:
    """A stored human date with an explicit year ("February 3, 2026").

    Accepts ISO ``YYYY-MM-DD``, month-name forms in either order with an
    optional (checked) weekday, and ``M/D/YYYY`` only when the day-first
    reading is invalid or identical. Year-less, relative or contradictory
    text is unavailable.
    """
    if type(text) is not str or len(text) > 64:
        raise _Unavailable("value_date_text_unavailable")
    raw = text.strip().rstrip(".").strip().lower()
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if match:
        found = calendar_day(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if found is None:
            raise _Unavailable("value_date_text_unavailable")
        return found
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if match:
        first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        readings = {found for found in (calendar_day(year, first, second), calendar_day(year, second, first))
                    if found is not None}
        if len(readings) != 1:
            raise _Unavailable("value_date_text_ambiguous")
        return readings.pop()
    for index, pattern in enumerate(_DATE_TEXT_FORMS):
        match = pattern.fullmatch(raw)
        if match is None:
            continue
        weekday_name, first, second, year = match.groups()
        month_name, day = (first, second) if index == 0 else (second, first)
        weekday = None
        if weekday_name is not None:
            if weekday_name not in WEEKDAY_NUMBERS:
                break
            weekday = WEEKDAY_NUMBERS[weekday_name]
        if month_name not in MONTH_NUMBERS:
            continue
        found = calendar_day(int(year), MONTH_NUMBERS[month_name], int(day), weekday)
        if found is not None:
            return found
        break
    raise _Unavailable("value_date_text_unavailable")


class DecimalExpression(FrozenModel):
    kind: Literal["decimal"]
    op: Literal["add", "sub", "mul", "div"]
    left: ValueExpression
    right: ValueExpression


class NumberBranch(FrozenModel):
    # Raw predicate serialization avoids a values/predicates import cycle.
    # Admission and evaluation still use the shared typed predicate contract.
    when: dict
    value: ValueExpression

    @field_validator("when", mode="before")
    @classmethod
    def admit_predicate(cls, raw):
        from .predicates import parse_predicate

        return parse_predicate(raw).model_dump(mode="python")


class ConditionalNumber(FrozenModel):
    kind: Literal["conditional_number"]
    branches: tuple[NumberBranch, ...] = Field(min_length=1, max_length=16)


class RoundedValue(FrozenModel):
    kind: Literal["round"]
    value: ValueExpression
    scale: StrictInt = Field(ge=0, le=12)
    ties: Literal["half_even", "half_up", "unavailable_on_tie"]


class DateDifference(FrozenModel):
    kind: Literal["days_between"]
    start: ValueExpression
    end: ValueExpression


class DateInterval(FrozenModel):
    kind: Literal["within_interval"]
    value: ValueExpression
    start: ValueExpression
    end: ValueExpression
    include_start: StrictBool
    include_end: StrictBool


class BusinessDayOffset(FrozenModel):
    """Add whole business days (Mon–Fri) skipping explicitly declared holidays.

    ``holidays`` is required (possibly empty) so a manifest states its holiday
    assumption instead of inheriting an unknown calendar.
    """

    kind: Literal["add_business_days"]
    date: ValueExpression
    days: ValueExpression
    holidays: tuple[StrictStr, ...]

    @model_validator(mode="after")
    def iso_holidays(self):
        for value in self.holidays:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError as exc:
                raise ValueError("value_business_day_holiday_invalid") from exc
        if len(set(self.holidays)) != len(self.holidays) or len(self.holidays) > 366:
            raise ValueError("value_business_day_holiday_invalid")
        return self


class CalendarMonthOffset(FrozenModel):
    kind: Literal["add_calendar_months"]
    date: ValueExpression
    months: ValueExpression
    invalid_day: Literal["unavailable", "clamp"]


class BusinessDayDifference(FrozenModel):
    """Signed Mon–Fri count over (earlier, later], with explicit holidays."""

    kind: Literal["business_days_between"]
    start: ValueExpression
    end: ValueExpression
    holidays: tuple[StrictStr, ...]

    @model_validator(mode="after")
    def iso_holidays(self):
        for value in self.holidays:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError as exc:
                raise ValueError("value_business_day_holiday_invalid") from exc
        if len(set(self.holidays)) != len(self.holidays) or len(self.holidays) > 366:
            raise ValueError("value_business_day_holiday_invalid")
        return self


type ValueExpression = Annotated[
    ValueInput | DecimalExpression | RoundedValue | DateDifference | DateInterval | CalendarMonthOffset
    | BusinessDayOffset | BusinessDayDifference | ConditionalNumber,
    Field(discriminator="kind"),
]
for _model in (DecimalExpression, RoundedValue, DateDifference, DateInterval, CalendarMonthOffset,
               BusinessDayOffset, BusinessDayDifference, NumberBranch, ConditionalNumber):
    _model.model_rebuild()
VALUE_EXPRESSION = TypeAdapter(ValueExpression)


@dataclass(frozen=True)
class ValueResult:
    status: Literal["qualified", "unavailable"]
    kind: Literal["decimal", "calendar_date", "day_count", "boolean"] | None
    canonical_value: str | int | bool | None
    reason: str
    evidence_paths: tuple[Path, ...] = ()
    raw_values: tuple[tuple[Path, str | int | float | bool | None], ...] = ()
    rounding: tuple[tuple[int, str], ...] = ()


def parse_value(raw) -> ValueExpression:
    """Bound structure before recursive schema admission, including copied models."""
    # Preserve invalid copied scalar types for strict admission. JSON dumping
    # can serialize a bool in a declared integer path as 1 before validation.
    raw = raw.model_dump(mode="python") if hasattr(raw, "model_dump") else raw
    pending, nodes = [(raw, 0)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > 32 or nodes > 512:
            raise ValueError("value_structure_budget_exceeded")
        if isinstance(item, dict):
            pending.extend((value, depth + 1) for value in item.values())
        elif isinstance(item, (tuple, list)):
            pending.extend((value, depth + 1) for value in item)
    return VALUE_EXPRESSION.validate_python(raw)


class _Unavailable(Exception):
    pass


def _decimal(raw, format):
    if format == "number":
        if type(raw) not in {int, float} or type(raw) is float and not math.isfinite(raw):
            raise _Unavailable("value_numeric_input_unavailable")
        if type(raw) is int and raw.bit_length() > 426:
            raise _Unavailable("value_numeric_budget_exceeded")
        text = str(raw)
    else:
        if type(raw) is not str or len(raw) > 256:
            raise _Unavailable("value_decimal_text_unavailable")
        if format == "decimal_string":
            valid = re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", raw)
            text = raw
        elif format == "percent_points_string":
            # Explicit percentage-point units: -28% becomes -28, not -0.28.
            # Require the marker; no whitespace, localized forms or coercion.
            valid = re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?%", raw)
            text = raw[:-1]
        else:
            # Explicit USD format: optional dollar prefix (required for
            # usd_marked), leading minus, strict three-digit comma groups.
            # Parentheses/localized strings are gaps.
            dollar = r"\$" if format == "usd_marked" else r"\$?"
            valid = re.fullmatch(r"-?" + dollar + r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.[0-9]+)?", raw)
            text = raw.replace("$", "").replace(",", "")
        if valid is None:
            raise _Unavailable("value_decimal_format_unavailable")
    if len(text) > 256:
        raise _Unavailable("value_numeric_budget_exceeded")
    decimal = Decimal(text)
    parts = decimal.as_tuple()
    if len(parts.digits) > 128 or abs(int(parts.exponent)) > 128:
        raise _Unavailable("value_numeric_budget_exceeded")
    return Fraction(decimal)


def _resolve(input, context, evidence):
    if input.path is None:
        return input.literal
    raw = context
    for part in input.path:
        if type(part) is int:
            if not isinstance(raw, (tuple, list)) or part >= len(raw):
                evidence.append((input.path, None))
                raise _Unavailable("value_field_unavailable")
        elif not isinstance(raw, Mapping) or part not in raw:
            evidence.append((input.path, None))
            raise _Unavailable("value_field_unavailable")
        raw = raw[part]
    if type(raw) in {str, int, bool, type(None)} or type(raw) is float and math.isfinite(raw):
        evidence.append((input.path, raw))
    else:
        evidence.append((input.path, None))
    return raw


def _bounded(value):
    if isinstance(value, Fraction) and max(value.numerator.bit_length(), value.denominator.bit_length()) > 2048:
        raise _Unavailable("value_numeric_budget_exceeded")
    return value


def _evaluate(expr, context, evidence, rounding):
    if isinstance(expr, ConditionalNumber):
        from .predicates import evaluate_predicate, parse_predicate

        results = [evaluate_predicate(parse_predicate(branch.when), context) for branch in expr.branches]
        for result in results:
            for path in result.evidence_paths:
                raw = context
                try:
                    for part in path:
                        raw = raw[part]
                except (KeyError, IndexError, TypeError):
                    raw = None
                evidence.append((path, raw))
        if any(result.value is None for result in results):
            raise _Unavailable("value_conditional_input_unavailable")
        matches = [branch for branch, result in zip(expr.branches, results, strict=True) if result.value]
        if len(matches) != 1:
            raise _Unavailable("value_conditional_unmapped" if not matches else "value_conditional_ambiguous")
        kind, value = _evaluate(matches[0].value, context, evidence, rounding)
        if kind != "decimal":
            raise _Unavailable("value_conditional_result_type_unavailable")
        return kind, value
    if isinstance(expr, ValueInput):
        raw = _resolve(expr, context, evidence)
        if expr.format in _DECIMAL_FORMATS:
            parser = {"clock_time": clock_minutes, "clock_24h": clock_24h_minutes, "duration_text": duration_minutes,
                      "duration_clock": duration_seconds, "iso_instant": instant_seconds}.get(expr.format)
            value = _bounded(parser(raw) if parser else _decimal(raw, expr.format))
            constraints = expr.number_constraints
            if constraints is not None:
                if constraints.integral and value.denominator != 1:
                    raise _Unavailable("value_number_integral_constraint_unavailable")
                if (constraints.minimum_exclusive is not None
                        and value <= _decimal(constraints.minimum_exclusive, "number")):
                    raise _Unavailable("value_number_minimum_constraint_unavailable")
            return "decimal", value
        if type(raw) is not str or len(raw) > 64:
            raise _Unavailable("value_date_input_unavailable")
        try:
            if expr.format == "iso_date":
                value = date.fromisoformat(raw)
                if value.isoformat() != raw:
                    raise ValueError("noncanonical date")
            elif expr.format == "date_text":
                value = date_from_text(raw)
            elif expr.format == "iso_civil_datetime_date":
                if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?", raw) is None:
                    raise ValueError("naive ISO civil datetime required")
                value = datetime.fromisoformat(raw).date()
            else:
                if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", raw) is None:
                    raise ValueError("offset ISO timestamp required")
                timestamp = datetime.fromisoformat(raw)
                value = timestamp.astimezone(UTC).date()
        except (ValueError, OverflowError) as exc:
            raise _Unavailable("value_date_format_unavailable") from exc
        if expr.date_constraints is not None and value.day != expr.date_constraints.day_of_month:
            raise _Unavailable("value_date_day_constraint_unavailable")
        return "calendar_date", value
    if isinstance(expr, DecimalExpression):
        left_kind, left = _evaluate(expr.left, context, evidence, rounding)
        right_kind, right = _evaluate(expr.right, context, evidence, rounding)
        if left_kind != "decimal" or right_kind != "decimal":
            raise _Unavailable("value_arithmetic_type_unavailable")
        if expr.op == "div" and right == 0:
            raise _Unavailable("value_division_by_zero")
        result = {"add": lambda: left + right, "sub": lambda: left - right,
                  "mul": lambda: left * right, "div": lambda: left / right}[expr.op]()
        return "decimal", _bounded(result)
    if isinstance(expr, RoundedValue):
        kind, value = _evaluate(expr.value, context, evidence, rounding)
        if kind != "decimal":
            raise _Unavailable("value_rounding_type_unavailable")
        scaled = abs(value) * 10 ** expr.scale
        whole, remainder = divmod(scaled.numerator, scaled.denominator)
        comparison = 2 * remainder - scaled.denominator
        if comparison == 0 and expr.ties == "unavailable_on_tie":
            raise _Unavailable("value_rounding_tie_unavailable")
        if comparison > 0 or comparison == 0 and (expr.ties == "half_up" or whole % 2):
            whole += 1
        rounding.append((expr.scale, expr.ties))
        return "decimal", Fraction((-1 if value < 0 else 1) * whole, 10 ** expr.scale)
    if isinstance(expr, BusinessDayOffset):
        date_kind, value = _evaluate(expr.date, context, evidence, rounding)
        days_kind, days = _evaluate(expr.days, context, evidence, rounding)
        if date_kind != "calendar_date" or days_kind != "decimal" or days.denominator != 1:
            raise _Unavailable("value_business_day_type_unavailable")
        count, step = abs(days.numerator), 1 if days >= 0 else -1
        if count > 3660:
            raise _Unavailable("value_business_day_budget_exceeded")
        holidays = {date.fromisoformat(item) for item in expr.holidays}
        while count:
            value = date.fromordinal(value.toordinal() + step)
            if value.weekday() < 5 and value not in holidays:
                count -= 1
        return "calendar_date", value
    if isinstance(expr, CalendarMonthOffset):
        date_kind, value = _evaluate(expr.date, context, evidence, rounding)
        months_kind, months = _evaluate(expr.months, context, evidence, rounding)
        if date_kind != "calendar_date" or months_kind != "decimal" or months.denominator != 1:
            raise _Unavailable("value_calendar_month_type_unavailable")
        # This is declared calendar arithmetic, not a business-day/fiscal
        # calendar or an inferred coverage interval/rounding convention.
        year, month = divmod((value.year - 1) * 12 + value.month - 1 + months.numerator, 12)
        year, month = year + 1, month + 1
        if not 1 <= year <= 9999:
            raise _Unavailable("value_calendar_month_range_unavailable")
        final_day = monthrange(year, month)[1]
        if value.day > final_day and expr.invalid_day == "unavailable":
            raise _Unavailable("value_calendar_month_day_unavailable")
        return "calendar_date", date(year, month, min(value.day, final_day))
    start_kind, start = _evaluate(expr.start, context, evidence, rounding)
    end_kind, end = _evaluate(expr.end, context, evidence, rounding)
    if start_kind != "calendar_date" or end_kind != "calendar_date":
        raise _Unavailable("value_date_operation_type_unavailable")
    if isinstance(expr, DateDifference):
        return "day_count", (end - start).days
    if isinstance(expr, BusinessDayDifference):
        direction = 1 if end >= start else -1
        earlier, later = (start, end) if direction == 1 else (end, start)
        span = (later - earlier).days
        if span > 3660:
            raise _Unavailable("value_business_day_difference_budget_exceeded")
        holidays = {date.fromisoformat(item) for item in expr.holidays}
        total = sum(day.weekday() < 5 and day not in holidays
                    for ordinal in range(earlier.toordinal() + 1, later.toordinal() + 1)
                    for day in (date.fromordinal(ordinal),))
        return "day_count", direction * total
    value_kind, value = _evaluate(expr.value, context, evidence, rounding)
    if value_kind != "calendar_date" or start > end:
        raise _Unavailable("value_date_interval_unavailable")
    return "boolean", (start <= value if expr.include_start else start < value) and (
        value <= end if expr.include_end else value < end)


def _canonical_decimal(value):
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    scale = max(twos, fives)
    if denominator != 1:
        raise _Unavailable("value_nonterminating_decimal_requires_rounding")
    if scale > 128:
        raise _Unavailable("value_numeric_budget_exceeded")
    coefficient = value.numerator * 2 ** (scale - twos) * 5 ** (scale - fives)
    digits = str(abs(coefficient))
    if len(digits) > 128:
        raise _Unavailable("value_numeric_budget_exceeded")
    if scale:
        digits = digits.zfill(scale + 1)
        digits = (digits[:-scale] + "." + digits[-scale:]).rstrip("0").rstrip(".")
    return ("-" if coefficient < 0 else "") + digits


def evaluate_value(expr, context: Mapping) -> ValueResult:
    """Return typed scalar evidence; missing inputs never become numeric zero."""
    expr = parse_value(expr)
    evidence, rounding = [], []
    try:
        kind, value = _evaluate(expr, context, evidence, rounding)
        canonical = _canonical_decimal(value) if kind == "decimal" else value.isoformat() if kind == "calendar_date" else value
        status, reason = "qualified", "value_exact_derivation"
    except _Unavailable as exc:
        kind, canonical, status, reason = None, None, "unavailable", str(exc)
    paths = tuple(dict.fromkeys(path for path, _ in evidence))
    # Include unresolved declared paths as well as raw inputs that were found.
    if isinstance(expr, ValueInput) and expr.path is not None and expr.path not in paths:
        paths = (*paths, expr.path)
    return ValueResult(status, kind, canonical, reason, paths, tuple(evidence), tuple(rounding))


def evaluate_exact_decimal(expr, context: Mapping) -> tuple[Fraction | None, str, tuple[Path, ...]]:
    """The exact rational value of a decimal derivation, even when non-terminating.

    ``evaluate_value`` requires a terminating canonical decimal (a repeating
    quotient needs explicit rounding). Declared mention precision compares a
    written number with the exact value at the written number's own places, so
    it needs the unrounded rational. Missing inputs stay unavailable.
    """
    expr = parse_value(expr)
    evidence, rounding = [], []
    try:
        kind, value = _evaluate(expr, context, evidence, rounding)
        if kind != "decimal":
            raise _Unavailable("value_exact_decimal_type_unavailable")
        result, reason = value, "value_exact_derivation"
    except _Unavailable as exc:
        result, reason = None, str(exc)
    return result, reason, tuple(dict.fromkeys(path for path, _ in evidence))


def round_places(value: Fraction, places: int, ties: str) -> Fraction:
    """``value`` rounded to ``places`` decimals with ``half_up``/``half_even`` ties."""
    scaled = abs(value) * 10 ** places
    whole, remainder = divmod(scaled.numerator, scaled.denominator)
    comparison = 2 * remainder - scaled.denominator
    if comparison > 0 or comparison == 0 and (ties == "half_up" or whole % 2):
        whole += 1
    return Fraction((-1 if value < 0 else 1) * whole, 10 ** places)
