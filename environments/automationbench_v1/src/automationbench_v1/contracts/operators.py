"""Small deterministic check vocabulary, independent of task identity or credit."""

import json
from datetime import datetime
from decimal import Decimal

from .evidence import RecordEvidence


def field_equal(actual, expected) -> bool:
    if expected.comparison == "string":
        return isinstance(actual, str) and actual == expected.value
    if expected.comparison in {"number", "integer"}:
        if type(actual) not in {int, float} or type(expected.value) not in {int, float}:
            return False
        if expected.comparison == "integer" and type(actual) is not int:
            return False
        left, right = Decimal(str(actual)), Decimal(str(expected.value))
        return left.is_finite() and right.is_finite() and left == right
    if expected.comparison == "calendar_date":
        if not isinstance(actual, str) or not isinstance(expected.value, str):
            return False
        try:
            return datetime.fromisoformat(actual).date().isoformat() == expected.value
        except ValueError:
            return False
    raise ValueError("manifest_comparison_unsupported")


def fields_equal(record: dict, expected) -> bool:
    return all(item.field in record and field_equal(record[item.field], item) for item in expected)


def record_fields_equal(check, evidence: RecordEvidence) -> tuple[float | None, str]:
    if evidence.final_json is None or evidence.initial_json is None or not evidence.complete:
        return None, "record_terminal_state_unavailable"
    final = json.loads(evidence.final_json)
    if any(item.field not in final for item in check.expected):
        return None, "record_field_unavailable"
    return float(fields_equal(final, check.expected)), "observed_terminal_record_state"


def record_coverage(check, evidence: RecordEvidence) -> tuple[float | None, str]:
    del check
    return (1.0 if evidence.recording_complete else None), evidence.reason


OPERATORS = {
    "record.fields_equal@1": record_fields_equal,
    "record.coverage@1": record_coverage,
}
