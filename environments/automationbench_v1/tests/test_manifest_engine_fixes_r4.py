"""Round-4 engine fixes: amount punctuation, magnitudes, 24-hour ranges, guard
lookup outcomes, contract caching and same-scope exclusions."""

import pytest
from test_manifest_mentions import mentions

from automationbench_v1.contracts.predicates import _NUMBER


@pytest.mark.parametrize("text,value,expected", [
    ("spend $8,420, no sign-off", "$8,420", True),
    ("spend 8420, no sign-off", "$8,420", True),
    ("spend $8,420,000, no", "$8,420", False),
    ("12,500 views, 245 shares", "$8,420", False),
    ("$1, $2", "$2", True),
    ("Totals: 8,420", "$8,420", True),
])
def test_a_trailing_comma_is_punctuation_not_a_digit_group(text, value, expected):
    assert mentions(text, value, "amount", "usd_string")[0] is expected


def test_number_tokens_keep_digit_groups_and_split_lists():
    assert [m.group(0) for m in _NUMBER.finditer("$8,420, $1, $2 and 1,000,000,")] == ["$8,420", "$1", "$2", "1,000,000"]


@pytest.mark.parametrize("text,value,expected", [
    ("NovaTech SaaS total contract value: $120k", "$25,000", False),
    ("NovaTech SaaS total contract value: $120k, renewal $25,000", "$25,000", True),
    ("Contract value: $120k", "$120,000", True),
    ("Contract value: $120K", "$120,000", True),
    ("Contract value: $120k", "$120,400", None),   # could be rounded
    ("Contract value: $4.2k", "$4,250", None),
    ("Contract value: $4.2k", "$4,300", False),
    ("Budget $1.2m", "$1,200,000", True),
    ("Budget 1.2m", "$1,200,000", None),            # bare m: unit reading stays open
    ("Budget 1.2m", "$25,000", False),
    ("Budget $2b", "$2,000,000,000", True),
])
def test_magnitude_suffixes_only_block_plausible_values(text, value, expected):
    assert mentions(text, value, "amount", "usd_string")[0] is expected


def test_magnitude_suffix_does_not_hide_unrelated_reformatted_amounts():
    assert mentions("Total contract value: $120k", "$25,000", "amount_reformatted", "usd_string")[0] is False
    assert mentions("Total: $120k vs 25000", "$25,000", "amount_reformatted", "usd_string")[0] is True


@pytest.mark.parametrize("text,value,expected", [
    ("Break confirmed 13:00-13:30, 30 minutes.", "1:00 PM", True),
    ("Break confirmed 13:00-13:30, 30 minutes.", "1:30 PM", True),
    ("Break confirmed 13:00 - 13:30.", "1:00 PM", True),
    ("Break confirmed 13:00–13:30.", "1:00 PM", True),
    ("Shift 09:00 to 17:00", "9:00 AM", True),
    ("Shift 9:00-17:00", "9:00 AM", True),
    ("Shift 22:00-02:00", "2:00 AM", True),
    ("Break confirmed 13:00-13:30.", "2:00 PM", False),
    ("Break 10:00-11:30", "10:00 AM", None),         # both ends could be 12-hour
    ("Break 1:00-1:30 PM.", "1:00 PM", True),
])
def test_24_hour_ranges_yield_both_endpoints(text, value, expected):
    assert mentions(text, value, "clock_time")[0] is expected


def _guard(prohibited, lookups=None):
    from automationbench_v1.contracts import guards

    field = {"kind": "field", "path": ["request", "Email"], "domain": "string"}
    return guards.GuardCheck.model_validate({
        "check_id": "g", "signal_id": "s.g", "role": "harm", "operator": "effects.prohibited_when@1",
        "population": "rows", "source": "e",
        "lookups": lookups if lookups is not None else [{"source": "mail", "alias": "mail", "keys": {"From": field}}],
        "prohibited_when": prohibited,
        "effect_match": {"op": "eq", "left": {"kind": "literal", "value": 1}, "right": {"kind": "literal", "value": 1}}})


def _status_is(alias, status):
    return {"op": "eq", "left": {"kind": "field", "path": ["lookup", alias], "domain": "string"},
            "right": {"kind": "literal", "value": status}}


def _mail_population(messages, closed=True):
    from automationbench_v1.contracts.populations import InitialCollectionSource, capture_population

    source = InitialCollectionSource.model_validate({
        "path": ["task_evidence", "initial", "gmail", "messages"], "fields": {"From": ["from_"], "Id": ["id"]},
        "key_fields": ["From"]})
    return capture_population({"task_evidence": {"initial": {"gmail": {"messages": messages}}}}, source)


class _Row:
    identity = ("google_sheets.rows@1", "s", "w", "2")
    native_record_id = "2"

    def __init__(self, email):
        from automationbench_v1.capture import canonical_json

        self.cells_json = canonical_json({"Email": email})


@pytest.mark.parametrize("messages,email,status,expected", [
    ([{"id": "m1", "from_": "bob@x"}], "alice@x", "not_found", True),
    ([{"id": "m1", "from_": "alice@x"}], "alice@x", "not_found", False),
    ([{"id": "m1", "from_": "alice@x"}], "alice@x", "matched", True),
    ([{"id": "m1", "from_": "alice@x"}, {"id": "m2", "from_": "alice@x"}], "alice@x", "not_found", None),
])
def test_guards_publish_decided_lookup_outcomes(messages, email, status, expected):
    from automationbench_v1.contracts import guards
    from automationbench_v1.contracts.predicates import evaluate_predicate

    guard = _guard(_status_is("mail", status))
    context = guards._candidate_context(guard, _Row(email), {"mail": _mail_population(messages)})
    assert evaluate_predicate(guard.prohibited_when, context).value is expected


@pytest.mark.parametrize("path", [["lookup", "other"], ["lookup"], ["lookup", "mail", "x"]])
def test_guard_lookup_status_references_are_closed(path):
    from pydantic import ValidationError

    prohibited = {"op": "eq", "left": {"kind": "field", "path": path, "domain": "string"},
                  "right": {"kind": "literal", "value": "not_found"}}
    with pytest.raises(ValidationError, match="guard_lookup_status_reference_unknown"):
        _guard(prohibited)
