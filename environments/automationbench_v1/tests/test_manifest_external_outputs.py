"""Real installed handler alternatives for shared external-field evidence."""

import copy
import json

import pytest
from test_contact_task_manifests import public
from test_manifest_guard_assessments import native_fixture
from test_notification_evidence import run_operations, zapier
from verifiers.v1.assessment_source import capture_trace_source

from automationbench.tools.zapier.gmail.message import gmail_get_email_by_id
from automationbench.tools.zapier.salesforce.contact import salesforce_contact_update
from automationbench_v1.authored_output_source import build_authored_output_material
from automationbench_v1.contracts.external_outputs import (
    ExternalOutputSource,
    capture_external_outputs,
    validate_external_outputs,
)
from automationbench_v1.tools import AutomationBenchToolset, _registry

NAME = "simple.email_sf_contact_assistant_update"


def source(calls=None, *, fields=None, initial=None, missing_ack=None):
    initial = copy.deepcopy(initial or public(NAME)["initial_state"])
    fields = fields if fields is not None else {"assistant_name": "Kevin Torres", "assistant_email": "kevin@example.com"}
    args = {"id": "003010", **fields}
    update = zapier("salesforce_contact_update", args, lambda world: salesforce_contact_update(world, **args))
    material = run_operations(initial, calls if calls is not None else [update])
    _, _, trace = native_fixture(material, missing_ack=missing_ack)
    task = {**material["task_evidence"], "complete": True, "authored_outputs": build_authored_output_material(trace)}
    return json.loads(capture_trace_source(trace, task_evidence=task).source_json)


def captured(raw):
    return capture_external_outputs(raw, ExternalOutputSource())


def test_contact_values_are_authored_text_with_relations_not_assumed_non_summary():
    raw = source(fields={"assistant_name": "Skipped Bob", "assistant_email": "kevin@example.com"})
    evidence = captured(raw)
    # Manufactured native envelopes have no qualified model-call inventory.
    assert not evidence.closed and evidence.status == "partial"
    assert evidence.reason == "invocation_model_inventory_unavailable"
    assert {item.field: item.text for item in evidence.text_records} == {
        "assistant_name": "Skipped Bob", "assistant_email": "kevin@example.com"}
    assert all(item.record_id == "003010" and item.surface == "record_field" for item in evidence.text_records)
    assert all(item.changed for item in evidence.action_relations)
    assert evidence.invocation_coverage[0].disposition == "authored_fields"
    validate_external_outputs(evidence, raw, ExternalOutputSource())
    restored = type(evidence).model_validate_json(evidence.model_dump_json())
    validate_external_outputs(restored, raw, ExternalOutputSource())


def test_noop_submission_retains_text_without_claiming_changed_state():
    initial = public(NAME)["initial_state"]
    contact = initial["salesforce"]["contacts"][0]
    contact["assistant_name"] = "Kevin Torres"
    evidence = captured(source(initial=initial, fields={"assistant_name": "Kevin Torres"}))
    assert not evidence.closed and len(evidence.text_records) == 1
    assert evidence.text_records[0].text == "Kevin Torres"
    assert not evidence.action_relations[0].changed


@pytest.mark.parametrize("fields", [
    {"description": "Skipped Bob"},
    {"assistant_name": "Kevin Torres", "description": "Updated Rachel"},
    {"assistant_name": None},
    {},
])
def test_unsupported_or_failed_update_never_closes_external_capture(fields):
    evidence = captured(source(fields=fields))
    assert not evidence.closed and evidence.status == "unavailable"
    assert evidence.invocation_coverage[0].disposition == "unavailable"


def test_supported_read_is_audited_no_authored_fields():
    args = {"message_id": "msg_3010"}
    read = zapier("gmail_get_email_by_id", args, lambda world: gmail_get_email_by_id(world, **args))
    evidence = captured(source([read]))
    assert not evidence.closed and not evidence.text_records and not evidence.action_relations
    assert evidence.invocation_coverage[0].disposition == "no_authored_fields"


def test_missing_ack_never_establishes_capture_completeness():
    evidence = captured(source(missing_ack=0))
    assert not evidence.closed and not evidence.text_records


def test_installed_registry_handler_substitution_is_unavailable(monkeypatch):
    raw = source()
    monkeypatch.setitem(_registry()._tool_map, "salesforce_contact_update", lambda **kwargs: "ignored")
    evidence = captured(raw)
    assert not evidence.closed
    assert evidence.invocation_coverage[0].reason == "external_output_installed_handler_mismatch"


def test_discovery_handler_substitution_cannot_claim_read_only_coverage(monkeypatch):
    search = ("search_tools", {"query": "Gmail", "top_k": 5}, lambda world: json.dumps([]))
    raw = source([search])
    monkeypatch.setattr(AutomationBenchToolset, "search_tools", lambda self, query, top_k=5: "different")
    evidence = captured(raw)
    assert not evidence.closed
    assert evidence.invocation_coverage[0].disposition == "unavailable"
    assert evidence.invocation_coverage[0].reason == "external_output_installed_handler_mismatch"


def test_outer_execution_handler_substitution_keeps_coverage_open(monkeypatch):
    raw = source()
    monkeypatch.setattr(AutomationBenchToolset, "execute_tool", lambda self, tool_name, arguments: "different")
    evidence = captured(raw)
    assert not evidence.closed and not evidence.text_records
    assert evidence.invocation_coverage[0].reason == "external_output_installed_handler_mismatch"


def test_projected_text_and_raw_source_tampering_are_rejected():
    raw = source()
    evidence = captured(raw)
    forged = evidence.model_copy(update={"text_records": ()})
    with pytest.raises(ValueError, match="raw_source_or_projection"):
        validate_external_outputs(forged, raw, ExternalOutputSource())
    altered = copy.deepcopy(raw)
    altered["task_evidence"]["complete"] = False
    with pytest.raises(ValueError, match="raw_source_or_projection"):
        validate_external_outputs(evidence, altered, ExternalOutputSource())


def test_later_repair_or_repetition_keeps_each_authored_submission_visible():
    calls = []
    for name in ("Skipped Bob", "Kevin Torres", "Kevin Torres"):
        args = {"id": "003010", "assistant_name": name}
        calls.append(zapier("salesforce_contact_update", args,
            lambda world, arguments=args: salesforce_contact_update(world, **arguments)))
    evidence = captured(source(calls))
    assert [item.text for item in evidence.text_records] == ["Skipped Bob", "Kevin Torres", "Kevin Torres"]
    assert [item.changed for item in evidence.action_relations] == [True, True, False]
    assert len({item.output_id for item in evidence.text_records}) == 3


def test_unrelated_unsupported_record_text_does_not_erase_known_authored_fields():
    calls = []
    for fields in ({"assistant_name": "Skipped Bob"}, {"description": "Updated Rachel"}):
        args = {"id": "003010", **fields}
        calls.append(zapier("salesforce_contact_update", args,
            lambda world, arguments=args: salesforce_contact_update(world, **arguments)))
    evidence = captured(source(calls))
    assert not evidence.closed and evidence.status == "partial"
    assert [item.text for item in evidence.text_records] == ["Skipped Bob"]
    assert [item.disposition for item in evidence.invocation_coverage] == ["authored_fields", "unavailable"]
