"""Native search response evidence distinguishes seed results from stored rows."""

import asyncio
import copy
import json

import pytest
import verifiers.v1 as vf
from test_manifest_airtable_record_writes import contract as write_contract
from test_manifest_airtable_record_writes import initial as stored_initial
from test_manifest_gmail_observations import material, mutate_return
from test_manifest_guard_assessments import native_fixture, terminal_records
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.airtable.actions import (
    airtable_findManyRecords,
    airtable_findRecord,
)
from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.airtable_reads import (
    AirtableReadSource,
    _project,
    capture_airtable_reads,
)
from automationbench_v1.manifest_guard_assessments import _capture_effect_input
from automationbench_v1.tools import AutomationBenchState


def initial():
    return {"airtable": {"bases": [], "actions": {"findRecord": [{
        "id": "seed", "action_key": "findRecord", "params": {
            "applicationId": "public-base", "tableName": "Contacts",
            "fields": {"Email": "jordan@example.com", "Status": "Active"},
            "searchField": "Email", "searchValue": "jordan@example.com"}}]}}}


def read(*, many=False, stored=False, search="jordan@example.com"):
    name = "airtable_findManyRecords" if many else "airtable_findRecord"
    fn = airtable_findManyRecords if many else airtable_findRecord
    args = {"applicationId": "app" if stored else "foreign-base",
            "tableName": "Requests" if stored else "foreign-table",
            "searchByField": "Status" if stored else "Email",
            "searchByValue": "Pending" if stored else search}
    return zapier(name, args, lambda world: fn(world, **args))


def capture(source):
    return capture_airtable_reads(source, AirtableReadSource())


@pytest.mark.parametrize("many", [False, True])
@pytest.mark.parametrize("stored", [False, True])
def test_real_handler_returns_only_authenticated_fields(many, stored):
    public = stored_initial() if stored else initial()
    if many and not stored:
        public["airtable"]["actions"]["findManyRecords"] = public["airtable"]["actions"].pop("findRecord")
    source = material([read(many=many, stored=stored)], public)
    value = _capture_effect_input(source, AirtableReadSource())
    assert value.complete, value.reason
    (fact,) = value.effects
    params = json.loads(fact.params_json)
    assert params["storage_kind"] == ("stored_table" if stored else "seeded_action")
    assert params["record"]["fields"]["Status"] == ("Pending" if stored else "Active")
    assert params["native_record_id"] == ("r1" if stored else "seed")
    assert "base_id" not in params and "table_id" not in params


def test_empty_search_is_explicit_and_complete():
    value = capture(material([read(search="absent")], initial()))
    assert value.complete
    assert json.loads(value.effects[0].params_json) == {"found": False, "returned_count": 0, "storage_kind": "none"}


@pytest.mark.parametrize("damage", ["field", "count", "id", "duplicate"])
def test_forged_native_and_local_return_still_rejects_source_mismatch(damage):
    def change(result):
        if damage == "field":
            result["results"][0]["fields"]["Status"] = "Forged"
        elif damage == "count":
            result["count"] = 9
        elif damage == "id":
            result["results"][0]["id"] = "foreign"
        else:
            result["results"].append(copy.deepcopy(result["results"][0]))
    value = capture(mutate_return(material([read()], initial()), change))
    assert not value.complete and all(f.status == "unavailable" for f in value.effects)


def test_missing_ack_and_terminal_tamper_cannot_close_inventory():
    source = material([read()], initial())
    source["state_write_receipts"] = []
    assert not capture(source).complete
    source = material([read()], initial())
    source["task_evidence"]["final"]["airtable"]["actions"] = {}
    assert not capture(source).complete


def test_projection_budget_precedes_native_reexecution():
    with pytest.raises(ValueError, match="budget"):
        _project({}, "airtable_findRecord", {}, {"success": True, "results": [{}] * 4097})
    with pytest.raises(ValueError, match="source_budget"):
        _project({"airtable": {"large": "x" * (8 * 1024 * 1024)}}, "airtable_findRecord", {},
                 {"success": True, "results": []})


@pytest.mark.parametrize("missing_ack", [None, 0])
def test_native_manifest_reload_and_scalar_noninterference(monkeypatch, missing_ack):
    raw = write_contract().model_dump(mode="json")
    raw["sources"]["writes"] = AirtableReadSource().model_dump(mode="json")
    raw["checks"][0]["effect_match"] = {"op": "eq", "left": {
        "kind": "field", "path": ["effect", "record", "fields", "Status"]},
        "right": {"kind": "literal", "value": "Pending"}}
    raw["credit"] = []
    contract = load_contract(canonical_json(raw))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    task, _, trace = native_fixture(run_operations(stored_initial(), [read(stored=True)]), missing_ack=missing_ack)
    wire = vf.WireEpisode.model_validate({"task": trace.task.model_dump(mode="json"),
                                         "traces": [trace.model_dump(mode="json")]})
    scored = wire.traces[0]
    scored.state = trace.state
    rewards = copy.deepcopy(scored.rewards)
    asyncio.run(task.score(scored))
    findings = {(r.signal.signal_id, r.status, r.value) for r in terminal_records(scored)}
    assert ("expense.status", "valid", 1) in findings if missing_ack is None else (
        "expense.status", "abstained", None) in findings, (findings, scored.assessment_errors)
    assert scored.rewards == rewards and not scored.assessment_errors and not scored.credit_errors
    restored = vf.WireEpisode.model_validate_json(wire.model_dump_json()).traces[0]
    restored.state = AutomationBenchState.model_validate(scored.state.model_dump(mode="json"))
    asyncio.run(task.score(restored))
    assert {(r.signal.signal_id, r.status, r.value) for r in terminal_records(restored)} == findings
    assert restored.rewards == rewards and not restored.assessment_errors
