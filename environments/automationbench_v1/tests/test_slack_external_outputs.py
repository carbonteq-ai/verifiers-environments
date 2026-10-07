"""Slack authored text, genuine handlers and a separate immutable Luna replay.

Small cases wrap real handler captures in validated manufactured native
envelopes. They establish local facts, not a complete generated-call inventory.
"""

import copy
import hashlib
import json
from typing import Any, cast

import pytest
from test_batch01_manifests import recorded
from test_manifest_guard_assessments import native_fixture
from test_manifest_slack_effects import dm, initial
from test_notification_evidence import run_operations, zapier
from verifiers.v1.assessment_source import capture_trace_source

from automationbench.tools.zapier.slack.messaging import slack_delete_message
from automationbench.tools.zapier.slack.users import slack_find_user_by_name
from automationbench_v1.calibration.collector import read_retained_artifacts
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.external_outputs import (
    ExternalOutputSource,
    capture_external_outputs,
    validate_external_outputs,
)
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState, _registry


def source(calls=None, *, world=None, missing_ack=None):
    material = run_operations(world or initial(), calls if calls is not None else [dm()])
    task, _, trace = native_fixture(material, missing_ack=missing_ack)
    sealed = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    return json.loads(sealed.source_json)


def captured(raw):
    return capture_external_outputs(raw, ExternalOutputSource())


def lookup(**kwargs):
    return zapier(
        "slack_find_user_by_name", kwargs, lambda world: slack_find_user_by_name(world, **kwargs)
    )


def rewrite_last(raw, *, result_change=None, after_change=None):
    """Coherent counterfactual capture; source files are never changed."""
    raw = copy.deepcopy(raw)
    event = next(
        e
        for e in reversed(raw["tool_execution_events"])
        if e["source"] == "tool_server" and e["phase"] == "returned"
    )
    receipt = json.loads(event["receipt_json"])
    payload = json.loads(receipt["evidence_json"][0])
    action = payload["action"]
    if result_change:
        result = json.loads(json.loads(action["result_json"]))
        result_change(result)
        action["result_json"] = receipt["result_json"] = canonical_json(json.dumps(result))
    if after_change:
        after = json.loads(payload["snapshots"][action["after_digest"]])
        after_change(after)
        encoded = canonical_json(after)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        payload["snapshots"][digest] = encoded
        action["after_digest"] = digest
        raw["task_evidence"]["final"] = after
        next(w for w in raw["state_write_receipts"] if w["write_id"] == receipt["invocation_id"])[
            "body_digest"
        ] = digest
    receipt["evidence_json"][0] = canonical_json(payload)
    event["receipt_json"] = canonical_json(receipt)
    return raw


@pytest.mark.parametrize(
    "bot,username",
    [
        (True, None),
        (True, ""),
        (True, "My work summary: skipped Bob"),
        (False, "Ignored non-bot name"),
    ],
)
def test_real_dm_preserves_every_written_authored_string_and_routing(bot, username):
    raw = source([dm(text="", as_bot=bot, username=username)])
    evidence = captured(raw)
    assert not evidence.closed  # No fake generated-call inventory.
    assert evidence.invocation_coverage[0].disposition == "authored_fields"
    expected = {"text": ""}
    if bot and username:
        expected["bot_name"] = username
    assert {fact.field: fact.text for fact in evidence.text_records} == expected
    assert all(fact.surface == "message_field" for fact in evidence.text_records)
    relations = {r.field: json.loads(r.value_json) for r in evidence.action_relations}
    assert relations["recipient_user_id"] == "Usarah"
    assert relations["sender_user_id"] == ("USLACKBOT" if bot else "UAUTHUSER")
    assert all(r.changed for r in evidence.action_relations)  # New messages, including empty ones.
    for fact in evidence.text_records:
        channel, timestamp = json.loads(fact.record_id)
        assert channel == relations["channel_id"] and timestamp
    validate_external_outputs(evidence, raw, ExternalOutputSource())


@pytest.mark.parametrize(
    "args",
    [
        {"full_name": "Sarah Jones"},
        {"name": "Sarah"},
        {"query": "SARAH"},
        {"full_name": "Sarah Jones", "name": "Ignored alias"},
        {"full_name": "Nobody"},
        {},
    ],
)
def test_audited_lookup_aliases_and_not_found_are_read_only(args):
    evidence = captured(source([lookup(**args)]))
    assert evidence.invocation_coverage[0].disposition == "no_authored_fields"
    assert not evidence.text_records and not evidence.action_relations


def test_failed_recipient_has_no_external_authored_message():
    evidence = captured(source([dm(user="unknown")]))
    assert evidence.invocation_coverage[0].disposition == "no_authored_fields"
    assert evidence.invocation_coverage[0].reason == "external_output_audited_slack_dm_not_found"
    assert not evidence.text_records


def test_repeated_same_text_is_two_distinct_message_occurrences():
    evidence = captured(source([dm(), dm()]))
    assert len(evidence.text_records) == 2
    assert len({f.record_id for f in evidence.text_records}) == 2
    assert len({f.output_id for f in evidence.text_records}) == 2
    assert {f.invocation_id for f in evidence.text_records} == {"execution-0", "execution-1"}
    assert all(r.changed for r in evidence.action_relations)


@pytest.mark.parametrize("missing", [0, 1])
def test_missing_ack_never_invents_text_and_later_gap_preserves_first(missing):
    evidence = captured(source([dm(), dm()], missing_ack=missing))
    assert not evidence.closed
    assert {f.invocation_id for f in evidence.text_records} == {f"execution-{1 - missing}"}


def test_later_unsupported_delete_does_not_erase_authored_message():
    def remove(world):
        message = world.slack.messages[-1]
        return slack_delete_message(world, channel=message.channel_id, ts=message.ts)

    # The delete's dynamic params aren't used as a qualified supported write;
    # its real mutation is retained, and scope must remain unsupported.
    evidence = captured(source([dm(), zapier("slack_delete_message", {}, remove)]))
    assert not evidence.closed and len(evidence.text_records) == 1
    assert evidence.invocation_coverage[-1].disposition == "unavailable"


@pytest.mark.parametrize(
    "change,known_text",
    [
        ("returned_text", False),
        ("persisted_text", False),
        ("returned_bot_name", True),
        ("persisted_bot_name", True),
        ("extra_attachment", True),
        ("other_service", True),
    ],
)
def test_result_state_disagreement_preserves_only_independently_proven_fields(change, known_text):
    raw = source([dm(username="Authored display name")])
    if change.startswith("returned"):
        field = "text" if change == "returned_text" else "username"
        raw = rewrite_last(
            raw, result_change=lambda result: result["message"].update({field: "Forged"})
        )
    else:

        def mutate(after):
            message = after["slack"]["messages"][-1]
            if change == "persisted_text":
                message["text"] = "Forged"
            elif change == "persisted_bot_name":
                message["bot_name"] = "Forged"
            elif change == "extra_attachment":
                message["attachments"] = [{"text": "Unaccounted narrative"}]
            else:
                after["meta"]["current_time"] = "2030-01-01T00:00:00Z"

        raw = rewrite_last(raw, after_change=mutate)
    evidence = captured(raw)
    assert evidence.invocation_coverage[0].disposition == "unavailable"
    assert any(f.field == "text" for f in evidence.text_records) is known_text
    if "bot_name" in change:
        assert not any(f.field == "bot_name" for f in evidence.text_records)


def test_wrong_lookup_response_or_world_change_cannot_close():
    raw = source([lookup(name="Sarah")])
    for bad in [
        rewrite_last(raw, result_change=lambda r: r["user"].update(id="wrong")),
        rewrite_last(raw, after_change=lambda w: w["slack"]["users"][0].update(name="changed")),
    ]:
        assert captured(bad).invocation_coverage[0].disposition == "unavailable"


@pytest.mark.parametrize("call", [lookup(name="Sarah Jones"), dm(user="Sarah Jones")])
def test_ambiguous_recipient_identity_never_establishes_known_destination(call):
    world = initial()
    duplicate = {**world["slack"]["users"][0], "id": "Uother"}
    world["slack"]["users"].append(duplicate)
    evidence = captured(source([call], world=world))
    assert evidence.invocation_coverage[0].disposition == "unavailable"
    assert not evidence.text_records


@pytest.mark.parametrize(
    "field,value", [("channel", "foreign"), ("user", "foreign"), ("ts", "foreign")]
)
def test_returned_message_native_identity_must_match_persisted_send(field, value):
    raw = rewrite_last(source(), result_change=lambda r: r["message"].update({field: value}))
    evidence = captured(raw)
    assert not evidence.text_records
    assert evidence.invocation_coverage[0].disposition == "unavailable"


def test_missing_return_cannot_be_reconstructed_from_persisted_message():
    raw = source()
    event = next(
        e
        for e in raw["tool_execution_events"]
        if e["source"] == "tool_server" and e["phase"] == "returned"
    )
    receipt = json.loads(event["receipt_json"])
    payload = json.loads(receipt["evidence_json"][0])
    receipt["result_json"] = payload["action"]["result_json"] = None
    receipt["evidence_json"][0] = canonical_json(payload)
    event["receipt_json"] = canonical_json(receipt)
    assert not captured(raw).text_records


def test_handler_replacement_and_projected_fact_forgery_reject(monkeypatch):
    raw = source()
    evidence = captured(raw)
    with pytest.raises(ValueError, match="raw_source_or_projection"):
        validate_external_outputs(
            evidence.model_copy(update={"text_records": ()}), raw, ExternalOutputSource()
        )
    monkeypatch.setitem(
        _registry()._tool_map, "slack_send_direct_message", lambda **kwargs: "other"
    )
    assert not captured(raw).text_records


def test_actual_sha_bound_dm_archive_closes_all_three_invocations_and_reloads():
    path, raw, episode, trace, data = recorded("simple.slack_dm_meeting_reminder")
    assert (
        hashlib.sha256(raw).hexdigest()
        == "19c8a4f60d49d991c3a5dd61dfef15ea58384ece563e25a53f55d0dc4121903d"
    )
    original_scores = copy.deepcopy(trace.rewards)
    original_events = canonical_json(
        [e.model_dump(mode="json") for e in trace.tool_execution_events]
    )
    artifacts = read_retained_artifacts(path.parent, trace)
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state,
        artifacts=artifacts,
    )
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    sealed = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    material = json.loads(sealed.source_json)
    evidence = captured(material)
    assert evidence.closed, evidence.reason
    assert len(evidence.invocation_coverage) == 3 and len(evidence.text_records) == 1
    fact = evidence.text_records[0]
    assert fact.invocation_id == "9c9ab46a05354a69a796a144b9789adf"
    assert (
        fact.text
        == "Hi Sarah, a reminder that your client meeting with Globex Financial is tomorrow at 2 PM. Please bring the updated proposal deck and the Q4 metrics report."
    )
    restored = cast(Any, type(episode).model_validate_json(episode.model_dump_json()).traces[0])
    restored.state = AutomationBenchState(
        world=trace.state.world, initial_state=data.initial_state, artifacts=artifacts
    )
    replay = capture_trace_source(restored, task_evidence=task.assessment_source(restored))
    again = captured(json.loads(replay.source_json))
    assert again.closed and again.text_records == evidence.text_records
    assert again.action_relations == evidence.action_relations
    assert trace.rewards == original_scores
    assert (
        canonical_json([e.model_dump(mode="json") for e in trace.tool_execution_events])
        == original_events
    )
    assert path.read_bytes() == raw
