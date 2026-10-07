"""Real handlers in manufactured native envelopes, plus immutable actual replay."""

import copy
import hashlib
import json
from typing import Any, cast

import pytest
from test_batch01_manifests import recorded
from test_manifest_zendesk_effects import initial
from test_notification_evidence import zapier
from test_slack_external_outputs import captured, rewrite_last, source
from verifiers.v1.assessment_source import capture_trace_source

from automationbench.tools.zapier.gmail.message import gmail_send_email
from automationbench.tools.zapier.zendesk.tickets import zendesk_find_ticket, zendesk_update_ticket
from automationbench_v1.calibration.collector import read_retained_artifacts
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.external_outputs import (
    ExternalOutputSource,
    _classify,
    validate_external_outputs,
)
from automationbench_v1.contracts.invocation_inventory import capture_invocation_inventory
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState


def send(**changes):
    args = {"to": "person@example.com", "subject": "Subject", "body": "Body", **changes}
    return zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))


def update(**changes):
    args = {"ticket_id": "T-1", "status": "solved", **changes}
    return zapier("zendesk_update_ticket", args, lambda world: zendesk_update_ticket(world, **args))


def find(**args):
    return zapier("zendesk_find_ticket", args, lambda world: zendesk_find_ticket(world, **args))


def fresh(calls):
    return source(calls, world=initial())


@pytest.mark.parametrize("body_type", [None, "plain", "html", "other-installed-plain"])
def test_send_exact_body_transforms_and_all_authored_headers(body_type):
    raw = fresh(
        [
            send(
                body_type=body_type,
                signature="Skipped Bob",
                from_name="Narrative name",
                from_="Sender prose",
                reply_to="Reply prose",
                to="Skipped Alice <a@example.com>, b@example.com",
                cc="CC prose",
                bcc="BCC prose",
                label_ids="Narrative label",
            )
        ]
    )
    evidence = captured(raw)
    assert evidence.invocation_coverage[0].disposition == "authored_fields", evidence.reason
    fields = {f.field: f.text for f in evidence.text_records}
    assert fields == {
        "subject": "Subject",
        "body_html" if body_type == "html" else "body_plain": "Body\n\nSkipped Bob",
        "from_name": "Narrative name",
        "from_": "Sender prose",
        "reply_to": "Reply prose",
        "to.0": "Skipped Alice <a@example.com>",
        "to.1": "b@example.com",
        "cc.0": "CC prose",
        "bcc.0": "BCC prose",
        "label_ids.1": "Narrative label",
    }
    assert all(f.surface == "message_field" for f in evidence.text_records)
    assert not evidence.closed  # Manufactured envelopes do not invent original call inventory.
    validate_external_outputs(evidence, raw, ExternalOutputSource())


def test_empty_body_and_ignored_empty_signature_remain_exact():
    evidence = captured(fresh([send(body="", subject="", signature="", from_name="")]))
    fields = {f.field: f.text for f in evidence.text_records}
    assert fields == {
        "subject": "",
        "body_plain": "",
        "to.0": "person@example.com",
        "from_name": "",
    }


def test_attachment_scope_open_but_known_body_preserved():
    evidence = captured(fresh([send(file="attachment.txt")]))
    assert evidence.invocation_coverage[0].disposition == "unavailable"
    assert any(f.field == "body_plain" and f.text == "Body" for f in evidence.text_records)


@pytest.mark.parametrize(
    "field", ["subject", "body_plain", "from_name", "snippet", "date", "other_service"]
)
def test_gmail_forged_fields_never_close_and_preserve_only_independent_fields(field):
    raw = fresh([send(from_name="Original")])

    def change(world):
        if field == "other_service":
            world["meta"]["current_time"] = "2030-01-01T00:00:00Z"
        else:
            world["gmail"]["messages"][-1][field] = True if field == "date" else "Forged"

    evidence = captured(rewrite_last(raw, after_change=change))
    assert evidence.invocation_coverage[0].disposition == "unavailable"
    assert not any(f.field == field for f in evidence.text_records)
    if field not in {"subject", "body_plain"}:
        assert any(f.field == "body_plain" for f in evidence.text_records)


def test_wrong_gmail_response_identity_cannot_establish_authored_fields():
    raw = rewrite_last(fresh([send()]), result_change=lambda r: r["message"].update(id="forged"))
    assert not captured(raw).text_records


@pytest.mark.parametrize(
    "args",
    [
        {"ticket_id": "T-1"},
        {"query": "original"},
        {"ticket_id": "missing"},
        {},
        {"ticket_id": "T-1", "query": "ignored"},
    ],
)
def test_zendesk_find_exact_known_read_routes(args):
    evidence = captured(fresh([find(**args)]))
    assert evidence.invocation_coverage[0].disposition == "no_authored_fields"
    assert not evidence.text_records


@pytest.mark.parametrize("comment", [None, "", " ", "My work summary: I skipped Bob."])
@pytest.mark.parametrize("public", [True, False])
def test_zendesk_comment_truthiness_and_status_relations(comment, public):
    evidence = captured(
        fresh(
            [
                update(comment=comment, comment_public=public),
                update(comment=comment, comment_public=public),
            ]
        )
    )
    assert all(
        c.disposition == ("authored_fields" if comment else "no_authored_fields")
        for c in evidence.invocation_coverage
    )
    assert len(evidence.text_records) == (2 if comment else 0)
    assert len({f.output_id for f in evidence.text_records}) == len(evidence.text_records)
    assert len({f.record_id for f in evidence.text_records}) == len(evidence.text_records)
    statuses = [r for r in evidence.action_relations if r.field == "status"]
    assert [r.changed for r in statuses] == [True, False]
    assert all(
        json.loads(r.value_json) is public for r in evidence.action_relations if r.field == "public"
    )


@pytest.mark.parametrize("field", ["body", "public", "id", "author_id", "other_service", "subject"])
def test_zendesk_comment_and_full_footprint_forgery(field):
    raw = fresh([update(comment="Known comment")])

    def change(world):
        ticket = world["zendesk"]["tickets"][0]
        if field == "other_service":
            world["meta"]["current_time"] = "2030-01-01T00:00:00Z"
        elif field == "subject":
            ticket["subject"] = "Unexpected narrative"
        else:
            ticket["comments"][-1][field] = {
                "body": "Forged",
                "public": False,
                "id": "",
                "author_id": "invented",
            }[field]

    evidence = captured(rewrite_last(raw, after_change=change))
    assert evidence.invocation_coverage[0].disposition == "unavailable"
    assert bool(evidence.text_records) is (field == "other_service")


def test_missing_ticket_known_atomic_failure_and_unsupported_extra_field():
    evidence = captured(fresh([update(ticket_id="missing", comment="Never posted")]))
    assert evidence.invocation_coverage[0].disposition == "no_authored_fields"
    assert not evidence.text_records
    evidence = captured(fresh([update(subject="Unreviewed subject", comment="Comment")]))
    assert evidence.invocation_coverage[0].disposition == "unavailable"


@pytest.mark.parametrize("missing", [0, 1])
def test_missing_ack_and_independent_later_gap(missing):
    raw = source([update(comment="Comment"), send()], world=initial(), missing_ack=missing)
    evidence = captured(raw)
    assert not evidence.closed
    assert {f.invocation_id for f in evidence.text_records} == {f"execution-{1 - missing}"}


def test_repeated_sends_and_later_unknown_mutation_keep_independent_facts():
    def remove(world):
        world.gmail.messages.clear()
        return json.dumps({"success": True})

    evidence = captured(fresh([send(), send(), zapier("unreviewed_delete", {}, remove)]))
    assert len({f.record_id for f in evidence.text_records}) == 2
    assert evidence.invocation_coverage[-1].disposition == "unavailable"


def test_raw_source_forgery_rejected():
    raw = fresh([update(comment="Known"), send()])
    evidence = captured(raw)
    forged = evidence.model_copy(
        update={"text_records": (evidence.text_records[0].model_copy(update={"text": "Forged"}),)}
    )
    with pytest.raises(ValueError, match="raw_source_or_projection_mismatch"):
        validate_external_outputs(forged, raw, ExternalOutputSource())


@pytest.mark.parametrize(
    "args",
    [
        {"status": "My work summary: skipped Bob"},
        {"comment_public": 1},
        {"comment_public": "false"},
    ],
)
def test_unconstrained_or_coerced_status_public_values_never_gain_read_only_exemption(args):
    if "status" in args:
        # Direct classifier admission seam: the normal native WorldState boundary
        # rejects invalid status before building a source. Do not weaken it.
        entry = capture_invocation_inventory(fresh([update(comment="Comment")])).entries[0]
        bad = entry.model_copy(
            update={"operation_arguments_json": canonical_json({"ticket_id": "T-1", **args})}
        )
        with pytest.raises(ValueError, match="status_unsupported"):
            _classify(bad)
        return
    evidence = captured(fresh([update(comment="Comment", **args)]))
    assert evidence.invocation_coverage[0].disposition == "unavailable"
    assert not evidence.text_records


def test_duplicate_ticket_id_and_existing_comment_id_are_ambiguous():
    world = initial()
    world["zendesk"]["tickets"].append(copy.deepcopy(world["zendesk"]["tickets"][0]))
    evidence = captured(source([update(comment="Comment")], world=world))
    assert evidence.invocation_coverage[0].disposition == "unavailable"
    assert not evidence.text_records
    raw = fresh([update(comment="First"), update(comment="Second")])

    def duplicate(after):
        comments = after["zendesk"]["tickets"][0]["comments"]
        comments[-1]["id"] = comments[0]["id"]

    evidence = captured(rewrite_last(raw, after_change=duplicate))
    assert [f.text for f in evidence.text_records] == ["First"]
    assert evidence.invocation_coverage[-1].disposition == "unavailable"


def test_inconsistent_find_result_and_known_failure_world_change_stay_open():
    raw = fresh([find(ticket_id="T-1")])
    evidence = captured(rewrite_last(raw, result_change=lambda result: result.update(count=0)))
    assert evidence.invocation_coverage[0].disposition == "unavailable"
    raw = fresh([update(ticket_id="missing", comment="Not posted")])
    evidence = captured(
        rewrite_last(
            raw, after_change=lambda w: w["zendesk"]["tickets"][0].update(subject="Unexpected")
        )
    )
    assert evidence.invocation_coverage[0].disposition == "unavailable"


def test_new_gmail_identity_cannot_reuse_previous_message():
    raw = fresh([send(), send()])
    evidence = captured(
        rewrite_last(
            raw,
            after_change=lambda w: w["gmail"]["messages"][-1].update(
                id=w["gmail"]["messages"][0]["id"]
            ),
        )
    )
    assert {f.invocation_id for f in evidence.text_records} == {"execution-0"}
    assert evidence.invocation_coverage[-1].disposition == "unavailable"


def test_actual_zendesk_five_calls_native_reload_exact_source_bytes_and_scalars():
    path, raw, episode, trace, data = recorded("simple.zendesk_resolve_email")
    assert (
        hashlib.sha256(raw).hexdigest()
        == "e04a068ad087b52ff28c8294f99cb539cf7f282c0914a795f654a115bd4439c9"
    )
    rewards = copy.deepcopy(trace.rewards)
    events = canonical_json([e.model_dump(mode="json") for e in trace.tool_execution_events])
    artifacts = read_retained_artifacts(path.parent, trace)
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state,
        artifacts=artifacts,
    )
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    sealed = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    evidence = captured(json.loads(sealed.source_json))
    assert evidence.closed, evidence.reason
    assert len(evidence.invocation_coverage) == 5
    by_call = {}
    for fact in evidence.text_records:
        by_call.setdefault(fact.invocation_id, {})[fact.field] = fact.text
    assert set(by_call) == {"a19b0f39ad6f4d81ae756b8b93d2daa0", "bd76192af43043899f47c0df4919f957"}
    assert by_call["a19b0f39ad6f4d81ae756b8b93d2daa0"] == {
        "body": "Your password reset issue has been resolved. Please try resetting your password again, and let us know if you need any further assistance."
    }
    assert (
        by_call["bd76192af43043899f47c0df4919f957"]["subject"]
        == "Your password reset issue has been resolved"
    )
    assert by_call["bd76192af43043899f47c0df4919f957"]["to.0"] == "elena.voss@retail.example.com"
    assert set(by_call["bd76192af43043899f47c0df4919f957"]) == {"subject", "body_plain", "to.0"}
    restored = cast(Any, type(episode).model_validate_json(episode.model_dump_json()).traces[0])
    restored.state = AutomationBenchState(
        world=trace.state.world, initial_state=data.initial_state, artifacts=artifacts
    )
    again = captured(
        json.loads(
            capture_trace_source(
                restored, task_evidence=task.assessment_source(restored)
            ).source_json
        )
    )
    assert again.closed and again.text_records == evidence.text_records
    assert again.action_relations == evidence.action_relations
    assert trace.rewards == rewards and path.read_bytes() == raw
    assert (
        canonical_json([e.model_dump(mode="json") for e in trace.tool_execution_events]) == events
    )
