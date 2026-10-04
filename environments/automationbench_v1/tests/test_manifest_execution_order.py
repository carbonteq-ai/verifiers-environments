"""Execution-order join relations from authenticated tool-server receipts.

Minimal reproduction: a state-revision join (``timing: "before"``) matches a
read whose response was returned *after* the action was dispatched, because
revisions order state, not responses. ``order: "returned_before_dispatch"``
and ``order: "overlapping"`` decide those questions from the native receipt
sequence and stay unknown when it is unavailable. Neither relation says
anything about model use.
"""

import asyncio
import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from pydantic import ValidationError
from test_manifest_sheet_reads import HOLD, OTHER, READS, SHEET, initial, post, read_other
from test_notification_evidence import run_operations
from verifiers.v1.mcp.execution import ToolServerReceipt
from verifiers.v1.trace import StateWriteReceipt, ToolServerExecutionEvent

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.execution_order import capture_execution_order, execution_relation
from automationbench_v1.contracts.joins import EffectJoin
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import (
    AutomationBenchData,
    AutomationBenchTask,
    AutomationBenchTaskConfig,
)
from automationbench_v1.tools import AutomationBenchState


@dataclass(frozen=True)
class Fact:
    invocation_id: str
    origin: str = "tool_server"


def event(seq, invocation, phase):
    ordinal = 0 if phase == "dispatch" else 1
    receipt = {"invocation_id": invocation, "phase": phase, "event_index": ordinal}
    return {
        "source": "tool_server",
        "invocation_id": invocation,
        "phase": phase,
        "event_index": ordinal,
        "receipt_seq": seq,
        "receipt_json": json.dumps(receipt),
    }


def events(*layout):
    return {"tool_execution_events": [event(seq, *item) for seq, item in enumerate(layout)]}


SERIAL = events(("r", "dispatch"), ("r", "returned"), ("a", "dispatch"), ("a", "returned"))
INTERLEAVED = events(("r", "dispatch"), ("a", "dispatch"), ("r", "returned"), ("a", "returned"))


def relation(name, source, own="a", joined="r"):
    return execution_relation(name, capture_execution_order(source), Fact(own), Fact(joined))


def test_return_before_dispatch_is_decided_from_receipt_positions():
    assert relation("returned_before_dispatch", SERIAL) is True
    assert (
        relation("returned_before_dispatch", INTERLEAVED) is False
    )  # returned after the action was requested
    assert relation("returned_before_dispatch", SERIAL, own="r", joined="a") is False
    raised = events(("r", "dispatch"), ("r", "raised"), ("a", "dispatch"), ("a", "returned"))
    assert relation("returned_before_dispatch", raised) is False  # no response was returned
    pending = events(("r", "dispatch"), ("a", "dispatch"), ("a", "returned"))
    assert (
        relation("returned_before_dispatch", pending) is False
    )  # never returned before the cutoff
    assert relation("returned_before_dispatch", SERIAL, own="r", joined="r") is False


def test_overlap_is_decided_only_for_two_ended_intervals():
    assert relation("overlapping", INTERLEAVED) is True
    assert relation("overlapping", INTERLEAVED, own="r", joined="a") is True
    assert relation("overlapping", SERIAL) is False  # serialised calls, even if emitted together
    nested = events(("r", "dispatch"), ("a", "dispatch"), ("a", "returned"), ("r", "returned"))
    assert relation("overlapping", nested) is True
    pending = events(("r", "dispatch"), ("a", "dispatch"), ("a", "returned"))
    assert relation("overlapping", pending) is None  # an open interval has no observed end


@pytest.mark.parametrize(
    "source",
    [
        {},  # no inventory
        {"tool_execution_events": "bad"},
        {"tool_execution_events": [event(1, "r", "dispatch")]},  # sequence gap
        events(("r", "returned"), ("a", "dispatch")),  # terminal without dispatch
        events(("r", "dispatch"), ("r", "dispatch"), ("r", "returned")),  # duplicate dispatch
        events(("r", "dispatch"), ("r", "returned"), ("r", "returned")),  # duplicate terminal
    ],
)
def test_unavailable_or_contradictory_order_is_unknown(source):
    order = capture_execution_order(source)
    assert not order.available
    assert execution_relation("returned_before_dispatch", order, Fact("a"), Fact("r")) is None
    assert execution_relation("overlapping", order, Fact("a"), Fact("r")) is None


def test_receipt_identity_must_agree_and_unknown_invocations_stay_unknown():
    forged = copy.deepcopy(SERIAL)
    forged["tool_execution_events"][1]["receipt_json"] = json.dumps(
        {"invocation_id": "other", "phase": "returned", "event_index": 1}
    )
    assert not capture_execution_order(forged).available
    order = capture_execution_order(SERIAL)
    assert execution_relation("returned_before_dispatch", order, Fact("a"), Fact("missing")) is None
    assert (
        execution_relation("returned_before_dispatch", order, Fact("a", "harness"), Fact("r"))
        is None
    )
    assert execution_relation("returned_before_dispatch", None, Fact("a"), Fact("r")) is None
    # Harness/interceptor events share the sequence but are not tool-server bounds.
    mixed = events(("r", "dispatch"), ("r", "returned"), ("a", "dispatch"), ("a", "returned"))
    mixed["tool_execution_events"].insert(2, {"source": "harness", "receipt_seq": 2})
    for seq, item in enumerate(mixed["tool_execution_events"]):
        item["receipt_seq"] = seq
    assert relation("returned_before_dispatch", mixed) is True


def test_order_is_a_separate_optional_field_requiring_timing_any():
    where = {
        "op": "eq",
        "left": {"kind": "literal", "value": 1},
        "right": {"kind": "literal", "value": 1},
    }
    with pytest.raises(ValidationError, match="join_order_requires_timing_any"):
        EffectJoin.model_validate(
            {"alias": "x", "source": "s", "where": where, "order": "overlapping"}
        )
    with pytest.raises(ValidationError):
        EffectJoin.model_validate(
            {"alias": "x", "source": "s", "where": where, "timing": "any", "order": "after"}
        )
    plain = EffectJoin.model_validate({"alias": "x", "source": "s", "where": where})
    assert "order" not in plain.model_dump(
        mode="json"
    )  # existing contracts keep their canonical bytes
    ordered = EffectJoin.model_validate(
        {
            "alias": "x",
            "source": "s",
            "where": where,
            "timing": "any",
            "order": "returned_before_dispatch",
        }
    )
    assert ordered.model_dump(mode="json")["order"] == "returned_before_dispatch"


# Native fixtures: genuine simulator calls, independently validated native traces,
# with an explicit receipt layout (call index, phase) to express interleaving.


def layout_fixture(material, layout, *, missing_ack=None):
    receipts, writes = {}, []
    for index, reduced in enumerate(material["tool_execution_events"]):
        receipt = json.loads(reduced["receipt_json"])
        payload = json.loads(receipt["evidence_json"][0])
        action = payload["action"]
        identity = {
            "invocation_id": receipt["invocation_id"],
            "tool_name": action["tool_name"],
            "arguments_json": canonical_json(
                {"args": [], "kwargs": json.loads(action["arguments_json"])}
            ),
            "state_read_revision": index,
        }
        acknowledged = index != missing_ack
        receipts[index, "dispatch"] = (
            ToolServerReceipt(**identity, event_index=0, phase="dispatch"),
            index,
        )
        receipts[index, "returned"] = (
            ToolServerReceipt(
                **identity,
                event_index=1,
                phase="returned",
                evidence_json=tuple(receipt["evidence_json"]),
                result_json=action["result_json"],
                state_write_revision=index + 1 if acknowledged else None,
                state_conflict=False if acknowledged else None,
                state_persistence="applied" if acknowledged else "unknown",
            ),
            index + 1,
        )
        if acknowledged:
            writes.append(
                StateWriteReceipt(
                    write_id=receipt["invocation_id"],
                    body_digest=hashlib.sha256(
                        payload["snapshots"][action["after_digest"]].encode()
                    ).hexdigest(),
                    expected_revision=index,
                    applied_revision=index + 1,
                    conflict=False,
                )
            )
    assert sorted(layout) == sorted(receipts)
    events_ = []
    for key in layout:
        envelope, revision = receipts[key]
        events_.append(
            ToolServerExecutionEvent(
                invocation_id=envelope.invocation_id,
                event_index=envelope.event_index,
                phase=envelope.phase,
                receipt_seq=len(events_),
                state_revision=revision,
                receipt_json=canonical_json(envelope.model_dump(mode="json")),
            )
        )
    data = AutomationBenchData(
        domain="support",
        task_name="support.manufactured_order_fixture",
        prompt="Read the legal hold sheet before purging, then announce the purge in #privacy.",
        initial_state=material["task_evidence"]["initial"],
        assertions=(),
        zapier_tools=("google_sheets_get_many_rows",),
    )
    trace = vf.Trace(
        episode_id="manufactured-native-order-envelope",
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type="Task", data=data),
        tool_execution_events=tuple(events_),
        state_write_receipts=tuple(writes),
        tool_state_revision=len(material["tool_execution_events"]),
        is_completed=True,
        ok=True,
        info={"automationbench": {"end_state": material["task_evidence"]["final"]}},
    )
    episode = vf.WireEpisode.model_validate(
        {"task": trace.task.model_dump(mode="json"), "traces": [trace.model_dump(mode="json")]}
    )
    retained = cast(Any, episode.traces[0])
    retained.state = AutomationBenchState(
        world=material["task_evidence"]["final"],
        initial_state=data.initial_state,
        assertions=data.assertions,
    )
    config = AutomationBenchTaskConfig(capture_actions=True)
    asyncio.run(AutomationBenchTask(data, config).score(retained))
    return ManifestAssessmentTask(data, config), episode, retained


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def literal(value):
    return {"kind": "literal", "value": value}


POPULATION = {
    "adapter": "google_sheets.rows@1",
    "path": ["task_evidence", "initial", "google_sheets"],
    "spreadsheet_id": SHEET,
    "worksheet_id": HOLD,
    "key_fields": ["Customer"],
}
ACME = {"op": "eq", "left": field("request", "Customer"), "right": literal("Acme")}
VALUES = {
    "op": "eq",
    "left": field("joined", "cell_values_returned", domain="boolean"),
    "right": literal(True),
}


def contract(source, join_source, *, timing="any", order=None):
    join = {
        "alias": "read",
        "source": join_source,
        "timing": timing,
        "match": "any",
        "where": VALUES,
    }
    if order:
        join["order"] = order
    check = {
        "check_id": "ordered",
        "signal_id": "support.ordered",
        "role": "goal",
        "operator": "effects.required_when@1",
        "semantics": "new_occurrence",
        "population": "holds",
        "source": source,
        "required_when": ACME,
        "match_cardinality": "per_candidate",
        "effect_match": {"op": "eq", "left": field("join", "read"), "right": literal("matched")},
        "effect_joins": [join],
    }
    return load_contract(
        canonical_json(
            {
                "schema_version": 1,
                "manifest_id": "execution-order",
                "revision": "1",
                "public_request": "Read the legal hold sheet before purging, then announce the purge in #privacy.",
                "sources": {
                    "holds": POPULATION,
                    "reads": {
                        "adapter": "google_sheets.reads@1",
                        "spreadsheet_id": SHEET,
                        "worksheet_id": HOLD,
                    },
                    "other_reads": {
                        "adapter": "google_sheets.reads@1",
                        "spreadsheet_id": SHEET,
                        "worksheet_id": OTHER,
                    },
                    "posts": {"adapter": "slack.messages@1", "kind": "channel_message"},
                },
                "checks": [check],
            }
        )
    )


def outcome(monkeypatch, declared, calls, layout, missing_ack=None, *, every=False):
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, _, trace = layout_fixture(
        run_operations(initial(), calls), layout, missing_ack=missing_ack
    )
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    findings = sorted(
        {
            (body["status"], body["value"])
            for batch in trace.assessment_batches
            for receipt in batch.run.execution_evidence
            if (body := json.loads(receipt.payload_json)).get("kind") == "finding"
            and body["status"] != "inapplicable"
        }
    )
    if every:
        return findings
    assert len(findings) == 1, findings
    return findings[0]


SERIAL_LAYOUT = [(0, "dispatch"), (0, "returned"), (1, "dispatch"), (1, "returned")]
INTERLEAVED_LAYOUT = [(0, "dispatch"), (1, "dispatch"), (0, "returned"), (1, "returned")]


def test_read_returned_before_post_dispatch_is_witnessed(monkeypatch):
    declared = contract("posts", "reads", order="returned_before_dispatch")
    assert outcome(monkeypatch, declared, [READS["many"](), post()], SERIAL_LAYOUT) == ("valid", 1)


def test_revision_order_matches_but_return_before_dispatch_does_not(monkeypatch):
    calls = [READS["many"](), post()]
    # The read committed revision 1 before the post read it, so revision order matches...
    assert outcome(
        monkeypatch, contract("posts", "reads", timing="before"), calls, INTERLEAVED_LAYOUT
    ) == ("valid", 1)
    # ...but its response was returned only after the post had been dispatched.
    assert outcome(
        monkeypatch,
        contract("posts", "reads", order="returned_before_dispatch"),
        calls,
        INTERLEAVED_LAYOUT,
    ) == ("valid", 0)


def test_post_then_read_and_other_worksheet_are_known_zero(monkeypatch):
    declared = contract("posts", "reads", order="returned_before_dispatch")
    assert outcome(monkeypatch, declared, [post(), READS["many"]()], SERIAL_LAYOUT) == ("valid", 0)
    assert outcome(monkeypatch, declared, [read_other(), post()], SERIAL_LAYOUT) == ("valid", 0)


def test_missing_read_ack_keeps_ordered_join_unknown(monkeypatch):
    declared = contract("posts", "reads", order="returned_before_dispatch")
    assert (
        outcome(monkeypatch, declared, [READS["many"](), post()], SERIAL_LAYOUT, missing_ack=0)[0]
        == "abstained"
    )


def test_overlapping_reads_are_distinct_from_sequential_reads(monkeypatch):
    declared = contract("reads", "other_reads", order="overlapping")
    calls = [READS["many"](), read_other()]
    assert outcome(monkeypatch, declared, calls, INTERLEAVED_LAYOUT) == ("valid", 1)
    assert outcome(monkeypatch, declared, calls, SERIAL_LAYOUT) == ("valid", 0)


def test_guard_join_order_publishes_returned_before_dispatch(monkeypatch):
    raw = contract("posts", "reads", order="returned_before_dispatch").model_dump(mode="json")
    check = raw["checks"][0]
    raw["checks"] = [
        {
            "check_id": "post-before-read-returned",
            "signal_id": "support.unread_post",
            "role": "harm",
            "operator": "effects.prohibited_when@1",
            "population": "holds",
            "source": "posts",
            "prohibited_when": ACME,
            "match_cardinality": "per_candidate",
            "effect_match": {"op": "eq", "left": field("join", "read"), "right": literal("none")},
            "effect_joins": check["effect_joins"],
        }
    ]
    declared = load_contract(canonical_json(raw))
    calls = [READS["many"](), post()]
    # The Beta row is outside prohibited_when (a decided 0); Acme fires only when interleaved.
    assert outcome(monkeypatch, declared, calls, INTERLEAVED_LAYOUT, every=True) == [
        ("valid", 0),
        ("valid", 1),
    ]
    assert outcome(monkeypatch, declared, calls, SERIAL_LAYOUT, every=True) == [("valid", 0)]
    assert outcome(monkeypatch, declared, calls, SERIAL_LAYOUT, missing_ack=0, every=True) == [
        ("abstained", None),
        ("valid", 0),
    ]


# Real retained Luna episode (support.zendesk_sf_case_sync): three config reads,
# each returned before the next dispatch; case creation dispatched afterwards.

EPISODE = Path(
    "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/"
    "luna-reference-campaign-01/remaining700/untimed/"
    "9cd36b8e356d599cb8c59ca1bf01706068425bff612ab960e01c2f7bb7c3ffd0/episode.json"
)
EPISODE_SHA256 = "466be90646f59d5e65cecc964739ed25d2a2b0b78c50dc86f062ac615d96c412"
CONFIG = {
    "adapter": "google_sheets.rows@1",
    "path": ["task_evidence", "initial", "google_sheets"],
    "spreadsheet_id": "ss_config",
    "worksheet_id": "ws_config",
    "key_fields": ["Setting"],
}
BATCH = {"op": "eq", "left": field("request", "Setting"), "right": literal("Batch_Reference")}


def case_contract(order, source="cases", join_source="config_reads"):
    reads = {
        name: {"adapter": "google_sheets.reads@1", "spreadsheet_id": sheet, "worksheet_id": tab}
        for name, sheet, tab in (
            ("config_reads", "ss_config", "ws_config"),
            ("sla_reads", "ss_sla", "ws_tiers"),
            ("blocklist_reads", "ss_blocklist", "ws_orgs"),
        )
    }
    join = {
        "alias": "read",
        "source": join_source,
        "timing": "any",
        "match": "any",
        "where": VALUES,
        "order": order,
    }
    return load_contract(
        canonical_json(
            {
                "schema_version": 1,
                "manifest_id": "case-order-probe",
                "revision": "1",
                "public_request": "Fetch the config sheets before processing.",
                "sources": {
                    "settings": CONFIG,
                    **reads,
                    "cases": {
                        "adapter": "service.record_writes@1",
                        "service": "salesforce",
                        "collection": ["cases"],
                        "kind": "create",
                    },
                },
                "checks": [
                    {
                        "check_id": "ordered",
                        "signal_id": "support.ordered",
                        "role": "goal",
                        "operator": "effects.required_when@1",
                        "semantics": "new_occurrence",
                        "population": "settings",
                        "source": source,
                        "required_when": BATCH,
                        "match_cardinality": "per_candidate",
                        "effect_match": {
                            "op": "eq",
                            "left": field("join", "read"),
                            "right": literal("matched"),
                        },
                        "effect_joins": [join],
                    }
                ],
            }
        )
    )


def findings(trace, start):
    return sorted(
        (body["status"], body["value"], body["reason"])
        for batch in trace.assessment_batches[start:]
        for receipt in batch.run.execution_evidence
        if (body := json.loads(receipt.payload_json)).get("kind") == "finding"
    )


@pytest.mark.parametrize(
    "order,source,join_source,expected",
    [
        ("returned_before_dispatch", "cases", "blocklist_reads", ("valid", 1)),
        (
            "overlapping",
            "sla_reads",
            "blocklist_reads",
            ("valid", 0),
        ),  # the "parallel" reads were sequential
    ],
)
def test_recorded_episode_order_rescore_and_reload(
    monkeypatch, order, source, join_source, expected
):
    if not EPISODE.exists():
        pytest.skip("retained Luna episode unavailable")
    raw = EPISODE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EPISODE_SHA256
    declared = case_contract(order, source, join_source)
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    episode = vf.WireEpisode.model_validate_json(raw)
    trace = cast(Any, episode.traces[0])
    data = AutomationBenchData.model_validate(trace.task.data.model_dump(mode="json"))
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
    assert {item[:2] for item in first if item[0] != "inapplicable"} == {expected}
    start = len(trace.assessment_batches)
    asyncio.run(task.score(trace))
    assert findings(trace, start) == first
    replay = cast(Any, vf.WireEpisode.model_validate_json(episode.model_dump_json()).traces[0])
    replay.state = trace.state
    start = len(replay.assessment_batches)
    asyncio.run(task.score(replay))
    assert findings(replay, start) == first
    assert trace.rewards == scalar and replay.rewards == scalar
    assert EPISODE.read_bytes() == raw
