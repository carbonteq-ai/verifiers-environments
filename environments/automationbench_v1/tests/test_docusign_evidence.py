"""Real simulator transitions and retained Luna sends qualify envelope evidence."""

import hashlib
import json
from pathlib import Path

import pytest
from test_notification_evidence import run_operations, zapier

from automationbench.domains.operations.tasks import get_ops_contract_renewal_pipeline_task
from automationbench.tools.zapier.docusign.envelope import (
    docusign_create_envelope_from_template,
    docusign_send_envelope,
    docusign_void_envelope,
)
from automationbench_v1.docusign_evidence import envelope_sends
from automationbench_v1.effect_evidence import world_transitions
from automationbench_v1.effect_index import EffectIndex


def create(status="sent"):
    args = {
        "template_id": "tpl_renewal", "signer_name": "Vendor",
        "signer_email": "contracts@pinnaclesolutions.com", "status": status,
    }
    return zapier(
        "docusign_create_envelope_from_template", args,
        lambda world: docusign_create_envelope_from_template(world, **args),
    )


def effects(source):
    return envelope_sends(EffectIndex(world_transitions(source)))


def send():
    captured_args = {"tool_name": "docusign_send_envelope", "arguments": "{}"}

    def handler(world):
        args = {"envelope_id": world.docusign.envelopes[0].id}
        captured_args["arguments"] = json.dumps(args)
        return docusign_send_envelope(world, **args)

    return "execute_tool", captured_args, handler


def test_created_draft_then_acknowledged_send():
    initial = get_ops_contract_renewal_pipeline_task()["info"]["initial_state"]
    source = run_operations(initial, [
        create("created"),
        send(),
    ])
    sent = effects(source)
    assert len(sent) == 1 and sent[0].status == "qualified"
    assert sent[0].invocation_id == "execution-1"
    assert sent[0].envelope["status"] == "sent"
    assert sent[0].envelope["template_id"] == "tpl_renewal"
    assert sent[0].envelope["completed_date_time"] is None


def test_later_void_does_not_erase_prior_send():
    initial = get_ops_contract_renewal_pipeline_task()["info"]["initial_state"]
    source = run_operations(initial, [
        create(),
        zapier("docusign_void_envelope", {}, lambda world: docusign_void_envelope(
            world, world.docusign.envelopes[0].id, "mistake",
        )),
    ])
    sent = effects(source)
    assert sent[0].status == "qualified" and sent[0].envelope["status"] == "sent"
    assert source["task_evidence"]["final"]["docusign"]["envelopes"][0]["status"] == "voided"


def test_duplicate_send_does_not_prove_new_delivery():
    initial = get_ops_contract_renewal_pipeline_task()["info"]["initial_state"]
    source = run_operations(initial, [
        create(),
        send(),
    ])
    sent = effects(source)
    assert [item.status for item in sent] == ["qualified", "unavailable"]
    assert sent[1].reason == "envelope_new_send_effect_unresolved"


def test_missing_acknowledgement_cannot_qualify_send():
    initial = get_ops_contract_renewal_pipeline_task()["info"]["initial_state"]
    source = run_operations(initial, [create()])
    source["state_write_receipts"] = []
    assert all(item.status == "unavailable" for item in effects(source))


def test_actual_source_hashed_luna_renewal_sends():
    registry = Path("/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/luna-development-policy-contracts.json")
    if not registry.exists():
        pytest.skip("retained development registry unavailable")
    contract = next(case for case in json.loads(registry.read_text())["tasks"]
                    if case["task_name"] == "operations.contract_renewal_pipeline")
    binding = contract["source_binding"]
    raw = Path(binding["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == binding["source_episode_sha256"]
    trace = json.loads(raw)["traces"][0]
    sent = effects({
        "tool_execution_events": trace["tool_execution_events"],
        "state_write_receipts": trace["state_write_receipts"],
    })
    qualified = [item for item in sent if item.status == "qualified"]
    assert len(qualified) == 3
    assert {item.envelope["signers"][0]["email"] for item in qualified} == {
        "contracts@pinnaclesolutions.com", "renewals@greenleaf.com", "billing@brightstar.com",
    }
    assert all(item.envelope["status"] == "sent" for item in qualified)
    assert all(item.envelope["template_id"] == "tpl_renewal" for item in qualified)
