"""Genuine Google Sheets read handlers: returned rows as read evidence and join sources."""

import asyncio
import copy
import json
from dataclasses import asdict
from typing import Any

import pytest
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.google_drive.actions import google_drive_find_multiple_files
from automationbench.tools.zapier.google_sheets.row import (
    google_sheets_add_row,
    google_sheets_find_many_rows,
    google_sheets_get_many_rows,
    google_sheets_get_row_by_id,
    google_sheets_lookup_row,
    google_sheets_update_row,
)
from automationbench.tools.zapier.google_sheets.spreadsheet import (
    google_sheets_get_spreadsheet_by_id,
)
from automationbench.tools.zapier.google_sheets.worksheet import google_sheets_find_worksheet
from automationbench.tools.zapier.slack.messaging import slack_send_channel_message
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import SheetReadSource, load_contract
from automationbench_v1.contracts.sheet_reads import capture_sheet_reads, validate_sheet_reads

SHEET, HOLD, OTHER = "ss_ops", "ws_legal_hold", "ws_vendors"


def initial():
    return {
        "slack": {"channels": [{"id": "Cprivacy", "name": "privacy", "channel_type": "public"}]},
        "google_sheets": {
            "spreadsheets": [{"id": SHEET, "title": "Operations"}, {"id": "ss_misc", "title": "Misc"}],
            "worksheets": [
                {"id": HOLD, "spreadsheet_id": SHEET, "title": "Legal Hold", "headers": ["Customer", "Hold"]},
                {"id": OTHER, "spreadsheet_id": SHEET, "title": "Vendors", "headers": ["Vendor"]},
                {"id": "ws_misc", "spreadsheet_id": "ss_misc", "title": "Legal Hold", "headers": ["Customer"]}],
            "rows": [
                {"id": "row_acme", "spreadsheet_id": SHEET, "worksheet_id": HOLD, "row_id": 2,
                 "cells": {"Customer": "Acme", "Hold": "yes"}},
                {"id": "row_beta", "spreadsheet_id": SHEET, "worksheet_id": HOLD, "row_id": 3,
                 "cells": {"Customer": "Beta", "Hold": "no"}},
                {"id": "row_vendor", "spreadsheet_id": SHEET, "worksheet_id": OTHER, "row_id": 2,
                 "cells": {"Vendor": "Globex"}},
                {"id": "row_misc", "spreadsheet_id": "ss_misc", "worksheet_id": "ws_misc", "row_id": 2,
                 "cells": {"Customer": "Acme"}}]}}


def call(name, function, **args: Any):
    return zapier(name, args, lambda world: function(world, **args))


READS = {
    "many": lambda: call("google_sheets_get_many_rows", google_sheets_get_many_rows,
                         spreadsheet=SHEET, worksheet="Legal Hold"),
    "raw": lambda: call("google_sheets_get_many_rows", google_sheets_get_many_rows,
                        spreadsheet_id="Operations", worksheet_id=HOLD, output_format="raw_rows"),
    "find": lambda: call("google_sheets_find_many_rows", google_sheets_find_many_rows,
                         spreadsheet=SHEET, worksheet=HOLD, lookup_key="Customer", lookup_value="acme"),
    "lookup": lambda: call("google_sheets_lookup_row", google_sheets_lookup_row,
                           spreadsheet="Operations", worksheet="legal hold", lookup_key="Customer",
                           lookup_value="Acme"),
    "get": lambda: call("google_sheets_get_row_by_id", google_sheets_get_row_by_id,
                        spreadsheet=SHEET, worksheet=HOLD, row_id=2),
    "grid": lambda: call("google_sheets_get_spreadsheet_by_id", google_sheets_get_spreadsheet_by_id,
                         spreadsheet=SHEET, includeGridData=True),
}


def post(text="Purged Acme's personal data"):
    return call("slack_send_channel_message", slack_send_channel_message, channel="Cprivacy", text=text)


def read_other():
    return call("google_sheets_get_many_rows", google_sheets_get_many_rows, spreadsheet=SHEET, worksheet=OTHER)


def write_hold():
    return call("google_sheets_update_row", google_sheets_update_row, spreadsheet=SHEET, worksheet=HOLD,
                row=2, cells={"Hold": "yes"})


def material(calls, world=None):
    source = run_operations(world or initial(), calls)
    _, _, trace = native_fixture(source)
    source["tool_execution_events"] = [{"source": "tool_server", "receipt_json": event.receipt_json}
                                       for event in trace.tool_execution_events]
    source["state_write_receipts"] = [receipt.model_dump(mode="json") for receipt in trace.state_write_receipts]
    return source


def evidence(source, **selector):
    return capture_sheet_reads(source, SheetReadSource(spreadsheet_id=SHEET, **selector))


def positive(value):
    return [json.loads(fact.params_json) for fact in value.effects if fact.status == "qualified"]


@pytest.mark.parametrize("name", sorted(READS))
def test_every_row_read_handler_returns_the_stored_hold_row(name):
    value = evidence(material([READS[name]()]), worksheet_id=HOLD)
    assert value.complete, value.reason
    [params] = positive(value)
    assert params["spreadsheet_id"] == SHEET and params["worksheet_id"] == HOLD
    assert params["worksheet_title"] == "Legal Hold" and params["operation"].startswith("google_sheets_")
    assert "row_acme" in params["native_row_ids"] and 2 in params["row_ids"]
    assert params["cell_values_returned"] is True and "Customer" in params["returned_fields"]


def test_full_reads_and_filtered_reads_are_distinguished():
    full = positive(evidence(material([READS["many"]()]), worksheet_id=HOLD))[0]
    assert full["all_rows_returned"] and full["native_row_ids"] == ["row_acme", "row_beta"]
    found = positive(evidence(material([READS["find"]()]), worksheet_id=HOLD))[0]
    assert not found["all_rows_returned"] and found["native_row_ids"] == ["row_acme"]


def test_spreadsheet_reads_yield_one_fact_per_returned_worksheet():
    value = evidence(material([READS["grid"]()]))
    assert value.complete and {params["worksheet_id"] for params in positive(value)} == {HOLD, OTHER}
    plain = call("google_sheets_get_spreadsheet_by_id", google_sheets_get_spreadsheet_by_id, spreadsheet=SHEET)
    facts = positive(evidence(material([plain]), worksheet_id=HOLD))
    assert len(facts) == 1 and facts[0]["cell_values_returned"] is False and facts[0]["row_count"] == 0


def test_metadata_and_empty_searches_read_the_worksheet_without_values():
    worksheet = call("google_sheets_find_worksheet", google_sheets_find_worksheet, spreadsheet=SHEET,
                     title="legal hold")
    empty = call("google_sheets_lookup_row", google_sheets_lookup_row, spreadsheet=SHEET, worksheet=HOLD,
                 lookup_key="Customer", lookup_value="Nobody")
    value = evidence(material([worksheet, empty]), worksheet_id=HOLD)
    assert value.complete and [(p["operation"], p["row_count"], p["cell_values_returned"])
                               for p in positive(value)] == [("google_sheets_find_worksheet", 0, False),
                                                             ("google_sheets_lookup_row", 0, False)]


@pytest.mark.parametrize("calls", [
    [call("google_sheets_get_row_by_id", google_sheets_get_row_by_id, spreadsheet=SHEET, worksheet=HOLD,
          row_id=99)],
    [call("google_sheets_get_many_rows", google_sheets_get_many_rows, spreadsheet=SHEET, worksheet="Nope")],
    [call("google_drive_find_multiple_files", google_drive_find_multiple_files, title="Operations")],
    [call("google_sheets_get_many_rows", google_sheets_get_many_rows, spreadsheet="Misc", worksheet="Legal Hold")],
])
def test_failed_metadata_only_and_other_spreadsheet_reads_return_nothing(calls):
    value = evidence(material(calls), worksheet_id=HOLD)
    assert value.complete and positive(value) == []


def test_reading_another_worksheet_is_not_a_read_of_the_declared_one():
    source = material([read_other()])
    assert evidence(source, worksheet_id=HOLD).complete and positive(evidence(source, worksheet_id=HOLD)) == []
    assert [p["worksheet_id"] for p in positive(evidence(source))] == [OTHER]


def test_writes_and_other_services_are_not_reads_and_keep_scope_closed():
    append = call("google_sheets_add_row", google_sheets_add_row, spreadsheet=SHEET, worksheet=HOLD,
                  cells={"Customer": "Gamma", "Hold": "no"})
    value = evidence(material([write_hold(), append, post()]), worksheet_id=HOLD)
    assert value.complete and value.effects == ()


def test_rewritten_result_cannot_invent_a_read():
    source = material([READS["get"]()])
    tampered = copy.deepcopy(source)
    for event in tampered["tool_execution_events"]:
        receipt = json.loads(event["receipt_json"])
        if receipt["phase"] != "returned":
            continue
        capture = json.loads(receipt["evidence_json"][0])
        result = json.loads(json.loads(capture["action"]["result_json"]))
        result["row"]["cells"]["Hold"] = "no"
        encoded = canonical_json(json.dumps(result))
        capture["action"]["result_json"] = receipt["result_json"] = encoded
        receipt["evidence_json"][0] = canonical_json(capture)
        event["receipt_json"] = canonical_json(receipt)
    value = evidence(tampered, worksheet_id=HOLD)
    assert not value.complete and positive(value) == []
    assert value.effects[0].reason == "sheet_read_returned_cells_mismatch"


def test_api_fetch_leaves_the_inventory_incomplete():
    from automationbench.tools.api import api_fetch

    args = {"method": "GET", "url": f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET}/values/Legal%20Hold"}
    value = evidence(material([("api_fetch", args, lambda world: api_fetch(world, **args))]), worksheet_id=HOLD)
    assert not value.complete and value.reason == "sheet_read_operation_unsupported"


def test_missing_ack_leaves_the_inventory_incomplete_and_validation_is_exact():
    source = material([READS["get"]()])
    spec = SheetReadSource(spreadsheet_id=SHEET, worksheet_id=HOLD)
    validate_sheet_reads(evidence(source, worksheet_id=HOLD), source, spec)
    broken = copy.deepcopy(source)
    broken["state_write_receipts"] = []
    assert not evidence(broken, worksheet_id=HOLD).complete
    forged = evidence(source, worksheet_id=HOLD)
    with pytest.raises(ValueError, match="sheet_read_raw_source_or_projection_mismatch"):
        validate_sheet_reads(type(forged)(**{**asdict(forged), "complete": False}), source, spec)


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def literal(value):
    return {"kind": "literal", "value": value}


POPULATION = {"adapter": "google_sheets.rows@1", "path": ["task_evidence", "initial", "google_sheets"],
              "spreadsheet_id": SHEET, "worksheet_id": HOLD, "key_fields": ["Customer"]}
ACME = {"op": "eq", "left": field("request", "Customer"), "right": literal("Acme")}
READ_HOLD_SHEET = {"op": "eq", "left": field("joined", "cell_values_returned", domain="boolean"),
                   "right": literal(True)}
READ_THIS_ROW = {"op": "in", "left": field("candidate", "native_record_id"),
                 "right": field("joined", "native_row_ids", domain="sequence")}


def purge_contract(timing="before", where=READ_HOLD_SHEET):
    check = {"check_id": "purge-after-legal-hold", "signal_id": "support.purge_after_hold_check", "role": "goal",
             "operator": "effects.required_when@1", "semantics": "new_occurrence",
             "population": "holds", "source": "posts", "required_when": ACME,
             # The post does not name the row, so each candidate is judged on its own (mechanism 16).
             "match_cardinality": "per_candidate",
             "effect_match": {"op": "eq", "left": field("join", "hold"), "right": literal("matched")},
             "effect_joins": [{"alias": "hold", "source": "reads", "timing": timing, "match": "any",
                               "where": where}]}
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "sheet-read-join", "revision": "1",
        "public_request": "Read the legal hold sheet before purging, then announce the purge in #privacy.",
        "sources": {"holds": POPULATION,
                    "reads": {"adapter": "google_sheets.reads@1", "spreadsheet_id": SHEET, "worksheet_id": HOLD},
                    "posts": {"adapter": "slack.messages@1", "kind": "channel_message"}},
        "checks": [check]}))


def read_contract():
    check = {"check_id": "read-legal-hold", "signal_id": "support.read_legal_hold", "role": "goal",
             "operator": "effects.required_when@1", "semantics": "new_occurrence",
             "population": "holds", "source": "reads", "required_when": ACME,
             "effect_match": {"op": "in", "left": field("candidate", "native_record_id"),
                              "right": field("effect", "native_row_ids", domain="sequence")}}
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "sheet-read-source", "revision": "1",
        "public_request": "Check the legal hold row for Acme.",
        "sources": {"holds": POPULATION,
                    "reads": {"adapter": "google_sheets.reads@1", "spreadsheet_id": SHEET, "worksheet_id": HOLD}},
        "checks": [check]}))


def outcome(monkeypatch, declared, calls, missing_ack=None):
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, _, trace = native_fixture(run_operations(initial(), calls), missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    findings = []
    for batch in trace.assessment_batches:
        for receipt in batch.run.execution_evidence:
            body = json.loads(receipt.payload_json)
            if body.get("kind") == "finding" and body["status"] != "inapplicable":
                findings.append((body.get("instance_key"), body["status"], body["value"]))
    assert findings and len({item[1:] for item in findings}) == 1, findings
    return findings[0][1:]


def test_read_then_act_is_witnessed(monkeypatch):
    assert outcome(monkeypatch, purge_contract(), [READS["find"](), post()]) == ("valid", 1)
    assert outcome(monkeypatch, purge_contract(), [READS["grid"](), post()]) == ("valid", 1)
    assert outcome(monkeypatch, purge_contract(where=READ_THIS_ROW), [READS["get"](), post()]) == ("valid", 1)


def test_act_then_read_is_a_known_zero_with_before_timing(monkeypatch):
    assert outcome(monkeypatch, purge_contract(), [post(), READS["many"]()]) == ("valid", 0)
    assert outcome(monkeypatch, purge_contract("any"), [post(), READS["many"]()]) == ("valid", 1)


def test_reading_another_worksheet_or_another_row_is_a_known_zero(monkeypatch):
    assert outcome(monkeypatch, purge_contract(), [read_other(), post()]) == ("valid", 0)
    beta = call("google_sheets_lookup_row", google_sheets_lookup_row, spreadsheet=SHEET, worksheet=HOLD,
                lookup_key="Customer", lookup_value="Beta")
    assert outcome(monkeypatch, purge_contract(where=READ_THIS_ROW), [beta, post()]) == ("valid", 0)


def test_a_write_only_call_is_not_a_read(monkeypatch):
    assert outcome(monkeypatch, purge_contract(), [write_hold(), post()]) == ("valid", 0)


def test_missing_ack_leaves_the_act_unknown(monkeypatch):
    assert outcome(monkeypatch, purge_contract(), [READS["find"](), post()], missing_ack=0)[0] == "abstained"


def test_reads_are_an_obligation_source(monkeypatch):
    assert outcome(monkeypatch, read_contract(), [READS["lookup"]()]) == ("valid", 1)
    assert outcome(monkeypatch, read_contract(), [read_other()]) == ("valid", 0)
    assert outcome(monkeypatch, read_contract(), [READS["get"]()], missing_ack=0)[0] == "abstained"


def test_sheet_reads_cannot_be_a_guard_source_and_defaults_are_stable():
    raw = purge_contract().model_dump(mode="json")
    assert raw["sources"]["reads"] == {"adapter": "google_sheets.reads@1", "kind": "read_sheet",
                                       "spreadsheet_id": SHEET, "worksheet_id": HOLD}
    assert SheetReadSource(spreadsheet_id=SHEET).model_dump(mode="json") == {
        "adapter": "google_sheets.reads@1", "kind": "read_sheet", "spreadsheet_id": SHEET}
    raw["checks"] = [{"check_id": "g", "signal_id": "g", "role": "harm", "operator": "effects.prohibited_when@1",
                      "population": "holds", "source": "reads", "prohibited_when": ACME, "effect_match": ACME}]
    with pytest.raises(ValidationError, match="sheet_read_requires_obligation_check"):
        load_contract(canonical_json(raw))


def test_every_installed_sheets_handler_is_classified():
    from automationbench_v1.contracts import sheet_reads
    from automationbench_v1.contracts.handler_scope import handler_footprints

    sheets = {name for name, footprint in handler_footprints().items() if footprint and "google_sheets" in footprint}
    assert not sheet_reads._READS & sheet_reads._SHEET_WRITES
    assert sheets == sheet_reads._READS | sheet_reads._SHEET_WRITES


def test_sheet_reads_are_a_guard_join_source():
    raw = purge_contract().model_dump(mode="json")
    raw["checks"] = [{"check_id": "g", "signal_id": "g", "role": "harm", "operator": "effects.prohibited_when@1",
                      "population": "holds", "source": "posts", "prohibited_when": ACME,
                      "match_cardinality": "per_candidate",
                      "effect_match": {"op": "ne", "left": field("join", "hold"), "right": literal("matched")},
                      "effect_joins": [{"alias": "hold", "source": "reads", "timing": "before", "match": "any",
                                        "where": READ_HOLD_SHEET}]}]
    assert load_contract(canonical_json(raw)).checks[0].effect_joins[0].source == "reads"
