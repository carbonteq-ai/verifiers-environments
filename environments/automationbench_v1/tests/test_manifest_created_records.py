"""Generic fresh-record retained outcomes (``final.created_records@1``).

Diagnosis that motivated it (sales.create_important_draft): the Gmail draft
create was already a qualified, complete ``service.record_writes@1`` fact; the
check abstained because a Gmail ``drafts`` record is only ``{id, message_id}``
and the content lives in the referenced ``messages`` record (a projection
gap). Action-side evidence is expressible today with the ``messages`` create
fact (and a ``drafts`` join on ``message_id``). The retained outcome needed a
generic adapter: ``objects.created_and_retained@1`` only knew HubSpot/Jira.
"""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture
from test_notification_evidence import run_operations

from automationbench.tools.api.impl.gmail import gmail_drafts_send
from automationbench.tools.zapier.gmail.draft import gmail_create_draft
from automationbench.tools.zapier.gmail.message import gmail_send_email
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.created_records import (
    CreatedRecordSource,
    capture_created_records,
)
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_guard_assessments import digest
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

PROMPT = "Draft an email to board@example.com with subject 'Q4 2025 Results Summary'."
DRAFTS = {
    "adapter": "final.created_records@1",
    "service": "gmail",
    "collection": "drafts",
    "references": {"message": {"field": "message_id", "collection": "messages"}},
}


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def literal(value):
    return {"kind": "literal", "value": value}


RETAINED = {
    "op": "all",
    "args": [
        {
            "op": "in",
            "left": field("request", "recipient"),
            "right": field("retained", "message", "to", domain="sequence"),
        },
        {
            "op": "eq",
            "left": field("retained", "message", "subject"),
            "right": field("request", "subject"),
        },
        {
            "op": "in",
            "left": literal("DRAFT"),
            "right": field("retained", "message", "label_ids", domain="sequence"),
        },
    ],
}


def raw_contract(prompt_path=("task_evidence", "prompt"), prompt=PROMPT):
    authority = [list(prompt_path)]
    return {
        "schema_version": 1,
        "manifest_id": "created-records",
        "revision": "1",
        "public_request": prompt,
        "bindings": [{"path": list(prompt_path), "canonical_sha256": digest(prompt)}],
        "sources": {
            "request": {
                "adapter": "public.request@1",
                "member_key": "board",
                "fields": {
                    "recipient": {"value": "board@example.com", "authority_paths": authority},
                    "subject": {"value": "Q4 2025 Results Summary", "authority_paths": authority},
                },
            },
            "drafts": DRAFTS,
        },
        "checks": [
            {
                "check_id": "board-draft-retained",
                "signal_id": "sales.board_draft_retained",
                "role": "goal",
                "operator": "objects.created_and_retained@1",
                "population": "request",
                "source": "drafts",
                "required_when": {
                    "op": "eq",
                    "left": field("request", "subject"),
                    "right": literal("Q4 2025 Results Summary"),
                },
                "retained_when": RETAINED,
            }
        ],
    }


def draft(to="board@example.com", subject="Q4 2025 Results Summary"):
    args = {"to": to, "subject": subject, "body": "Revenue YoY: 37%"}
    return (
        "execute_tool",
        {"tool_name": "gmail_create_draft", "arguments": canonical_json(args)},
        lambda world: gmail_create_draft(world, **args),
    )


def send_latest_draft():
    return (
        "execute_tool",
        {"tool_name": "gmail_drafts_send", "arguments": canonical_json({})},
        lambda world: gmail_drafts_send(world, id=world.gmail.drafts[-1].id),
    )


def send(to="board@example.com", subject="Q4 2025 Results Summary"):
    args = {"to": to, "subject": subject, "body": "Revenue YoY: 37%"}
    return (
        "execute_tool",
        {"tool_name": "gmail_send_email", "arguments": canonical_json(args)},
        lambda world: gmail_send_email(world, **args),
    )


def initial(drafts=()):
    return {
        "gmail": {
            "messages": [
                {
                    "id": f"m{index}",
                    "to": ["board@example.com"],
                    "subject": "Q4 2025 Results Summary",
                    "label_ids": ["DRAFT"],
                }
                for index, _ in enumerate(drafts)
            ],
            "drafts": [
                {"id": identity, "message_id": f"m{index}"} for index, identity in enumerate(drafts)
            ],
        }
    }


def outcome(monkeypatch, calls, world=None, contract=None, *, sparse=False):
    declared = load_contract(canonical_json(contract or raw_contract()))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    material = run_operations(world or initial(), calls)
    if sparse:
        material["task_evidence"]["initial"] = copy.deepcopy(world)  # public state as authored
    task, _, trace = native_fixture(material)
    # native_fixture's prompt differs; bind this task's public prompt instead.
    data = AutomationBenchData.model_validate(
        {**task.data.model_dump(mode="json"), "prompt": PROMPT}
    )
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    findings = sorted(
        {
            (body["status"], body["value"], body["reason"])
            for batch in trace.assessment_batches
            for receipt in batch.run.execution_evidence
            if (body := json.loads(receipt.payload_json)).get("kind") == "finding"
        }
    )
    assert len(findings) == 1, findings
    return findings[0]


def test_fresh_retained_draft_with_referenced_content_is_the_outcome(monkeypatch):
    assert outcome(monkeypatch, [draft()]) == (
        "valid",
        1.0,
        "created_matching_fresh_object_retained",
    )


@pytest.mark.parametrize(
    "calls",
    [
        [draft(to="cfo@example.com")],  # wrong recipient
        [draft(subject="Q4 Results")],  # wrong subject
        [draft(), send_latest_draft()],  # created but sent: not retained as a draft
        [send()],  # a sent email is not a draft
        [],  # nothing created
    ],
)
def test_non_matching_or_unretained_drafts_are_a_known_zero(monkeypatch, calls):
    assert outcome(monkeypatch, calls)[:2] == ("valid", 0.0)


def test_pre_existing_matching_draft_is_not_fresh(monkeypatch):
    assert outcome(monkeypatch, [], world=initial(drafts=("d_old",)))[:2] == ("valid", 0.0)
    assert outcome(monkeypatch, [draft()], world=initial(drafts=("d_old",)))[:2] == ("valid", 1.0)


def test_public_draft_without_explicit_id_keeps_freshness_unknown(monkeypatch):
    world = initial(drafts=("d_old",))
    del world["gmail"]["drafts"][0]["id"]  # hydrated with a generated id: it would look fresh
    assert outcome(monkeypatch, [], world=world, sparse=True)[:2] == ("abstained", None)
    # Neither terminal draft can be proven fresh: the old one's id was generated.
    assert outcome(monkeypatch, [draft()], world=world, sparse=True)[:2] == ("abstained", None)


def evidence_for(final_gmail, public_gmail=None, complete=True):
    source = {
        "task_evidence": {
            "initial": {"gmail": public_gmail or {}},
            "final": {"gmail": final_gmail},
            "complete": complete,
        }
    }
    return capture_created_records(source, CreatedRecordSource.model_validate(DRAFTS))


def test_references_resolve_one_unique_terminal_record_or_nothing():
    message = {"id": "m1", "to": ["board@example.com"]}
    ok = evidence_for({"drafts": [{"id": "d1", "message_id": "m1"}], "messages": [message]})
    assert ok.complete and json.loads(ok.final.objects[0].object_json) == {
        "id": "d1",
        "record": {"id": "d1", "message_id": "m1"},
        "message": message,
    }
    dangling = evidence_for({"drafts": [{"id": "d1", "message_id": "gone"}], "messages": [message]})
    assert "message" not in json.loads(dangling.final.objects[0].object_json)
    ambiguous = evidence_for(
        {"drafts": [{"id": "d1", "message_id": "m1"}], "messages": [message, message]}
    )
    assert "message" not in json.loads(ambiguous.final.objects[0].object_json)
    duplicate = evidence_for(
        {"drafts": [{"id": "d1", "message_id": "m1"}] * 2, "messages": [message]}
    )
    assert not duplicate.final.closed and not duplicate.complete
    # An omitted collection is decided by the simulator's own hydration:
    # Gmail's 'emails' alias feeds messages, never drafts.
    aliased = evidence_for({"drafts": [], "messages": []}, public_gmail={"emails": [{"id": "m0"}]})
    assert aliased.initial.identities_complete and aliased.initial.all_object_ids == ()
    malformed = evidence_for({"drafts": [], "messages": []}, public_gmail={"drafts": "bad"})
    assert not malformed.initial.identities_complete
    assert not evidence_for({"drafts": [], "messages": []}, complete=False).complete


def test_selector_validation_and_canonical_defaults():
    plain = CreatedRecordSource.model_validate(
        {"adapter": "final.created_records@1", "service": "gmail", "collection": "drafts"}
    )
    assert plain.model_dump(mode="json") == {
        "adapter": "final.created_records@1",
        "service": "gmail",
        "collection": "drafts",
    }
    for bad in (
        {"service": "nope", "collection": "drafts"},
        {"service": "gmail", "collection": "labels_x"},
        {
            "service": "gmail",
            "collection": "drafts",
            "references": {"m": {"field": "nope", "collection": "messages"}},
        },
        {
            "service": "gmail",
            "collection": "drafts",
            "references": {"record": {"field": "message_id", "collection": "messages"}},
        },
    ):
        with pytest.raises(ValidationError):
            CreatedRecordSource.model_validate({"adapter": "final.created_records@1", **bad})


def test_outcome_only_adapter_rejects_completion_credit_and_effect_checks():
    raw = raw_contract()
    raw["credit"] = [
        {
            "policy": "created_retained_completion_once@1",
            "check": "board-draft-retained",
            "effects": "drafts",
            "goal_fields": ["subject"],
            "selection": "earliest",
        }
    ]
    with pytest.raises(ValidationError):
        load_contract(canonical_json(raw))
    raw = raw_contract()
    raw["checks"] = [
        {
            "check_id": "x",
            "signal_id": "x",
            "role": "goal",
            "operator": "effects.required_when@1",
            "semantics": "new_occurrence",
            "population": "request",
            "source": "drafts",
            "required_when": literal(True),
            "effect_match": literal(True),
        }
    ]
    with pytest.raises((ValidationError, ValueError)):
        load_contract(canonical_json(raw))


EPISODE = Path(
    "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/"
    "luna-reference-campaign-01/remaining700/timed/"
    "5a575a6e5a186cc1f861924955ec15840962d596f357d0ce891be00ef09aa2cc/episode.json"
)
EPISODE_SHA256 = "a0b852d5ee29f5054a81743b749ad2666a28eb676470adb3975f60a587623fd1"


def findings(trace, start):
    return sorted(
        (body["status"], body["value"], body["reason"])
        for batch in trace.assessment_batches[start:]
        for receipt in batch.run.execution_evidence
        if (body := json.loads(receipt.payload_json)).get("kind") == "finding"
    )


def test_recorded_sales_draft_is_retained_with_rescore_and_reload(monkeypatch):
    if not EPISODE.exists():
        pytest.skip("retained Luna episode unavailable")
    raw = EPISODE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EPISODE_SHA256
    episode = vf.WireEpisode.model_validate_json(raw)
    trace = cast(Any, episode.traces[0])
    data = AutomationBenchData.model_validate(trace.task.data.model_dump(mode="json"))
    prompt = data.model_dump(mode="json")["prompt"][1]["content"]
    declared = load_contract(
        canonical_json(raw_contract(("task_evidence", "prompt", 1, "content"), prompt))
    )
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    trace.state = AutomationBenchState(
        world=trace.info["automationbench"]["end_state"],
        initial_state=data.initial_state,
        assertions=data.assertions,
        artifacts=dict(trace.state.artifacts),
    )
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    first = findings(trace, 0)
    assert not trace.assessment_errors and not trace.credit_errors
    assert ("valid", 1.0, "created_matching_fresh_object_retained") in first
    start = len(trace.assessment_batches)
    asyncio.run(task.score(trace))
    assert findings(trace, start) == first
    replay = cast(Any, vf.WireEpisode.model_validate_json(episode.model_dump_json()).traces[0])
    replay.state = trace.state
    start = len(replay.assessment_batches)
    asyncio.run(task.score(replay))
    assert findings(replay, start) == first
    assert trace.rewards == scalar and replay.rewards == scalar and EPISODE.read_bytes() == raw
