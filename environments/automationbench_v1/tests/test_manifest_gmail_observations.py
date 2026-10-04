"""Real read handlers retain returned fields without backfilling hidden bodies."""

import copy
import json
from dataclasses import replace
from typing import Any, cast

import pytest
from test_manifest_guard_assessments import native_fixture
from test_notification_evidence import run_operations, zapier

from automationbench.tools.api.fetch import api_fetch
from automationbench.tools.zapier.gmail.message import (
    gmail_find_email,
    gmail_get_email_by_id,
    gmail_list_emails,
)
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.gmail_observations import (
    GmailObservationSource,
    capture_gmail_observations,
    validate_gmail_observations,
)
from automationbench_v1.contracts.predicates import evaluate_predicate, parse_predicate


def initial():
    return {"gmail": {"messages": [{"id": "message-1", "thread_id": "thread-1", "from_": "person@example.com",
        "subject": "Introduction", "body_plain": "New assistant is Kevin", "body_html": "<p>Kevin</p>"}]}}


def read(name="get", *, format="full", identity="message-1", url=None):
    args: dict[str, Any]
    if name == "get":
        args = {"message_id": identity, "format": format}
        return zapier("gmail_get_email_by_id", args, lambda world: gmail_get_email_by_id(world, **args))
    if name in {"find", "list"}:
        args = {"query": "Kevin", "format": format}
        function = gmail_find_email if name == "find" else gmail_list_emails
        return zapier("gmail_find_email" if name == "find" else "gmail_list_emails", args,
                      lambda world: function(world, **args))
    args = {"url": url or ("/gmail/v1/users/me/messages" + ("/" + identity if name == "api-get" else "")),
            "method": "GET", "params": {"format": format}}
    return "api_fetch", args, lambda world: api_fetch(world, **args)


def material(calls, world=None):
    source = run_operations(world or initial(), calls)
    # Real handlers, manufactured VALIDATED native lifecycle envelopes. This
    # interface fixture does not claim a live server/network run. The shared
    # helper constructs ToolServerReceipt and StateWriteReceipt schema objects.
    _, _, trace = native_fixture(source)
    source["tool_execution_events"] = [{"source": "tool_server", "receipt_json": event.receipt_json}
        for event in trace.tool_execution_events]
    source["state_write_receipts"] = [receipt.model_dump(mode="json") for receipt in trace.state_write_receipts]
    return source


def evidence(source):
    return capture_gmail_observations(source, GmailObservationSource())


def positive(value):
    return [fact for fact in value.effects if fact.status == "qualified"]


def mutate_return(source, change, *, local=True, native=True):
    source = copy.deepcopy(source)
    event = next(event for event in source["tool_execution_events"] if json.loads(event["receipt_json"])["phase"] == "returned")
    receipt = json.loads(event["receipt_json"])
    capture = json.loads(receipt["evidence_json"][0])
    result = json.loads(json.loads(capture["action"]["result_json"]))
    change(result)
    encoded = canonical_json(json.dumps(result))
    if local:
        capture["action"]["result_json"] = encoded
    if native:
        receipt["result_json"] = encoded
    receipt["evidence_json"][0] = canonical_json(capture)
    event["receipt_json"] = canonical_json(receipt)
    return source


@pytest.mark.parametrize("name", ["find", "list", "get", "api-get"])
def test_full_returned_native_paths_prove_original_body_sender_and_identity(name):
    value = evidence(material([read(name)]))
    assert value.complete and len(positive(value)) == 1
    params = json.loads(cast(str, positive(value)[0].params_json))
    assert params["message_id"] == params["native_record_id"] == "message-1"
    assert params["from_"] == "person@example.com" and params["body_plain"] == "New assistant is Kevin"
    assert set(params["returned_fields"]) == set(params) - {"native_record_id", "returned_fields"}


@pytest.mark.parametrize("name,format,body", [("find", "minimal", False), ("get", "metadata", False),
    ("list", "metadata", False), ("api-list", "full", False), ("api-get", "minimal", False),
    ("api-get", "metadata", True)])
def test_observed_fields_not_format_labels_determine_body_availability(name, format, body):
    value = evidence(material([read(name, format=format)]))
    assert len(positive(value)) == 1
    params = json.loads(cast(str, positive(value)[0].params_json))
    assert ("body_plain" in params) is body
    predicate = parse_predicate({"op": "eq", "left": {"kind": "field", "path": ["effect", "body_plain"]},
                                 "right": {"kind": "literal", "value": "New assistant is Kevin"}})
    assert evaluate_predicate(predicate, {"effect": params}).value is (True if body else None)


def test_real_full_url_and_repeated_reads_have_distinct_occurrences():
    value = evidence(material([read("api-get", url="https://gmail.googleapis.com/gmail/v1/users/me/messages/message-1"), read()]))
    assert value.complete and len(positive(value)) == 2
    assert len({fact.effect_id for fact in positive(value)}) == 2


@pytest.mark.parametrize("change", ["body", "sender", "id-alias", "count", "duplicate"])
def test_coherently_changed_returns_cannot_invent_before_world_message_facts(change):
    source = material([read("find")])
    def alter(result):
        message = result["messages"][0]
        if change == "body":
            message["body_plain"] = "Invented"
        elif change == "sender":
            message["from"] = "other@example.com"
        elif change == "id-alias":
            message["message_id"] = "other"
        elif change == "count":
            result["result_count"] = True
        else:
            result["messages"].append(copy.deepcopy(message))
            result["result_count"] = result["total_count"] = 2
    value = evidence(mutate_return(source, alter))
    assert not positive(value) and not value.complete


def test_local_capture_cannot_replace_actual_native_return_and_missing_ack_abstains():
    source = material([read()])
    changed = mutate_return(source, lambda result: result["message"].update(body_plain="Invented"), native=False)
    assert not positive(evidence(changed))
    source["state_write_receipts"] = []
    assert not positive(evidence(source))


@pytest.mark.parametrize("change", ["missing-native-return", "local-raised", "local-error", "native-state-error", "native-call"])
def test_missing_or_failed_native_local_returns_cannot_claim_retrieval(change):
    source = material([read()])
    event = next(event for event in source["tool_execution_events"] if json.loads(event["receipt_json"])["phase"] == "returned")
    receipt = json.loads(event["receipt_json"])
    capture = json.loads(receipt["evidence_json"][0])
    if change == "missing-native-return":
        del receipt["result_json"]
    elif change == "local-raised":
        capture["action"]["status"] = "raised"
    elif change == "local-error":
        capture["action"]["error_json"] = canonical_json({"type": "RuntimeError"})
    elif change == "native-state-error":
        receipt["state_error_json"] = canonical_json({"type": "RuntimeError"})
    else:
        receipt["tool_name"] = "different_native_call"
    receipt["evidence_json"][0] = canonical_json(capture)
    event["receipt_json"] = canonical_json(receipt)
    assert not positive(evidence(source))


def test_duplicate_before_identity_wrong_requested_id_and_wrong_router_are_unavailable():
    world = initial()
    world["gmail"]["messages"].append(copy.deepcopy(world["gmail"]["messages"][0]))
    assert not positive(evidence(material([read()], world)))
    source = material([read()])
    changed = mutate_return(source, lambda result: result["message"].update(id="wrong", message_id="wrong"))
    assert not positive(evidence(changed))
    assert not positive(evidence(material([read("api-get", url="https://unrelated.example.com/gmail/v1/users/me/messages/message-1")])))


def test_mutating_read_cannot_claim_body_observation_and_later_unknown_preserves_known_read():
    args = {"message_id": "message-1"}
    def mutated(world):
        result = gmail_get_email_by_id(world, **args)
        world.gmail.messages[0].body_plain = "Changed"
        return result
    call = zapier("gmail_get_email_by_id", args, mutated)
    assert not positive(evidence(material([call])))
    value = evidence(material([read(), ("custom_read", {}, lambda world: "{}")]))
    assert len(positive(value)) == 1 and not value.complete


def test_later_message_change_does_not_rewrite_prior_returned_fields():
    def changed(world):
        world.gmail.messages[0].body_plain = "Later changed"
        return "{}"
    value = evidence(material([read(), ("custom_mutation", {}, changed), read()]))
    assert [json.loads(cast(str, fact.params_json))["body_plain"] for fact in positive(value)] == [
        "New assistant is Kevin", "Later changed"]
    assert not value.complete


def test_raw_source_recapture_rejects_forged_receipt_metadata_or_params():
    source = material([read()])
    value = evidence(source)
    validate_gmail_observations(value, source, GmailObservationSource())
    for forged in (replace(value, complete=1), replace(value, effects=(replace(value.effects[0],
            params_json=canonical_json({"message_id": "wrong"})),))):
        with pytest.raises(ValueError, match="raw_source_or_projection"):
            validate_gmail_observations(forged, source, GmailObservationSource())
