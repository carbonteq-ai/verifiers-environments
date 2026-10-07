"""Public parameters beside row candidates, using genuine local handler evidence."""

import asyncio
import copy
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import guard_contract, native_fixture, terminal_records
from test_manifest_guards import comparison, create, field, literal
from test_manifest_obligations import new_occurrence, world
from test_manifest_request_assessments import PROMPT
from test_notification_evidence import run_operations

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts import load_contract
from automationbench_v1.contracts.guards import GuardCheck
from automationbench_v1.contracts.obligations import ObligationCheck
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.manifest_guard_assessments import digest
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig


def declaration(*, bindings=True):
    raw = guard_contract().model_dump(mode="json")
    raw["bindings"] = [{"path": ["task_evidence", "prompt"], "canonical_sha256": digest(PROMPT)}] if bindings else []
    raw["sources"]["parameters"] = {"adapter": "public.request@1", "member_key": "policy", "fields": {
        "threshold": {"value": 3, "authority_paths": [["task_evidence", "prompt"]]},
        # Same spelling as a row field must never replace the row's Status.
        "Status": {"value": "Public parameter", "authority_paths": [["task_evidence", "prompt"]]}}}
    goal = new_occurrence()
    goal["required_when"]["args"][1]["right"] = field("policy", "threshold", domain="integer")
    guard = raw["checks"][0]
    guard["prohibited_when"] = comparison("lt", field("manager", "Rank", domain="integer"), field("policy", "threshold", domain="integer"))
    for check in (goal, guard):
        check["request_aliases"] = [{"alias": "policy", "source": "parameters"}]
    raw["checks"] = [goal, guard]
    raw["credit"] = []
    return raw


def score(monkeypatch, *, bindings=True, rank=4, missing_ack=None, prompt=None):
    contract = load_contract(canonical_json(declaration(bindings=bindings)))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    task, _, trace = native_fixture(run_operations(world(rank=rank), [create()]), missing_ack=missing_ack)
    data = AutomationBenchData.model_validate({**task.data.model_dump(mode="json"), "prompt": prompt or PROMPT})
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    trace.task = trace.task.model_copy(update={"data": data})
    wire = vf.WireEpisode.model_validate({"task": trace.task.model_dump(mode="json"), "traces": [trace.model_dump(mode="json")]})
    retained = cast(Any, wire.traces[0])
    retained.state = trace.state
    rewards = copy.deepcopy(retained.rewards)
    asyncio.run(task.score(retained))
    assert retained.rewards == rewards
    assert not retained.assessment_errors and not retained.credit_errors
    records = {(r.signal.signal_id, r.status, r.value) for r in terminal_records(retained)}
    restored = cast(Any, vf.WireEpisode.model_validate_json(wire.model_dump_json()).traces[0])
    restored.state = retained.state
    asyncio.run(task.score(restored))
    assert {(r.signal.signal_id, r.status, r.value) for r in terminal_records(restored)} == records
    assert restored.rewards == rewards and not restored.assessment_errors
    return {r.signal.signal_id: (r.status, r.value) for r in terminal_records(retained)}


def test_native_public_parameters_do_not_replace_row_fields(monkeypatch):
    result = score(monkeypatch)
    assert result["access.required_effect"] == ("valid", 1)
    assert result["access.prohibited_effect"] == ("valid", 0)


def test_native_guard_uses_public_threshold(monkeypatch):
    result = score(monkeypatch, rank=2)
    assert result["access.required_effect"] == ("inapplicable", None)
    assert result["access.prohibited_effect"] == ("valid", 1)


@pytest.mark.parametrize("options", [{"bindings": False}, {"missing_ack": 0},
    {"prompt": [{"role": "user", "content": "Foreign policy"}]}])
def test_missing_authority_or_ack_stays_unknown(monkeypatch, options):
    result = score(monkeypatch, **options)
    assert result["access.required_effect"] == ("abstained", None)
    assert result["access.prohibited_effect"] == ("abstained", None)


@pytest.mark.parametrize("index,model", [(0, ObligationCheck), (1, GuardCheck)])
def test_aliases_are_bounded_and_namespace_checked(index, model):
    raw = declaration()["checks"][index]
    for alias in ("request", "effect", "candidate", "manager", "lookup", "selected", "joined"):
        changed = raw | {"request_aliases": [{"alias": alias, "source": "parameters"}]}
        with pytest.raises(ValueError, match="alias_conflict"):
            model.model_validate(changed)
    with pytest.raises(ValueError):
        model.model_validate(raw | {"request_aliases": [{"alias": f"p{i}", "source": "parameters"} for i in range(17)]})


def test_alias_source_requires_public_request_and_no_baseline_discharge():
    raw = declaration()
    raw["checks"][0]["request_aliases"][0]["source"] = "queue"
    with pytest.raises(ValueError, match="request_alias_requires_public_request"):
        load_contract(canonical_json(raw))
    raw = declaration()["checks"][0] | {"semantics": "occurrence", "initially_satisfied_when": comparison("eq", field("request", "Status"), literal("Pending"))}
    with pytest.raises(ValueError, match="request_alias_has_no_initial_discharge"):
        ObligationCheck.model_validate(raw)


def test_empty_aliases_preserve_legacy_serialization():
    for raw, model in ((new_occurrence(), ObligationCheck), (guard_contract().checks[0].model_dump(mode="json"), GuardCheck)):
        assert model.model_validate(raw).model_dump(mode="json") == model.model_validate(raw | {"request_aliases": []}).model_dump(mode="json")
        assert "request_aliases" not in model.model_validate(raw).model_dump(mode="json")
