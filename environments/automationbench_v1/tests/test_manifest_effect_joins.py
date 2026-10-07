"""Generated-object relationships: an effect must reference an earlier effect."""

import asyncio
import copy
import json
from typing import Any

import pytest
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.monday.actions import (
    monday_change_status_column_value,
    monday_create_item,
)
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import ObligationCheck, load_contract


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def world():
    return {"google_sheets": {"worksheets": [{"id": "t", "spreadsheet_id": "s", "title": "Trainings"}],
                              "rows": [{"spreadsheet_id": "s", "worksheet_id": "t", "row_id": 1,
                                        "cells": {"Training": "Safety Training", "Board": "brd_training"}}]}}


def create(name="Safety Training", board="brd_training"):
    args: dict[str, Any] = {"board_id": board, "item_name": name}
    return zapier("monday_create_item", args, lambda w: monday_create_item(w, **args))


def set_status(item_id, label="Scheduled"):
    """Reference by literal id, or by index of an earlier create (resolved at run time)."""
    def handler(w):
        target = item_id if isinstance(item_id, str) else w.monday.actions["create_item"][item_id].id
        return monday_change_status_column_value(w, board_id="brd_training", item_id=target,
                                                 column_id="status", value_label=label)
    return "monday_change_status_column_value", {"item_id": str(item_id), "value_label": label}, handler


CREATED_ON_BOARD = {"op": "all", "args": [
    {"op": "eq", "left": field("effect", "record", "params", "item_id"), "right": field("joined", "record_id")},
    {"op": "eq", "left": field("joined", "record", "params", "board_id"), "right": field("request", "Board")}]}


def contract(where=CREATED_ON_BOARD, timing="not_after", reference=("join", "created")):
    check = {"check_id": "status-on-created-item", "signal_id": "ops.training_status", "role": "goal",
             "operator": "effects.required_when@1", "semantics": "new_occurrence",
             "population": "trainings", "source": "status_updates",
             "required_when": {"op": "ne", "left": field("request", "Training"),
                               "right": {"kind": "literal", "value": ""}},
             "effect_match": {"op": "all", "args": [
                 {"op": "eq", "left": field(*reference), "right": {"kind": "literal", "value": "matched"}},
                 {"op": "eq", "left": field("joined", "created", "record", "params", "item_name"),
                  "right": field("request", "Training")},
                 {"op": "eq", "left": field("effect", "record", "params", "value_label"),
                  "right": {"kind": "literal", "value": "Scheduled"}}]},
             "effect_joins": [{"alias": "created", "source": "creates", "where": where, "timing": timing}]}
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "join-fixture", "revision": "1",
        "public_request": "Create the training item and set its status to Scheduled.",
        "sources": {"trainings": {"adapter": "google_sheets.rows@1",
                                  "path": ["task_evidence", "initial", "google_sheets"],
                                  "spreadsheet_id": "s", "worksheet_id": "t", "key_fields": ["Training"],
                                  "required_fields": ["Board"]},
                    "creates": {"adapter": "service.record_writes@1", "service": "monday",
                                "collection": ["actions", "create_item"], "kind": "create"},
                    "status_updates": {"adapter": "service.record_writes@1", "service": "monday",
                                       "collection": ["actions", "change_status_column_value"], "kind": "create"}},
        "checks": [check]}))


def outcome(monkeypatch, calls, declared=None, missing_ack=None):
    declared = declared or contract()
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, _, trace = native_fixture(run_operations(world(), calls), missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    for batch in trace.assessment_batches:
        for receipt in batch.run.execution_evidence:
            body = json.loads(receipt.payload_json)
            if body.get("kind") == "finding":
                return body["status"], body["value"]
    raise AssertionError("no finding")


def test_status_on_the_created_item_is_witnessed(monkeypatch):
    assert outcome(monkeypatch, [create(), set_status(0)]) == ("valid", 1)


def test_status_on_an_item_not_created_in_the_run_is_zero(monkeypatch):
    assert outcome(monkeypatch, [create(), set_status("monday_preexisting")]) == ("valid", 0)


def test_status_before_the_create_is_zero(monkeypatch):
    def early(w):
        return monday_change_status_column_value(w, board_id="brd_training", item_id="monday_future",
                                                 column_id="status", value_label="Scheduled")
    calls = [("monday_change_status_column_value", {"item_id": "x"}, early), create()]
    assert outcome(monkeypatch, calls) == ("valid", 0)


def test_item_created_on_another_board_is_zero(monkeypatch):
    assert outcome(monkeypatch, [create(board="brd_other"), set_status(0)]) == ("valid", 0)


def test_two_possible_earlier_effects_leave_the_link_unknown(monkeypatch):
    board_only = {"op": "eq", "left": field("joined", "record", "params", "board_id"),
                  "right": field("request", "Board")}
    status, value = outcome(monkeypatch, [create(), create(), set_status(0)], contract(where=board_only))
    assert (status, value) == ("abstained", None)


def test_missing_ack_on_the_create_leaves_the_link_unknown(monkeypatch):
    assert outcome(monkeypatch, [create(), set_status(0)], missing_ack=0)[0] == "abstained"


def test_before_timing_excludes_the_same_call():
    check = contract(timing="before").checks[0]
    assert isinstance(check, ObligationCheck) and check.effect_joins[0].timing == "before"


@pytest.mark.parametrize("change,message", [
    ({"reference": ("join", "other")}, "obligation_join_reference_unknown"),
    ({"where": {"op": "eq", "left": field("lookup", "x"), "right": {"kind": "literal", "value": "y"}}},
     "obligation_lookup_status_reference_unknown"),
    ({"where": {"op": "eq", "left": field("member", "x"), "right": {"kind": "literal", "value": "y"}}},
     "obligation_join_context_unknown"),
])
def test_join_declarations_are_closed(change, message):
    with pytest.raises(ValidationError, match=message):
        contract(**change)


def test_join_cannot_be_read_by_required_when_or_target_a_population():
    raw = contract().model_dump(mode="json")
    raw["checks"][0]["required_when"] = {"op": "eq", "left": field("join", "created"),
                                         "right": {"kind": "literal", "value": "matched"}}
    with pytest.raises(ValidationError, match="obligation_join_reference_unknown"):
        load_contract(canonical_json(raw))
    raw = contract().model_dump(mode="json")
    raw["checks"][0]["effect_joins"][0]["source"] = "trainings"
    with pytest.raises(ValidationError, match="obligation_join_requires_effect_source"):
        load_contract(canonical_json(raw))


def test_join_source_joins_selector_identity():
    from automationbench_v1.manifest_guard_assessments import selectors_digest

    declared = contract()
    check = declared.checks[0]
    assert isinstance(check, ObligationCheck)
    plain = check.model_copy(update={"effect_joins": ()})
    assert selectors_digest(declared, check) != selectors_digest(declared, plain)


def test_any_match_accepts_several_earlier_effects(monkeypatch):
    board_only = {"op": "eq", "left": field("joined", "record", "params", "board_id"),
                  "right": field("request", "Board")}
    raw = contract(where=board_only).model_dump(mode="json")
    raw["checks"][0]["effect_joins"][0]["match"] = "any"
    declared = load_contract(canonical_json(raw))
    assert outcome(monkeypatch, [create(), create(), set_status(0)], declared) == ("valid", 1)
    assert outcome(monkeypatch, [create(board="brd_other"), set_status(0)], declared) == ("valid", 0)


def test_any_timing_finds_a_later_effect(monkeypatch):
    def early(w):
        return monday_change_status_column_value(w, board_id="brd_training", item_id="monday_x",
                                                 column_id="status", value_label="Scheduled")
    board_only = {"op": "eq", "left": field("joined", "record", "params", "board_id"),
                  "right": field("request", "Board")}
    raw = contract(where=board_only).model_dump(mode="json")
    raw["checks"][0]["effect_joins"][0]["timing"] = "any"
    declared = load_contract(canonical_json(raw))
    calls = [("monday_change_status_column_value", {"item_id": "x"}, early), create()]
    assert outcome(monkeypatch, calls, declared) == ("valid", 1)
    raw["checks"][0]["effect_joins"][0]["timing"] = "not_after"
    assert outcome(monkeypatch, calls, load_contract(canonical_json(raw))) == ("valid", 0)  # later create missed
