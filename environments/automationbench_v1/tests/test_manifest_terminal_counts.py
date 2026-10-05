"""Admission and authenticated collective outcomes, separate from action credit."""

import copy

import pytest
from test_manifest_guards import comparison, field, literal

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.populations import InitialCollectionSource
from automationbench_v1.contracts.retained_records import (
    RetainedRecordSource,
    capture_record_retention,
)
from automationbench_v1.contracts.sheet_effects import SheetEffectSource
from automationbench_v1.contracts.tables import TableSource
from automationbench_v1.contracts.terminal_counts import (
    TerminalCountCheck,
    capture_terminal_count_population,
    capture_terminal_count_retention,
    evaluate_terminal_counts,
)


def fixture(candidates=2, members=2):
    initial = InitialCollectionSource(path=("task_evidence", "initial", "salesforce", "contacts"),
        fields={"ID": ("id",)}, key_fields=("ID",))
    final = RetainedRecordSource(path=("task_evidence", "final", "zendesk", "tickets"),
        fields={"Status": ("status",)})
    check = TerminalCountCheck(check_id="roster", signal_id="roster", population="initial", source="final",
        counts=[{"alias": "open", "where": comparison("eq", field("member", "Status"), literal("open"))}],
        required_when=comparison("eq", literal(True), literal(True)),
        counts_when=comparison("eq", {"kind": "field", "path": ["count", "open"], "domain": "integer"}, literal(members)))
    source = {"task_evidence": {"initial": {"salesforce": {"contacts": [{"id": f"c{i}"} for i in range(candidates)]}},
        "final": {"zendesk": {"tickets": [{"id": f"t{i}", "status": "open"} for i in range(members)]}}, "complete": True}}
    return source, initial, final, check


def evaluate(source, initial, final, check, *, population=None, retained=None):
    return evaluate_terminal_counts(source, check,
        population or capture_terminal_count_population(source, initial),
        retained or capture_record_retention(source, final), population_source=initial, retention_source=final)


@pytest.mark.parametrize("target", ["initial", "final"])
def test_raw_mutation_rejects_previously_captured_projection(target):
    source, initial, final, check = fixture()
    population = capture_terminal_count_population(source, initial)
    retained = capture_record_retention(source, final)
    if target == "initial":
        source["task_evidence"]["initial"]["salesforce"]["contacts"][0]["id"] = "different"
    else:
        source["task_evidence"]["final"]["zendesk"]["tickets"][0]["status"] = "solved"
    with pytest.raises(ValueError, match="source_or_projection_mismatch"):
        evaluate(source, initial, final, check, population=population, retained=retained)


@pytest.mark.parametrize("candidates,members", [(0, 2), (2, 0)])
def test_closed_empty_population_is_decided_without_inventing_candidate(candidates, members):
    result = evaluate(*fixture(candidates, members))
    assert result.scope_complete
    assert len(result.findings) == candidates
    assert all(finding.value == 1 and finding.native_record_id is None for finding in result.findings)


def test_instance_and_comparison_budgets_do_not_emit_partial_totals():
    source, initial, final, check = fixture(256, 257)
    result = evaluate(source, initial, final, check)
    assert not result.scope_complete and len(result.findings) == 256
    assert all(finding.value is None and finding.reason == "terminal_count_comparison_budget_exceeded"
               for finding in result.findings)
    check = TerminalCountCheck.model_validate({**check.model_dump(mode="python"), "max_instances": 255})
    result = evaluate(source, initial, final, check)
    assert not result.findings and result.reason == "terminal_count_instance_budget_exceeded"


@pytest.mark.parametrize("mutation,reason", [
    ("unknown_count", "terminal_count_alias_unknown"),
    ("count_dependency", "terminal_count_context_unknown"),
    ("retained_candidate", "terminal_count_context_unknown"),
    ("native_identity", "terminal_count_candidate_metadata_unknown"),
    ("duplicate_alias", "terminal_count_alias_conflict"),
    ("undeclared_initial", "terminal_count_projection_undeclared"),
    ("undeclared_final", "terminal_count_projection_undeclared"),
])
def test_contract_admission_rejects_unsupported_projection_and_context(mutation, reason):
    _, initial, final, check = fixture()
    raw = check.model_dump(mode="json")
    if mutation == "unknown_count":
        raw["counts_when"]["left"]["path"] = ["count", "absent"]
    elif mutation == "count_dependency":
        raw["counts"][0]["where"]["left"]["path"] = ["count", "open"]
    elif mutation == "retained_candidate":
        raw["required_when"]["left"] = field("retained", "ID")
    elif mutation == "native_identity":
        raw["required_when"]["left"] = field("candidate", "native_record_id")
    elif mutation == "duplicate_alias":
        raw["counts"].append(copy.deepcopy(raw["counts"][0]))
    elif mutation == "undeclared_initial":
        raw["required_when"]["left"] = field("request", "absent")
    else:
        raw["counts"][0]["where"]["left"]["path"] = ["member", "absent"]
    declaration = {"schema_version": 1, "manifest_id": "manufactured-count-admission", "revision": "1",
        "public_request": "Manufactured collective outcome.", "sources": {
            "initial": initial.model_dump(mode="json"), "final": final.model_dump(mode="json")}, "checks": [raw]}
    with pytest.raises(ValueError, match=reason):
        load_contract(canonical_json(declaration))


def sheet_fixture(assignments=("Marcus",)):
    initial = TableSource(path=("task_evidence", "initial", "google_sheets"),
        spreadsheet_id="parking", worksheet_id="employees", key_fields=("Name",))
    final = SheetEffectSource(spreadsheet_id="parking", worksheet_id="spots", kind="update")
    check = TerminalCountCheck(check_id="one-spot", signal_id="one-spot", population="initial", source="final",
        member_fields=("Assignee",), counts=[{"alias": "assigned", "where":
            comparison("eq", field("member", "Assignee"), field("request", "Name"))}],
        required_when=comparison("eq", literal(True), literal(True)),
        counts_when=comparison("lte", {"kind": "field", "path": ["count", "assigned"], "domain": "integer"}, literal(1)))
    roster = {"id": "employee", "spreadsheet_id": "parking", "worksheet_id": "employees", "row_id": 1,
              "cells": {"Name": "Marcus"}}
    tabs = [{"id": name, "spreadsheet_id": "parking"} for name in ("employees", "spots")]
    source = {"task_evidence": {"complete": True,
        "initial": {"google_sheets": {"spreadsheets": [{"id": "parking"}], "worksheets": tabs, "rows": [roster]}},
        "final": {"google_sheets": {"spreadsheets": [{"id": "parking"}], "worksheets": tabs,
            "rows": [roster, *[{"id": f"spot-{i}", "spreadsheet_id": "parking", "worksheet_id": "spots",
                               "row_id": i, "cells": {"Assignee": name}} for i, name in enumerate(assignments)]]}}}}
    return source, initial, final, check


def evaluate_sheet(source, initial, final, check, *, retained=None):
    return evaluate_terminal_counts(source, check, capture_terminal_count_population(source, initial),
        retained or capture_terminal_count_retention(source, final), population_source=initial, retention_source=final)


@pytest.mark.parametrize("assignments,value", [((), 1), (("Marcus",), 1), (("Marcus", "Marcus"), 0)])
def test_sheet_counts_detect_duplicate_employee_and_authenticate_raw_row_paths(assignments, value):
    source, initial, final, check = sheet_fixture(assignments)
    result = evaluate_sheet(source, initial, final, check)
    assert result.scope_complete and result.findings[0].value == value
    if assignments:
        assert ("task_evidence", "final", "google_sheets", "rows", 1) in result.findings[0].evidence_paths
    retained = capture_terminal_count_retention(source, final)
    assert evaluate_sheet(source, initial, final, check, retained=type(retained).model_validate_json(retained.model_dump_json())) == result


@pytest.mark.parametrize("mutation", ["unfinished", "missing_cell", "duplicate_id", "missing_worksheet"])
def test_sheet_counts_unavailable_evidence_never_becomes_zero(mutation):
    source, initial, final, check = sheet_fixture()
    if mutation == "unfinished":
        source["task_evidence"]["complete"] = False
    elif mutation == "missing_cell":
        source["task_evidence"]["final"]["google_sheets"]["rows"][1]["cells"] = {}
    elif mutation == "duplicate_id":
        source["task_evidence"]["final"]["google_sheets"]["rows"].append(copy.deepcopy(source["task_evidence"]["final"]["google_sheets"]["rows"][1]))
    else:
        source["task_evidence"]["final"]["google_sheets"]["worksheets"].pop()
    result = evaluate_sheet(source, initial, final, check)
    assert not result.scope_complete and result.findings[0].value is None


def test_sheet_counts_reject_projection_tampering_and_undeclared_headers():
    source, initial, final, check = sheet_fixture()
    retained = capture_terminal_count_retention(source, final)
    source["task_evidence"]["final"]["google_sheets"]["rows"][1]["cells"]["Assignee"] = "Someone else"
    with pytest.raises(ValueError, match="source_or_projection_mismatch"):
        evaluate_sheet(source, initial, final, check, retained=retained)
    from automationbench_v1.contracts.terminal_counts import admit_terminal_count_projections
    raw = check.model_dump(mode="json")
    raw["member_fields"] = ["Other"]
    with pytest.raises(ValueError, match="sheet_projection_undeclared"):
        admit_terminal_count_projections(TerminalCountCheck.model_validate(raw), initial, final)
    raw["member_fields"] = []
    with pytest.raises(ValueError, match="sheet_member_fields_required"):
        admit_terminal_count_projections(TerminalCountCheck.model_validate(raw), initial, final)


@pytest.mark.parametrize("duplicate", [False, True])
@pytest.mark.parametrize("missing_ack", [None, 0])
def test_genuine_sheet_handler_counts_native_reload_and_outcome_only(monkeypatch, duplicate, missing_ack):
    import asyncio

    import verifiers.v1 as vf
    from test_manifest_guard_assessments import native_fixture, penalties, terminal_records
    from test_manifest_sheet_effects import google_sheets_update_row
    from test_notification_evidence import run_operations, zapier

    from automationbench_v1 import manifest_assessments

    source, initial, final, check = sheet_fixture(("", ""))
    world = source["task_evidence"]["final"]
    world["google_sheets"]["spreadsheets"][0]["title"] = "Parking"
    for tab in world["google_sheets"]["worksheets"]:
        tab["title"] = tab["id"]
    calls = []
    for row_id in range(2 if duplicate else 1):
        args = {"spreadsheet_id": "parking", "worksheet_id": "spots", "row": str(row_id), "cells": {"Assignee": "Marcus"}}
        calls.append(zapier("google_sheets_update_row", args,
            lambda state, args=args: google_sheets_update_row(state, **args)))
    material = run_operations(world, calls)
    assert evaluate_sheet(material, initial, final, check).findings[0].value == int(not duplicate)
    declaration = load_contract(canonical_json({"schema_version": 1, "manifest_id": "manufactured-sheet-count",
        "revision": "1", "public_request": "Manufactured one-spot-per-employee invariant.",
        "sources": {"initial": initial.model_dump(mode="json"), "final": final.model_dump(mode="json")},
        "checks": [check.model_dump(mode="json")]}))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declaration)
    task, episode, trace = native_fixture(material, missing_ack=missing_ack)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors and trace.rewards == scalar
    assert [item.value for item in terminal_records(trace) if item.signal.signal_id == "one-spot"] == [int(not duplicate)]
    assert not penalties(trace)
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = loaded.traces[0]
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors and replay.rewards == scalar
    assert [item.value for item in terminal_records(replay) if item.signal.signal_id == "one-spot"][-1] == int(not duplicate)
    rejected = declaration.model_dump(mode="json")
    rejected["credit"] = [{"check": "one-spot", "policy": "records_retained_completion_once@1",
        "channel": "allocation", "effects": "final", "goal_fields": ["Assignee"], "completion_selection": "earliest"}]
    with pytest.raises(ValueError, match="credit_policy_check_capability_mismatch"):
        load_contract(canonical_json(rejected))


def test_outcome_reuse_keys_exact_material_and_keeps_configuration_and_mutation_checks():
    from automationbench_v1 import manifest_record_retained_assessments as native
    from automationbench_v1.contracts.loader import canonical_contract_digest
    from automationbench_v1.manifest_guard_assessments import digest, selectors_digest
    from automationbench_v1.manifest_retained_assessments import RetainedConfig

    source, initial, final, check = sheet_fixture()
    contract = load_contract(canonical_json({"schema_version": 1, "manifest_id": "cache-fixture", "revision": "1",
        "public_request": "Manufactured count invariant.", "sources": {"initial": initial.model_dump(mode="json"),
            "final": final.model_dump(mode="json")}, "checks": [check.model_dump(mode="json")]}))
    material = {"source": source, **native.capture_record_retained_inputs(source, contract)}
    config = RetainedConfig(contract_digest=canonical_contract_digest(contract), source_digest=digest(source),
        selectors_digest=selectors_digest(contract, check), check_id=check.check_id, instance_key="scope",
        candidate_identity=None, potential_instances=1)
    native._prepare_outcome.cache_clear()
    first, populations, retained = native._outcome_output(material, contract, check, config, "0" * 64)
    populations.clear()
    retained.clear()
    second, populations, retained = native._outcome_output(material, contract, check, config, "0" * 64)
    assert second == first and populations and retained
    assert native._prepare_outcome.cache_info().misses == 1 and native._prepare_outcome.cache_info().hits == 1
    bad_config = config.model_copy(update={"potential_instances": 2})
    with pytest.raises(ValueError, match="configuration_mismatch"):
        native._outcome_output(material, contract, check, bad_config, "0" * 64)
    changed_check = check.model_copy(update={"max_instances": 2})
    misses = native._prepare_outcome.cache_info().misses
    native._outcome_output(material, contract, changed_check, config, "0" * 64)
    assert native._prepare_outcome.cache_info().misses == misses + 1
    changed_contract = contract.model_copy(update={"revision": "2"})
    with pytest.raises(ValueError, match="configuration_mismatch"):
        native._outcome_output(material, changed_contract, check, config, "0" * 64)
    # Oversized input bypasses retention but still checks the exact material.
    oversized = copy.deepcopy(material)
    oversized["unused_padding"] = "x" * (8 * 1024 * 1024)
    before = native._prepare_outcome.cache_info()
    uncached, _, _ = native._outcome_output(oversized, contract, check, config, "0" * 64)
    assert uncached == first and native._prepare_outcome.cache_info() == before
    # Keeping the caller-provided input digest unchanged must not admit new raw
    # data against the old projection from a previous successful cache entry.
    material["source"]["task_evidence"]["final"]["google_sheets"]["rows"][1]["cells"]["Assignee"] = "Someone else"
    with pytest.raises(ValueError, match="raw_source_or_selector_mismatch"):
        native._outcome_output(material, contract, check, config, "0" * 64)
    native._prepare_outcome.cache_clear()
