"""Authored text authority and inventory, without semantic report judgments."""

import base64
import copy
import hashlib
import json

import pytest

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.authored_outputs import (
    AuthoredOutputEvidence,
    AuthoredOutputSource,
    capture_authored_outputs,
    validate_authored_outputs,
)


def projection(**changes):
    return {"schema_version": 1, "trace_id": "trace-1", "complete": True, "sdk_declared": False,
        "sdk_info": None, "sdk_artifact_base64": None, "sdk_artifact_sha256": None,
        "native_nodes": [{"node": 0, "parent": None, "sampled": False, "role": "user", "content": "Requested task"},
                         {"node": 1, "parent": 0, "sampled": True, "role": "assistant", "content": "Done."}],
        "native_calls": [{"node": 1, "finish_reason": "stop", "failed": False}], **changes}


def source(value):
    return {"task_evidence": {"authored_outputs": value}}


def capture(value):
    return capture_authored_outputs(source(value), AuthoredOutputSource())


def completed(identity="output-1", text="Done.", **changes):
    return {"kind": "event", "event": {"method": "item/completed", "params": {
        "threadId": "thread-1", "turnId": "turn-1", "item": {
            "id": identity, "type": "agentMessage", "text": text, "phase": "final_answer", **changes}}}}


def sdk(events=None):
    events = events if events is not None else [completed(), {"kind": "event", "event": {"method": "turn/completed", "params": {
        "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed", "error": None}}}},
        {"kind": "finished", "ok": True, "status": "completed", "turn_id": "turn-1", "thread_id": "thread-1"}]
    payload = {"events": events, "token_alignment": "unavailable"}
    raw = canonical_json(payload).encode()
    return projection(sdk_declared=True, sdk_info=payload, sdk_artifact_base64=base64.b64encode(raw).decode(),
        sdk_artifact_sha256=hashlib.sha256(raw).hexdigest(), native_nodes=[], native_calls=[])


def replace_sdk_payload(value, mutate):
    payload = copy.deepcopy(value["sdk_info"])
    mutate(payload)
    raw = canonical_json(payload).encode()
    return {**value, "sdk_info": payload, "sdk_artifact_base64": base64.b64encode(raw).decode(),
            "sdk_artifact_sha256": hashlib.sha256(raw).hexdigest()}


def isolated_sdk_events():
    # A manufactured transport fixture, not an executed solver trajectory.
    from verifiers.v1.harnesses.codex_sdk import worker

    return [
        {"kind": "thread_started", "response": {"thread": {"id": "thread-1"}}},
        {"kind": "builtin_tool_isolation", "revision": worker.BUILTIN_TOOL_ISOLATION,
         "scope": "loaded_thread", "thread_id": "thread-1",
         "disabled_features": dict(worker.DISABLED_BUILTIN_FEATURES)},
        {"kind": "turn_started", "response": {"turn": {"id": "turn-1"}}},
        *sdk()["sdk_info"]["events"],
    ]


def test_sdk_isolation_metadata_preserves_closed_output_and_raw_coordinates():
    value = sdk(isolated_sdk_events())
    raw = base64.b64decode(value["sdk_artifact_base64"], validate=True)
    result = capture(value)
    assert result.closed and [record.text for record in result.records] == ["Done."]
    assert result.records[0].source_path[-4:] == (3, "event", "params", "item")
    validate_authored_outputs(result, source(value), AuthoredOutputSource())
    assert base64.b64decode(value["sdk_artifact_base64"], validate=True) == raw
    # The existing format does not require a new runtime proof retroactively.
    assert capture(sdk()).closed


@pytest.mark.parametrize("mutation", [
    "zero", "float", "string", "true", "missing-feature", "extra-feature",
    "revision", "scope", "thread", "extra-field", "duplicate",
    "before-thread", "after-turn", "after-output", "after-finish",
])
def test_invalid_sdk_isolation_metadata_keeps_text_but_cannot_close_capture(mutation):
    events = isolated_sdk_events()
    proof = events[1]
    if mutation in {"zero", "float", "string", "true"}:
        proof["disabled_features"]["image_generation"] = {
            "zero": 0, "float": 0.0, "string": "false", "true": True}[mutation]
    elif mutation == "missing-feature":
        del proof["disabled_features"]["image_generation"]
    elif mutation == "extra-feature":
        proof["disabled_features"]["future_tool"] = False
    elif mutation in {"revision", "scope", "thread"}:
        proof[{"thread": "thread_id"}.get(mutation, mutation)] = "unknown"
    elif mutation == "extra-field":
        proof["text"] = "An unrecognized output channel"
    elif mutation == "duplicate":
        events.insert(2, copy.deepcopy(proof))
    else:
        events.pop(1)
        events.insert({"before-thread": 0, "after-turn": 2, "after-output": 3,
                       "after-finish": len(events)}[mutation], proof)
    result = capture(sdk(events))
    assert not result.closed and result.status == "partial"
    assert result.reason == "authored_output_sdk_isolation_metadata_unavailable"
    assert [record.text for record in result.records] == ["Done."]


def test_native_generation_inventory_retains_text_excluding_supplied_history_and_tools():
    value = projection()
    value["native_nodes"] += [{"node": 2, "parent": 1, "sampled": False, "role": "assistant", "content": "Supplied prior text"},
                              {"node": 3, "parent": 2, "sampled": False, "role": "tool", "content": "Secret tool body"}]
    result = capture(value)
    assert result.closed and [record.text for record in result.records] == ["Done."]
    assert result.records[0].output_id == "native-node:1"


def test_native_nonempty_complete_tool_only_calls_prove_empty_text_but_absent_calls_do_not():
    value = projection()
    value["native_nodes"][1]["content"] = None
    value["native_calls"][0]["finish_reason"] = "tool_calls"
    assert capture(value).closed and not capture(value).records
    assert not capture(projection(native_nodes=[], native_calls=[])).closed


@pytest.mark.parametrize("field,bad", [("node", True), ("node", 1.0), ("node", "1"), ("sampled", 1), ("parent", False)])
def test_native_copied_metadata_types_are_not_coerced(field, bad):
    value = projection()
    value["native_nodes"][1][field] = bad
    result = capture(value)
    assert not result.closed and not result.records


@pytest.mark.parametrize("change", ["failed", "length", "missing-node", "duplicate-node", "unlinked", "multimodal", "incomplete"])
def test_incomplete_native_inventory_never_establishes_silence(change):
    value = projection()
    if change == "failed":
        value["native_calls"][0]["failed"] = True
    elif change == "length":
        value["native_calls"][0]["finish_reason"] = "length"
    elif change == "missing-node":
        value["native_calls"][0]["node"] = 5
    elif change == "duplicate-node":
        value["native_nodes"].append(copy.deepcopy(value["native_nodes"][1]))
    elif change == "unlinked":
        value["native_calls"] = []
    elif change == "multimodal":
        value["native_nodes"][1]["content"] = [{"type": "image", "url": "unknown"}]
    else:
        value["complete"] = False
    assert not capture(value).closed


def test_native_text_parts_preserve_original_text_without_tool_or_reasoning_extraction():
    value = projection()
    value["native_nodes"][1]["content"] = [{"type": "text", "text": "Done"}, {"type": "text", "text": "."}]
    assert capture(value).records[0].text == "Done."


def test_sdk_original_completed_agent_messages_include_commentary_and_final():
    value = sdk()
    value = replace_sdk_payload(value, lambda payload: payload["events"].insert(0,
        completed("commentary-1", "Checking records.", phase="commentary", channel="commentary")))
    result = capture(value)
    assert result.closed and [record.text for record in result.records] == ["Checking records.", "Done."]
    assert result.records[0].channel == "commentary" and result.records[1].channel is None


def test_sdk_ignores_delta_reasoning_and_mcp_body_as_authored_completed_messages():
    value = sdk()
    def alter(payload):
        payload["events"][:0] = [{"kind": "event", "event": {"method": "item/agentMessage/delta", "params": {
            "itemId": "output-1", "turnId": "turn-1", "threadId": "thread-1", "delta": "Injected delta"}}},
            completed("reasoning", "Private reasoning", type="reasoning"), completed("tool", "MCP tool body", type="mcpToolCall")]
    result = capture(replace_sdk_payload(value, alter))
    assert result.closed and [record.text for record in result.records] == ["Done."]


def test_unrecognized_completed_item_cannot_prove_closed_authored_inventory():
    value = replace_sdk_payload(sdk(), lambda payload: payload["events"].insert(0,
        completed("future", "Unclassified output", type="futurePublicOutput")))
    assert not capture(value).closed and [record.text for record in capture(value).records] == ["Done."]


@pytest.mark.parametrize("bad", [[], {}, True, None])
def test_malformed_sdk_item_type_is_unavailable_without_crashing_or_losing_known_text(bad):
    value = replace_sdk_payload(sdk(), lambda payload: payload["events"].insert(0,
        completed("malformed", "Unclassified", type=bad)))
    result = capture(value)
    assert not result.closed and [record.text for record in result.records] == ["Done."]


@pytest.mark.parametrize("change", ["missing-artifact", "bad-base64", "bad-hash", "mutable-info", "missing-finish", "failed-finish",
    "duplicate-finish", "wrong-turn", "wrong-thread", "incomplete-item", "turn-unseen-message"])
def test_sdk_uncertain_inventory_is_never_false_silence(change):
    value = sdk()
    if change == "missing-artifact":
        value["sdk_artifact_base64"] = None
    elif change == "bad-base64":
        value["sdk_artifact_base64"] = "%%%"
    elif change == "bad-hash":
        value["sdk_artifact_sha256"] = "0" * 64
    elif change == "mutable-info":
        value["sdk_info"]["events"][0]["event"]["params"]["item"]["text"] = "Foreign info"
    else:
        def alter(payload):
            events = payload["events"]
            if change == "missing-finish":
                events.pop()
            elif change == "failed-finish":
                events[-1]["ok"] = False
            elif change == "duplicate-finish":
                events.append(copy.deepcopy(events[-1]))
            elif change == "wrong-turn":
                events[0]["event"]["params"]["turnId"] = "foreign"
            elif change == "wrong-thread":
                events[0]["event"]["params"]["threadId"] = "foreign"
            elif change == "incomplete-item":
                events.insert(0, {"kind": "event", "event": {"method": "item/started", "params": {"item": {
                    "type": "agentMessage", "id": "unfinished"}}}})
            else:
                events[1]["event"]["params"]["turn"]["items"] = [completed("unseen")["event"]["params"]["item"]]
        value = replace_sdk_payload(value, alter)
    assert not capture(value).closed


def test_identical_sdk_completed_item_dedup_and_conflict_keep_independent_output():
    value = replace_sdk_payload(sdk(), lambda payload: payload["events"].insert(1, completed()))
    assert capture(value).closed and len(capture(value).records) == 1
    value = replace_sdk_payload(value, lambda payload: payload["events"].insert(1, completed("independent", "Known other text")))
    value = replace_sdk_payload(value, lambda payload: payload["events"].insert(1, completed(text="Conflicting text")))
    result = capture(value)
    assert not result.closed and [record.text for record in result.records] == ["Known other text"]


@pytest.mark.parametrize("field,bad", [("schema_version", True), ("schema_version", 1.0), ("schema_version", "1"),
    ("complete", 1), ("sdk_declared", 0), ("trace_id", 1)])
def test_projection_strict_types_reject_false_complete_inventory(field, bad):
    assert not capture(projection(**{field: bad})).closed


def test_finished_wrapper_cannot_prove_sdk_empty_inventory():
    assert not capture(sdk([{"kind": "finished", "ok": True, "status": "completed"}])).closed
    terminal = sdk()["sdk_info"]["events"][1:]
    assert capture(sdk(terminal)).closed and not capture(sdk(terminal)).records
    result = capture(sdk([completed(), terminal[-1]]))
    assert not result.closed and [record.text for record in result.records] == ["Done."]


@pytest.mark.parametrize("field,bad", [("turn_id", None), ("thread_id", None), ("turn_id", True), ("thread_id", 1),
    ("turn_id", ""), ("thread_id", "")])
def test_sdk_terminal_anchor_strict_types(field, bad):
    value = replace_sdk_payload(sdk(), lambda payload: payload["events"][-1].update({field: bad}))
    assert not capture(value).closed and capture(value).records


@pytest.mark.parametrize("change", ["unfinished-delta", "foreign-turn", "foreign-thread", "error", "unknown-kind"])
def test_sdk_unfinished_or_foreign_stream_cannot_prove_silence(change):
    def alter(payload):
        extra = {"kind": "event", "event": {"method": "item/agentMessage/delta", "params": {
            "itemId": "output-1", "turnId": "turn-1", "threadId": "thread-1", "delta": "Not factual text"}}}
        if change == "unfinished-delta":
            extra["event"]["params"]["itemId"] = "missing-output"
        elif change == "foreign-turn":
            extra["event"]["params"]["turnId"] = "foreign"
        elif change == "foreign-thread":
            extra["event"]["params"]["threadId"] = "foreign"
        elif change == "error":
            extra = {"kind": "event", "event": {"method": "error", "params": {"error": {"message": "failed"}}}}
        else:
            extra = {"kind": "unknown-output", "text": "Not captured"}
        payload["events"].insert(0, extra)
    result = capture(replace_sdk_payload(sdk(), alter))
    assert not result.closed and [record.text for record in result.records] == ["Done."]


@pytest.mark.parametrize("change", ["gap", "reordered"])
def test_native_original_index_mismatch_preserves_unaffected_known_text(change):
    value = projection()
    value["native_nodes"].append({"node": 2, "parent": 1, "sampled": True, "role": "assistant", "content": "Other"})
    value["native_calls"].append({"node": 2, "finish_reason": "stop", "failed": False})
    if change == "gap":
        value["native_nodes"][2]["node"] = 4
        value["native_calls"][1]["node"] = 4
    else:
        value["native_nodes"][0], value["native_nodes"][2] = value["native_nodes"][2], value["native_nodes"][0]
    result = capture(value)
    assert not result.closed and [record.text for record in result.records] == ["Done."]


@pytest.mark.parametrize("change", ["malformed", "unknown-type", "foreign-turn", "foreign-thread"])
def test_started_authored_items_require_shape_and_coherent_stream(change):
    def alter(payload):
        params = {"item": {"id": "output-1", "type": "agentMessage"}, "turnId": "turn-1", "threadId": "thread-1"}
        if change == "malformed":
            params["item"] = []
        elif change == "unknown-type":
            params["item"]["type"] = "unknownPublicOutput"
        elif change == "foreign-turn":
            params["turnId"] = "foreign"
        else:
            params["threadId"] = "foreign"
        payload["events"].insert(0, {"kind": "event", "event": {"method": "item/started", "params": params}})
    result = capture(replace_sdk_payload(sdk(), alter))
    assert not result.closed and [record.text for record in result.records] == ["Done."]


def test_actual_worker_startup_diagnostic_kinds_are_not_additional_authored_channels():
    from test_batch01_manifests import recorded

    from automationbench_v1.calibration.collector import read_retained_artifacts

    path, _, _, trace, _ = recorded("simple.email_sf_contact_assistant_update")
    raw = read_retained_artifacts(path.parent, trace)["codex_sdk/events.json"]
    assert isinstance(raw, bytes)
    assert hashlib.sha256(raw).hexdigest() == "bb65881e6d7fec76cb38c370902ba67c774e379da4f353d469521d62a7aacd06"
    payload = json.loads(raw)
    assert {event["kind"] for event in payload["events"]} == {
        "capability_catalog", "authenticated", "initialized", "thread_started", "mcp_inventory", "turn_started", "event", "finished"}
    result = capture(sdk(payload["events"]))
    assert result.closed and len(result.records) == 1
    assert result.records[0].text == "Updated Rachel Nguyen’s Salesforce contact with assistant Kevin Torres (kevin.torres@ironclad.example.com)."


@pytest.mark.parametrize("bad", ["futureAuthoredMessage", [], {}, True, None])
def test_unknown_terminal_item_types_cannot_establish_empty_or_complete_inventory(bad):
    def alter(payload):
        payload["events"][1]["event"]["params"]["turn"]["items"] = [
            {"type": bad, "id": "unknown-output", "text": "Not recognized"}]
    result = capture(replace_sdk_payload(sdk(), alter))
    assert not result.closed and [record.text for record in result.records] == ["Done."]


@pytest.mark.parametrize("bad", [None, "", True, []])
def test_terminal_agent_message_requires_completed_nonempty_identity(bad):
    def alter(payload):
        payload["events"][1]["event"]["params"]["turn"]["items"] = [
            {"type": "agentMessage", "id": bad, "text": "Done."}]
    assert not capture(replace_sdk_payload(sdk(), alter)).closed


@pytest.mark.parametrize("method,params", [
    ("item/futureMessage/delta", {"delta": "Unknown authored output"}),
    ("rawResponse/completed", {"responseId": "r", "threadId": "thread-1", "turnId": "turn-1", "usage": [], "text": "Not metadata"}),
    ("thread/tokenUsage/updated", {"threadId": "thread-1", "turnId": "foreign", "tokenUsage": {}}),
    ("turn/started", {"threadId": "thread-1", "turn": {"id": "foreign", "status": "inProgress", "error": None}}),
])
def test_unknown_methods_and_malformed_or_foreign_metadata_keep_scope_open(method, params):
    value = replace_sdk_payload(sdk(), lambda payload: payload["events"].insert(0,
        {"kind": "event", "event": {"method": method, "params": params}}))
    result = capture(value)
    assert not result.closed and [record.text for record in result.records] == ["Done."]


def test_evidence_json_reload_and_copied_forgery_are_raw_source_bound():
    material = source(sdk())
    spec = AuthoredOutputSource()
    value = capture_authored_outputs(material, spec)
    restored = AuthoredOutputEvidence.model_validate_json(value.model_dump_json())
    validate_authored_outputs(restored, material, spec)
    for forged in (value.model_copy(update={"closed": 1}), value.model_copy(update={"records": (
            value.records[0].model_copy(update={"text": "Invented"}),)})):
        with pytest.raises(ValueError):
            validate_authored_outputs(forged, material, spec)
    material["task_evidence"]["authored_outputs"]["complete"] = False
    with pytest.raises(ValueError):
        validate_authored_outputs(value, material, spec)
