"""Obligations satisfied by any of several channels (e.g. Gmail or Slack)."""

import asyncio
import copy
import json

import pytest
from pydantic import ValidationError
from test_manifest_guard_assessments import native_fixture
from test_manifest_slack_effects import dm
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.gmail.message import gmail_send_email
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract


def field(*path, domain="string"):
    return {"kind": "field", "path": list(path), "domain": domain}


def world():
    return {"gmail": {"messages": [], "drafts": []},
            "slack": {"channels": [{"id": "Cproduct", "name": "product", "channel_type": "public"}],
                      "users": [{"id": "Usarah", "name": "Sarah Jones", "username": "sarah",
                                 "email": "sarah@example.com"}], "messages": []},
            "google_sheets": {"worksheets": [{"id": "b", "spreadsheet_id": "s", "title": "Buddies"}],
                              "rows": [{"spreadsheet_id": "s", "worksheet_id": "b", "row_id": 1,
                                        "cells": {"Buddy": "Sarah Jones", "Email": "sarah@example.com",
                                                  "Slack": "Usarah", "Hire": "Hal"}}]}}


def email(to="sarah@example.com", body="You are Hal's buddy"):
    args = {"to": to, "subject": "Buddy", "body": body}
    return zapier("gmail_send_email", args, lambda w: gmail_send_email(w, **args))


MENTIONS_HIRE = {"op": "mentions", "text": field("effect", "text"), "mode": "words", "value": field("request", "Hire")}


def contract(alternatives=True):
    check = {"check_id": "buddy-notified", "signal_id": "hr.buddy_notified", "role": "goal",
             "operator": "effects.required_when@1", "semantics": "new_occurrence",
             "population": "buddies", "source": "sends",
             "required_when": {"op": "ne", "left": field("request", "Buddy"), "right": {"kind": "literal", "value": ""}},
             "effect_match": {"op": "all", "args": [
                 {"op": "in", "left": field("request", "Email"), "right": field("effect", "recipients", domain="sequence")},
                 {"op": "mentions", "text": field("effect", "body_text"), "mode": "words",
                  "value": field("request", "Hire")}]}}
    if alternatives:
        check["alternatives"] = [{"alias": "slack_dm", "source": "dms", "effect_match": {"op": "all", "args": [
            {"op": "eq", "left": field("effect", "recipient_user_id"), "right": field("request", "Slack")},
            MENTIONS_HIRE]}}]
    return load_contract(canonical_json({
        "schema_version": 1, "manifest_id": "buddy-any-channel", "revision": "1",
        "public_request": "Notify each buddy by email or Slack.",
        "sources": {"buddies": {"adapter": "google_sheets.rows@1", "path": ["task_evidence", "initial", "google_sheets"],
                                "spreadsheet_id": "s", "worksheet_id": "b", "key_fields": ["Buddy"],
                                "required_fields": ["Email", "Slack", "Hire"]},
                    "sends": {"adapter": "gmail.messages@1", "kind": "send"},
                    "dms": {"adapter": "slack.messages@1", "kind": "direct_message"}},
        "checks": [check],
        "credit": [{"check": "buddy-notified", "policy": "required_effect_once@1", "channel": "useful"}]}))


def scored(monkeypatch, calls, declared=None, missing_ack=None):
    declared = declared or contract()
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declared)
    task, _, trace = native_fixture(run_operations(world(), calls), missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert trace.rewards == scalar and not trace.assessment_errors and not trace.credit_errors
    finding = next(json.loads(r.payload_json) for b in trace.assessment_batches for r in b.run.execution_evidence
                   if json.loads(r.payload_json).get("kind") == "finding")
    credited = [part.recipient.execution.invocation_id for a in trace.credit_assignments if a.status == "complete"
                for part in a.contributions if part.value == 1]
    return (finding["status"], finding["value"]), credited


def test_email_satisfies_the_obligation(monkeypatch):
    assert scored(monkeypatch, [email()]) == (("valid", 1), ["execution-0"])


def test_slack_dm_satisfies_the_obligation(monkeypatch):
    assert scored(monkeypatch, [dm(text="Hi Sarah, you are Hal's buddy")]) == (("valid", 1), ["execution-0"])


def test_neither_channel_is_a_known_zero(monkeypatch):
    outcome, credited = scored(monkeypatch, [email(to="other@example.com"), dm(text="No names here")])
    assert outcome == ("valid", 0) and not credited


def test_without_the_alternative_a_slack_dm_is_zero(monkeypatch):
    assert scored(monkeypatch, [dm(text="you are Hal's buddy")], contract(alternatives=False))[0] == ("valid", 0)


def test_missing_ack_on_one_channel_leaves_absence_unknown(monkeypatch):
    outcome, _ = scored(monkeypatch, [email(to="other@example.com"), dm(text="No names")], missing_ack=1)
    assert outcome[0] == "abstained"


def test_alternative_sources_must_be_effect_sources():
    raw = contract().model_dump(mode="json")
    raw["checks"][0]["alternatives"][0]["source"] = "buddies"
    with pytest.raises(ValidationError, match="obligation_alternative_requires_effect_source"):
        load_contract(canonical_json(raw))
    raw = contract().model_dump(mode="json")
    raw["checks"][0]["alternatives"].append(raw["checks"][0]["alternatives"][0])
    with pytest.raises(ValidationError, match="obligation_alternative_alias_conflict"):
        load_contract(canonical_json(raw))
