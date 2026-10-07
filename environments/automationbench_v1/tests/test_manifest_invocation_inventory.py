"""Coverage-only reconciliation; native envelopes wrap genuine simulator reads."""

import copy
import json

import pytest
from test_manifest_authored_outputs import sdk
from test_manifest_gmail_observations import material, read

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.invocation_inventory import (
    InvocationInventory,
    capture_invocation_inventory,
    validate_invocation_inventory,
)


def source(*, repeated=False):
    value = material([read(), read()] if repeated else [read()])
    entries = capture_invocation_inventory(value).entries
    events = [{"kind": "mcp_inventory", "scope": "thread_bound", "servers": [
        {"name": "native-server", "runtime_status": "connected", "tool_names": ["execute_tool"]}]}]
    for index, entry in enumerate(entries):
        assert entry.outer_arguments_json is not None and entry.result_json is not None
        item = {"id": f"sdk-{index}", "type": "mcpToolCall", "server": "native-server", "tool": entry.outer_tool,
            "arguments": json.loads(entry.outer_arguments_json), "error": None, "status": "inProgress", "result": None}
        params = {"threadId": "thread-1", "turnId": "turn-1", "item": copy.deepcopy(item)}
        events.append({"kind": "event", "event": {"method": "item/started", "params": params}})
        item["status"] = "completed"
        text = json.loads(entry.result_json)
        item["result"] = {"content": [{"type": "text", "text": text}], "structuredContent": {"result": text}}
        events.append({"kind": "event", "event": {"method": "item/completed", "params": {**params, "item": item}}})
    events.extend(sdk()["sdk_info"]["events"][1:])
    value["task_evidence"]["authored_outputs"] = sdk(events)
    from test_manifest_authored_outputs import replace_sdk_payload

    def controller(payload):
        payload.update(server_aliases={"": "native-server"}, approved_mcp_tools={"native-server": ["execute_tool"]})
    value["task_evidence"]["authored_outputs"] = replace_sdk_payload(value["task_evidence"]["authored_outputs"], controller)
    return value


def change_sdk(value, change):
    from test_manifest_authored_outputs import replace_sdk_payload

    value = copy.deepcopy(value)
    value["task_evidence"]["authored_outputs"] = replace_sdk_payload(value["task_evidence"]["authored_outputs"], change)
    return value


def completed(payload):
    return next(event["event"]["params"]["item"] for event in payload["events"]
        if event.get("kind") == "event" and event["event"]["method"] == "item/completed")


def test_unique_native_sdk_populations_qualify_coverage_without_call_identity_claim():
    value = source()
    result = capture_invocation_inventory(value)
    assert result.closed and len(result.entries) == len(result.sdk_coverage_pairs) == 1
    entry = result.entries[0]
    assert entry.status == "qualified" and entry.operation == "gmail_get_email_by_id"
    assert entry.before_json and entry.after_json and entry.action_json
    assert result.sdk_coverage_pairs[0].sdk_item_id != result.sdk_coverage_pairs[0].native_invocation_id


def test_repeated_equal_calls_are_ambiguous_without_erasing_known_native_entries():
    result = capture_invocation_inventory(source(repeated=True))
    assert not result.closed and not result.sdk_coverage_pairs
    assert len(result.entries) == 2 and all(entry.status == "qualified" for entry in result.entries)


@pytest.mark.parametrize("change", ["structured", "is-error", "error", "started-arguments", "started-server", "started-tool",
    "foreign-server", "wrong-text", "wrong-args", "no-declaration"])
def test_sdk_population_and_response_channels_are_exact(change):
    def alter(payload):
        item = completed(payload)
        if change == "structured":
            item["result"]["structuredContent"]["result"] = "Contradictory"
        elif change == "is-error":
            item["result"]["isError"] = True
        elif change == "error":
            item["error"] = {"message": "failed"}
        elif change.startswith("started-"):
            start = next(event["event"]["params"]["item"] for event in payload["events"]
                if event.get("kind") == "event" and event["event"]["method"] == "item/started")
            if change == "started-arguments":
                start["arguments"]["arguments"] = "{}"
            else:
                start[change.removeprefix("started-")] = "foreign"
        elif change == "foreign-server":
            item["server"] = "foreign"
        elif change == "wrong-text":
            item["result"]["content"][0]["text"] = "Wrong text"
        elif change == "wrong-args":
            item["arguments"]["arguments"] = "{}"
        else:
            payload["events"].pop(0)
    result = capture_invocation_inventory(change_sdk(source(), alter))
    assert not result.closed and result.entries[0].status == "qualified"


@pytest.mark.parametrize("change", ["missing-ack", "missing-dispatch", "missing-return", "local-error", "native-result", "args-bool", "unfinished"])
def test_native_missing_or_incoherent_material_keeps_coverage_open(change):
    value = source()
    events = value["tool_execution_events"]
    if change == "missing-ack":
        value["state_write_receipts"] = []
    elif change == "missing-dispatch":
        events.pop(0)
    elif change == "missing-return":
        events.pop()
    elif change == "unfinished":
        value["task_evidence"]["complete"] = False
    else:
        receipt = json.loads(events[-1]["receipt_json"])
        if change == "local-error":
            raw = json.loads(receipt["evidence_json"][0])
            raw["action"]["error_json"] = canonical_json({"message": "failed"})
            receipt["evidence_json"][0] = canonical_json(raw)
        elif change == "native-result":
            receipt["result_json"] = canonical_json("Wrong result")
        else:
            args = json.loads(receipt["arguments_json"])
            args["kwargs"]["arguments"] = True
            receipt["arguments_json"] = canonical_json(args)
        events[-1]["receipt_json"] = canonical_json(receipt)
    assert not capture_invocation_inventory(value).closed


def test_non_sdk_projection_does_not_invent_complete_model_tool_inventory():
    value = material([read()])
    result = capture_invocation_inventory(value)
    assert not result.closed and result.entries[0].status == "qualified"
    assert result.reason == "invocation_model_inventory_unavailable"


def test_known_entry_survives_later_capture_loss():
    value = source(repeated=True)
    receipt = json.loads(value["tool_execution_events"][-1]["receipt_json"])
    receipt["evidence_json"] = []
    value["tool_execution_events"][-1]["receipt_json"] = canonical_json(receipt)
    result = capture_invocation_inventory(value)
    assert not result.closed and [entry.status for entry in result.entries] == ["qualified", "unavailable"]


def test_reload_and_copied_labels_are_raw_source_bound():
    value = source()
    inventory = capture_invocation_inventory(value)
    validate_invocation_inventory(InvocationInventory.model_validate_json(inventory.model_dump_json()), value)
    for fake in (inventory.model_copy(update={"closed": 1}), inventory.model_copy(update={"entries": (
            inventory.entries[0].model_copy(update={"operation": "invented"}),)})):
        with pytest.raises(ValueError):
            validate_invocation_inventory(fake, value)
    value["task_evidence"]["complete"] = False
    with pytest.raises(ValueError):
        validate_invocation_inventory(inventory, value)


def test_foreign_declared_server_does_not_bind_original_native_namespace():
    def alter(payload):
        payload["events"][0]["servers"][0]["name"] = "foreign-server"
        for event in payload["events"]:
            if event.get("kind") == "event" and event["event"]["method"] in {"item/started", "item/completed"}:
                event["event"]["params"]["item"]["server"] = "foreign-server"
    result = capture_invocation_inventory(change_sdk(source(), alter))
    assert not result.closed and result.entries[0].status == "qualified"


def test_known_native_entry_survives_later_malformed_receipt():
    value = source(repeated=True)
    value["tool_execution_events"][-1]["receipt_json"] = "not JSON"
    result = capture_invocation_inventory(value)
    assert not result.closed and result.entries[0].status == "qualified"


@pytest.mark.parametrize("change", ["body", "conflict-int"])
def test_write_acknowledgement_revalidates_digest_shape_and_boolean_metadata(change):
    value = source()
    ack = value["state_write_receipts"][0]
    if change == "body":
        ack["body_digest"] = "invalid"
    else:
        ack["conflict"] = 0
    result = capture_invocation_inventory(value)
    assert not result.closed and result.entries[0].status == "unavailable"
