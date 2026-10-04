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


def _exclusive(text, terms, excluded, scope="line", context=None):
    from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate

    def term(value, mode="amount", fmt="usd_string"):
        operand = value if isinstance(value, dict) else {"kind": "literal", "value": value}
        return {"value": operand, "mode": mode, **({"format": fmt} if mode in {"amount", "amount_reformatted"} else {})}

    raw = {"op": "mentions_together", "text": {"kind": "field", "path": ["t"], "domain": "string"}, "scope": scope,
           "terms": [term(*item) if isinstance(item, tuple) else term(item) for item in terms],
           "excluding_values": [term(*item) if isinstance(item, tuple) else term(item) for item in excluded]}
    return evaluate_predicate(parse_predicate(raw), {"t": text, **(context or {})}).value


SHARES = ["$1,500", "$900"]


@pytest.mark.parametrize("text,expected", [
    ("Engineering: $4,000\nSales: $1,500\nOperations: $900", True),          # correct line
    ("Engineering: $4,000 / $1,500 / $900", False),                          # every share listed on one line
    ("Engineering: $4,000 (or $900)\nEngineering: $4,000", True),            # a clean line still counts
    ("Engineering: $4,000 or $1.5k", False),                                 # excluded value in another form
    ("Engineering: $4,000 or 0.0015m", None),                                 # could be an excluded value
    ("Sales: $1,500", False),
    ("> Engineering: $4,000", None),
])
def test_excluded_values_must_be_absent_from_the_matched_line(text, expected):
    assert _exclusive(text, [("Engineering", "words"), "$4,000"], SHARES) is expected


def test_excluded_value_in_an_unreadable_line_of_the_block_is_unknown():
    terms = [("Engineering", "words"), "$4,000"]
    assert _exclusive("Engineering\n$4,000\n\nSales $1,500", terms, SHARES, "block") is True
    assert _exclusive("Engineering\n$4,000\nSales $1,500", terms, SHARES, "block") is False
    assert _exclusive("Engineering\n$4,000\n> was $900", terms, SHARES, "block") is None


def test_unknown_excluded_values_propagate():
    terms = [("Engineering", "words"), "$4,000"]
    missing = {"kind": "field", "path": ["request", "Other"], "domain": "string"}
    assert _exclusive("Engineering: $4,000", terms, [missing]) is None
    assert _exclusive("Engineering: $4,000", terms, [missing], context={"request": {"Other": "$900"}}) is True
    assert _exclusive("Engineering: $4,000 $900", terms, [missing], context={"request": {"Other": "$900"}}) is False


def test_record_values_text_is_one_unit():
    from automationbench_v1.contracts.record_writes import _values_text

    clean = _values_text({"name": "Engineering charge", "amount": 4000, "notes": "Approved"})
    gamed = _values_text({"name": "Engineering charge", "amount": 4000, "notes": "or 1500 or 900"})
    terms = [("Engineering", "words"), ("4000", "amount", "decimal_string")]
    excluded = [("1500", "amount", "decimal_string"), ("900", "amount", "decimal_string")]
    assert _exclusive(clean, terms, excluded, "text") is True
    assert _exclusive(gamed, terms, excluded, "text") is False


def test_single_term_needs_exclusions_and_empty_exclusions_are_not_dumped():
    from pydantic import ValidationError

    from automationbench_v1.contracts.predicates import parse_predicate

    body = {"kind": "field", "path": ["t"], "domain": "string"}
    one = [{"value": {"kind": "literal", "value": "$4,000"}, "mode": "amount", "format": "usd_string"}]
    with pytest.raises(ValidationError, match="requires_two_terms_or_exclusions"):
        parse_predicate({"op": "mentions_together", "text": body, "terms": one})
    single = parse_predicate({"op": "mentions_together", "text": body, "terms": one, "scope": "text",
                              "excluding_values": one})
    assert single.model_dump(mode="json")["excluding_values"]
    plain = parse_predicate({"op": "mentions_together", "text": body, "terms": one * 2})
    assert "excluding_values" not in plain.model_dump(mode="json")
    assert _exclusive("Total $4,000", ["$4,000"], ["$900"], "text") is True
    assert _exclusive("Total $4,000, $900", ["$4,000"], ["$900"], "text") is False
