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
