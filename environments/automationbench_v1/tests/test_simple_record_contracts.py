"""Public request/schema checks and ten immutable real development replays."""

import hashlib
import json
from pathlib import Path

import pytest

from automationbench.domains.simple import tasks
from automationbench.schema.salesforce.opportunity import Opportunity
from automationbench_v1.simple_record_contracts import CONTRACTS, evaluate_simple_record_update


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda item: item.task_name)
def test_contract_matches_exact_public_request_and_declared_native_field(contract):
    factory = getattr(tasks, "get_" + contract.task_name.replace(".", "_"))
    public = factory()
    users = [item["content"] for item in public["prompt"] if item["role"] == "user"]
    assert users == [contract.user_request]
    assert all(field.name in Opportunity.model_fields for field in contract.desired_fields)
    assert all(field.name in Opportunity.model_fields for field in contract.baseline_requirements)
    assert len(contract.desired_fields) == 1


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda item: item.task_name)
def test_actual_sha_bound_luna_opportunity_update_uses_shared_strategy(contract):
    registry = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-review-coverage.json"
    )
    if not registry.exists():
        pytest.skip("retained development coverage index unavailable")
    entry = next(
        item
        for item in json.loads(registry.read_bytes())["entries"]
        if item["task_name"] == contract.task_name
    )
    path = Path(entry["source_episode_path"])
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["source_episode_sha256"]
    episode = json.loads(raw)
    trace = episode["traces"][0]
    data = episode["task"]["data"]
    source = {
        "tool_execution_events": trace["tool_execution_events"],
        "state_write_receipts": trace["state_write_receipts"],
        "task_evidence": {
            "task_name": contract.task_name,
            "prompt": data["prompt"],
            "initial": data["initial_state"],
            "final": trace["info"]["automationbench"]["end_state"],
            "complete": True,
        },
    }
    findings = evaluate_simple_record_update(source)
    assert findings[0].value == 1 and findings[0].occurrence is not None
    assert findings[1].value == 1
    assert path.read_bytes() == raw
