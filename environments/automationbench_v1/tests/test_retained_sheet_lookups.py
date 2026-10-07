"""A public Sheet mapping supplies a goal, never an invented action witness."""

import asyncio
import copy

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import penalties, terminal_records
from test_manifest_record_retained_credit import clean, contract, scored
from test_manifest_zendesk_effects import initial

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.populations import capture_population
from automationbench_v1.contracts.retained_records import (
    capture_record_retention,
    evaluate_retained_records,
)
from automationbench_v1.contracts.tables import capture_table


def fixture(*, damage=None):
    world = initial()
    world["google_sheets"] = {"spreadsheets": [{"id": "policy", "title": "Public policy"}],
        "worksheets": [{"id": "targets", "spreadsheet_id": "policy", "title": "Targets"}],
        "rows": [{"spreadsheet_id": "policy", "worksheet_id": "targets",
            "row_id": 2, "cells": {"Ticket": "T-1", "Target": "solved"}}]}
    if damage == "duplicate":
        other = copy.deepcopy(world["google_sheets"]["rows"][0])
        other.update(row_id=3)
        world["google_sheets"]["rows"].append(other)
    elif damage == "missing":
        world["google_sheets"]["rows"].clear()
    elif damage == "field":
        del world["google_sheets"]["rows"][0]["cells"]["Target"]
    raw = contract().model_dump(mode="json")
    raw["sources"]["targets"] = {"adapter": "google_sheets.rows@1",
        "path": ["task_evidence", "initial", "google_sheets"], "spreadsheet_id": "policy",
        "worksheet_id": "targets", "key_fields": ["Ticket"], "required_fields": ["Target"]}
    check = raw["checks"][0]
    check["lookups"] = [{"source": "targets", "alias": "policy", "keys": {
        "Ticket": {"kind": "field", "path": ["request", "id"], "domain": "string"}}}]
    check["retained_when"]["right"] = {"kind": "field", "path": ["policy", "Target"], "domain": "string"}
    return world, load_contract(canonical_json(raw))


@pytest.mark.parametrize("damage", [None, "duplicate", "missing", "field"])
@pytest.mark.parametrize("missing_ack", [None, 0])
def test_sheet_goal_native_completion_and_reload(monkeypatch, damage, missing_ack):
    world, declaration = fixture(damage=damage)
    task, episode, trace = scored(monkeypatch, public=world, declaration=declaration, missing_ack=missing_ack)
    clean(trace)
    target = next(item for item in terminal_records(trace)
        if item.signal.signal_id == "manufactured.ticket_solved" and item.subject.kind == "trace")
    assert target.status == ("valid" if damage is None else "abstained")
    assert target.value == (1 if damage is None else None)
    credits = penalties(trace)
    assert len(credits) == int(damage is None and missing_ack is None)
    if credits:
        assert credits[0].recipient.execution.invocation_id == "execution-0"
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = loaded.traces[0]
    replay.state = trace.state
    asyncio.run(task.score(replay))
    clean(replay)
    assert tuple(replay.credit_assignments) == tuple(trace.credit_assignments)
    assert replay.rewards == trace.rewards


def test_sheet_lookup_raw_tamper_is_not_admitted_as_cached_projection():
    world, declaration = fixture()
    source = {"task_evidence": {"initial": world, "final": copy.deepcopy(world), "complete": True}}
    specs = {name: declaration.sources[name] for name in ("initial", "targets")}
    populations = {"initial": capture_population(source, specs["initial"]),
        "targets": capture_table(source, specs["targets"])}
    final = declaration.sources["final"]
    retained = capture_record_retention(source, final)
    source["task_evidence"]["initial"]["google_sheets"]["rows"][0]["cells"]["Target"] = "open"
    with pytest.raises(ValueError, match="initial_projection_mismatch"):
        evaluate_retained_records(source, declaration.checks[0], populations, retained,
            population_sources=specs, retention_source=final)


def test_lookup_rejects_final_tables_and_undeclared_nested_cells():
    _, declaration = fixture()
    raw = declaration.model_dump(mode="json")
    raw["sources"]["targets"]["path"][1] = "final"
    with pytest.raises(ValueError, match="requires_initial_lookup"):
        load_contract(canonical_json(raw))
    raw = declaration.model_dump(mode="json")
    raw["checks"][0]["retained_when"]["right"]["path"].append("nested")
    with pytest.raises(ValueError, match="projection_undeclared"):
        load_contract(canonical_json(raw))
