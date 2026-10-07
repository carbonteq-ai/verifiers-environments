"""Manifest inputs read tool-server receipts; harness hook events are not executions."""

import json
from types import SimpleNamespace

from automationbench_v1.manifest_assessments import _source_material


def test_harness_hook_events_are_excluded_from_manifest_inventory():
    server = {"source": "tool_server", "phase": "dispatch", "invocation_id": "i1", "receipt_seq": 1,
              "receipt_json": json.dumps({"invocation_id": "i1", "phase": "dispatch"})}
    hooks = [{"source": "harness", "phase": phase, "execution_id": "x1", "event_index": index,
              "request_json": "{}", "decision_json": "{}"} for index, phase in enumerate(("before", "dispatch", "after"))]
    write = {"write_id": "i1", "expected_revision": 0, "applied_revision": 1, "conflict": False}
    snapshot = SimpleNamespace(source_json=json.dumps({
        "task_evidence": {"prompt": [], "initial": {}},
        "tool_execution_events": [hooks[0], hooks[1], server, hooks[2]],
        "state_write_receipts": [write]}))
    material = _source_material(snapshot)
    assert material["tool_execution_events"] == [server]
    assert material["state_write_receipts"] == [write]
    assert all("receipt_json" in event for event in material["tool_execution_events"])
