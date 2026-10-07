"""Genuine list lookups and read-before-card ordering, with native archive parity."""

import asyncio
import copy
import json

import pytest
import verifiers.v1 as vf
from test_manifest_airtable_record_writes import contract as write_contract
from test_manifest_airtable_record_writes import initial as sheet_initial
from test_manifest_gmail_observations import material, mutate_return
from test_manifest_guard_assessments import native_fixture, terminal_records
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.trello.actions import (
    trello_board_list,
    trello_card,
    trello_card_label,
    trello_card_update,
    trello_list_by_id,
    trello_to_board_list,
)
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.trello_reads import (
    TrelloListReadSource,
    _project,
    capture_trello_list_reads,
)
from automationbench_v1.tools import AutomationBenchState


def initial(*, operation="board_list", scope=True):
    value = sheet_initial()
    params = {"id": "list-1", "list": "list-1", "name": "To Do"}
    if scope:
        params.update(board="board-1", to_board="board-1")
    value["trello"] = {"actions": {operation: [{"id": "audit-1", "action_key": operation, "params": params}]}}
    return value


def read(operation="board_list", **overrides):
    fn = {"board_list": trello_board_list, "list_by_id": trello_list_by_id, "to_board_list": trello_to_board_list}[operation]
    args = {"board": "board-1", "name": "To Do"} if operation == "board_list" else {"id": "list-1"} if operation == "list_by_id" else {"to_board": "board-1"}
    args.update(overrides)
    return zapier("trello_" + operation, args, lambda world: fn(world, **args))


def card():
    args = {"board": "board-1", "list": "list-1", "name": "Card"}
    return zapier("trello_card", args, lambda world: trello_card(world, **args))


def capture(value):
    return capture_trello_list_reads(value, TrelloListReadSource())


@pytest.mark.parametrize("operation", ["board_list", "list_by_id", "to_board_list"])
def test_native_search_exact_returned_action_record(operation):
    value = capture(material([read(operation)], initial(operation=operation)))
    assert value.complete, value.reason
    (fact,) = value.effects
    fields = json.loads(fact.params_json)
    assert fields["storage_kind"] == "action_record" and fields["record"]["list"] == "list-1"
    assert fields["native_record_id"] == "list-1"


def test_missing_stored_scope_never_backfills_requested_board():
    value = capture(material([read(board="foreign")], initial(scope=False)))
    assert value.complete
    assert "board" not in json.loads(value.effects[0].params_json)["record"]


def test_find_or_create_miss_is_not_a_read():
    value = capture(material([read(name="New List")], initial()))
    assert not value.complete and all(f.status == "unavailable" for f in value.effects)


@pytest.mark.parametrize("damage", ["field", "count", "branch", "id"])
def test_coherently_forged_return_does_not_become_read(damage):
    def change(result):
        if damage == "field":
            result["results"][0]["list"] = "foreign"
        elif damage == "count":
            result["count"] = 8
        elif damage == "branch":
            result["found"] = False
        else:
            result["results"][0]["id"] = "foreign"
    value = capture(mutate_return(material([read()], initial()), change))
    assert not value.complete and all(f.status == "unavailable" for f in value.effects)


def test_empty_pure_lookup_and_known_write_inventory():
    value = capture(material([read("list_by_id", id="absent"), card()], initial(operation="list_by_id")))
    assert value.complete, value.reason
    assert len(value.effects) == 1 and json.loads(value.effects[0].params_json)["found"] is False


def test_audited_card_update_does_not_poison_read_inventory():
    args = {"card": "card-1", "board": "board-1", "list": "list-1"}
    update = zapier("trello_card_update", args, lambda world: trello_card_update(world, **args))
    source = material([read(), update], initial())
    evidence = capture(source)
    assert evidence.complete and len(evidence.effects) == 1, evidence.reason
    source['state_write_receipts'] = source['state_write_receipts'][:-1]
    assert not capture(source).complete


def test_missing_ack_and_args_forgery_abstain():
    source = material([read()], initial())
    source["state_write_receipts"] = []
    assert not capture(source).complete
    source = material([read()], initial())
    event = source["tool_execution_events"][1]
    receipt = json.loads(event["receipt_json"])
    receipt["arguments_json"] = canonical_json({"args": [], "kwargs": {"board": "foreign", "name": "To Do"}})
    event["receipt_json"] = canonical_json(receipt)
    assert not capture(source).complete


def test_audited_label_write_keeps_read_inventory_and_requires_ack():
    args = {"board": "board-1", "card": "card-1", "label": "urgent"}
    label = zapier("trello_card_label", args, lambda world: trello_card_label(world, **args))
    source = material([read(), card(), label], initial())
    evidence = capture(source)
    assert evidence.complete and len(evidence.effects) == 1, evidence.reason
    assert json.loads(evidence.effects[0].params_json)["record"]["list"] == "list-1"
    source["state_write_receipts"] = source["state_write_receipts"][:-1]
    assert not capture(source).complete


def test_projection_bounds():
    with pytest.raises(ValueError, match="budget"):
        _project({}, "trello_board_list", {}, {"success": True, "results": [{}] * 4097})


def declaration():
    raw = write_contract().model_dump(mode="json")
    raw["sources"]["writes"] = {"adapter": "service.record_writes@1", "service": "trello", "collection": ["actions", "card"], "kind": "create"}
    raw["sources"]["reads"] = TrelloListReadSource().model_dump(mode="json")
    raw["checks"][0]["effect_match"] = {"op": "eq", "left": {"kind": "field", "path": ["effect", "record", "params", "name"]}, "right": {"kind": "literal", "value": "Card"}}
    raw["checks"][0]["effect_match"] = {"op": "all", "args": [raw["checks"][0]["effect_match"], {
        "op": "eq", "left": {"kind": "field", "path": ["join", "list_read"]},
        "right": {"kind": "literal", "value": "matched"}}]}
    raw["checks"][0]["effect_joins"] = [{"alias": "list_read", "source": "reads", "timing": "any", "match": "any", "order": "returned_before_dispatch", "where": {
        "op": "eq", "left": {"kind": "field", "path": ["joined", "record", "list"]}, "right": {"kind": "field", "path": ["effect", "record", "params", "list"]}}}]
    raw["credit"] = []
    return load_contract(canonical_json(raw))


@pytest.mark.parametrize("scenario,expected", [("ordered", ("valid", 1)), ("late", ("valid", 0)), ("missing", ("abstained", None))])
def test_native_read_before_card_join_reload_scalar(monkeypatch, scenario, expected):
    contract = declaration()
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    calls = [card(), read()] if scenario == "late" else [read(), card()]
    task, _, trace = native_fixture(run_operations(initial(), calls), missing_ack=0 if scenario == "missing" else None)
    wire = vf.WireEpisode.model_validate({"task": trace.task.model_dump(mode="json"), "traces": [trace.model_dump(mode="json")]})
    scored = wire.traces[0]
    scored.state = trace.state
    rewards = copy.deepcopy(scored.rewards)
    asyncio.run(task.score(scored))
    findings = {(r.signal.signal_id, r.status, r.value) for r in terminal_records(scored)}
    assert ("expense.status", *expected) in findings, findings
    assert scored.rewards == rewards and not scored.assessment_errors and not scored.credit_errors
    restored = vf.WireEpisode.model_validate_json(wire.model_dump_json()).traces[0]
    restored.state = AutomationBenchState.model_validate(scored.state.model_dump(mode="json"))
    asyncio.run(task.score(restored))
    assert {(r.signal.signal_id, r.status, r.value) for r in terminal_records(restored)} == findings
    assert restored.rewards == rewards and not restored.assessment_errors
