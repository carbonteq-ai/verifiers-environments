"""Successful nonmutating calls must not certify absence of read evidence."""

import json

import pytest
import test_manifest_gmail_observations as gmail
import test_manifest_slack_reads as slack

from automationbench_v1.capture import canonical_json


@pytest.mark.parametrize("adapter", [gmail, slack], ids=["gmail", "slack"])
@pytest.mark.parametrize("persistence", ["unchanged", "not_attempted"])
def test_successful_unacknowledged_reads_leave_inventory_open(adapter, persistence):
    call = gmail.read() if adapter is gmail else slack.read_other()
    source = adapter.material([call])
    baseline = adapter.evidence(source)
    assert baseline.complete and adapter.positive(baseline)
    source["state_write_receipts"] = []
    source["tool_state_revision"] = 0
    for event in source["tool_execution_events"]:
        receipt = json.loads(event["receipt_json"])
        if receipt["phase"] == "returned":
            receipt.update(state_persistence=persistence, state_write_revision=None, state_conflict=None)
        event["receipt_json"] = canonical_json(receipt)
    value = adapter.evidence(source)
    assert not value.complete
    assert not adapter.positive(value)
