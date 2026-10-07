"""Occurrence witnesses survive incomplete history; absence needs closed scope."""

import copy
import hashlib
import json
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path
from typing import Literal

import pytest
from test_asana_evidence import task_and_section
from test_notification_evidence import run_operations, zapier

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.effects import EffectSource, capture_effects


def initial():
    return {"asana": {"actions": {"create_task": [], "add_task_to_section": []}}}


def spec(kind: Literal["create_task", "add_task_to_section"] = "create_task"):
    return EffectSource(adapter="asana.actions@1", kind=kind)


def captured(operations=None):
    return run_operations(initial(), task_and_section() if operations is None else operations)


def test_creation_and_section_have_separate_qualified_witnesses():
    source = captured()
    created = capture_effects(source, spec())
    section = capture_effects(source, spec("add_task_to_section"))
    assert created.complete and section.complete
    assert len(created.effects) == len(section.effects) == 1
    assert created.effects[0].status == section.effects[0].status == "qualified"
    assert created.effects[0].invocation_id == "execution-0"
    assert section.effects[0].invocation_id == "execution-1"
    assert section.effects[0].params_json is not None
    assert json.loads(section.effects[0].params_json)["task_id"] == created.effects[0].effect_id
    assert created.effects[0].effect_id != section.effects[0].effect_id
    assert created.selector_digest != section.selector_digest


def test_explicit_empty_selected_collection_with_qualified_other_operation():
    source = captured(task_and_section()[:1])
    evidence = capture_effects(source, spec("add_task_to_section"))
    assert evidence.complete and evidence.effects == ()


@pytest.mark.parametrize("missing", ["service", "actions", "collection"])
def test_missing_initial_structure_is_not_schema_qualified_empty(missing):
    source = captured(task_and_section()[:1])
    if missing == "service":
        del source["task_evidence"]["initial"]["asana"]
    elif missing == "actions":
        del source["task_evidence"]["initial"]["asana"]["actions"]
    else:
        del source["task_evidence"]["initial"]["asana"]["actions"]["create_task"]
    evidence = capture_effects(source, spec())
    assert not evidence.complete
    # A qualified occurrence has its own explicit before/after evidence.
    assert evidence.effects[0].status == "qualified"


def test_first_native_append_qualifies_without_claiming_missing_initial_scope_empty():
    source = run_operations({}, task_and_section())
    evidence = capture_effects(source, spec())
    assert not evidence.complete
    assert evidence.effects[0].status == "qualified"
    assert evidence.effects[0].effect_id is not None
    assert source["task_evidence"]["initial"]["asana"]["actions"] == {}
    assert evidence.reason == "asana_selected_collection_missing"


def test_missing_later_ack_preserves_earlier_effect():
    source = captured()
    source["state_write_receipts"] = source["state_write_receipts"][:1]
    evidence = capture_effects(source, spec())
    assert not evidence.complete
    assert [item.status for item in evidence.effects] == ["qualified", "unavailable"]
    assert evidence.effects[0].invocation_id == "execution-0"


def test_missing_own_ack_never_qualifies_effect():
    source = captured(task_and_section()[:1])
    source["state_write_receipts"] = []
    evidence = capture_effects(source, spec())
    assert not evidence.complete
    assert evidence.effects[0].status == "unavailable"


def test_repair_does_not_erase_earlier_action_record_witness():
    def remove(world):
        world.asana.actions["create_task"] = []
        return {"success": True}

    source = captured([
        *task_and_section()[:1], zapier("asana_delete_task", {}, remove),
    ])
    evidence = capture_effects(source, spec())
    assert source["task_evidence"]["final"]["asana"]["actions"]["create_task"] == []
    assert evidence.effects[0].status == "qualified"
    assert evidence.effects[0].effect_id is not None
    assert not evidence.complete  # Delete semantics have not been qualified.


@pytest.mark.parametrize("name,args", [
    ("foreign_tool", {}),
    ("api_fetch", {"method": "POST", "url": "/asana/api/1.0/tasks"}),
])
def test_unsupported_unchanged_call_cannot_close_simulator_effect_scope(name, args):
    source = captured([(name, args, lambda world: {"success": True})])
    evidence = capture_effects(source, spec())
    assert not evidence.complete
    assert evidence.effects[0].reason == "asana_operation_scope_unsupported"


def test_foreign_reporter_never_gets_fabricated_tool_server_origin():
    source = captured(task_and_section()[:1])
    source["tool_execution_events"][0]["source"] = "interceptor"
    evidence = capture_effects(source, spec())
    assert not evidence.complete and evidence.effects == ()
    assert evidence.reason == "unsupported_execution_origin"


def test_unmatched_ack_prevents_complete_inventory_without_erasing_known_effect():
    source = captured(task_and_section()[:1])
    source["state_write_receipts"].append({
        "write_id": "unobserved", "expected_revision": 1, "applied_revision": 2,
        "conflict": False,
    })
    evidence = capture_effects(source, spec())
    assert not evidence.complete
    assert evidence.reason == "effect_invocation_ack_inventory_mismatch"
    assert evidence.effects[0].status == "qualified"


def test_missing_prefix_and_unreconciled_terminal_prevent_completeness():
    source = captured()
    source["tool_execution_events"] = source["tool_execution_events"][1:]
    source["state_write_receipts"] = source["state_write_receipts"][1:]
    evidence = capture_effects(source, spec("add_task_to_section"))
    assert not evidence.complete
    assert evidence.effects[0].status == "qualified"
    source = captured()
    source["task_evidence"]["final"]["asana"]["actions"]["create_task"] = []
    assert not capture_effects(source, spec()).complete


def test_empty_event_list_alone_is_not_complete_execution_accounting():
    source = captured([])
    evidence = capture_effects(source, spec())
    assert not evidence.complete and evidence.effects == ()
    assert evidence.reason == "effect_history_empty_occurrence_inventory"
    del source["tool_execution_events"]
    assert capture_effects(source, spec()).reason == "execution_inventory_missing"


def test_source_selector_binding_and_immutable_json_round_trip():
    source = captured()
    before = copy.deepcopy(source)
    evidence = capture_effects(source, spec())
    assert source == before
    assert json.loads(canonical_json(asdict(evidence)))["source_digest"] == evidence.source_digest
    for target, attribute, value in (
        (evidence, "complete", False),
        (evidence.effects[0], "params_json", "{}"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(target, attribute, value)
    source["task_evidence"]["complete"] = False
    changed = capture_effects(source, spec())
    assert changed.source_digest != evidence.source_digest
    assert not changed.complete and changed.effects[0].status == "qualified"


def test_distinct_identical_calls_are_not_deduplicated():
    source = captured([*task_and_section()[:1], *task_and_section()[:1]])
    evidence = capture_effects(source, spec())
    assert evidence.complete and len(evidence.effects) == 2
    assert len({item.effect_id for item in evidence.effects}) == 2
    assert len({item.invocation_id for item in evidence.effects}) == 2


def test_forged_returned_record_identity_does_not_qualify():
    source = captured(task_and_section()[:1])
    event = source["tool_execution_events"][0]
    receipt = json.loads(event["receipt_json"])
    envelope = json.loads(receipt["evidence_json"][0])
    envelope["action"]["result_json"] = canonical_json({
        "success": True, "results": [{"id": "wrong"}],
    })
    receipt["evidence_json"] = [canonical_json(envelope)]
    event["receipt_json"] = canonical_json(receipt)
    evidence = capture_effects(source, spec())
    assert not evidence.complete and evidence.effects[0].status == "unavailable"


def test_agreeing_but_nonunit_revision_jump_does_not_qualify_occurrence():
    source = captured(task_and_section()[:1])
    event = source["tool_execution_events"][0]
    receipt = json.loads(event["receipt_json"])
    receipt["state_write_revision"] = 2
    event["receipt_json"] = canonical_json(receipt)
    source["state_write_receipts"][0]["applied_revision"] = 2
    evidence = capture_effects(source, spec())
    assert not evidence.complete and evidence.effects[0].status == "unavailable"
    assert evidence.effects[0].reason == "asana_occurrence_revision_unqualified"


@pytest.mark.parametrize("missing", ["service", "actions"])
def test_native_first_append_does_not_hydrate_missing_before_capture(missing):
    source = run_operations({}, task_and_section()[:1])
    event = source["tool_execution_events"][0]
    receipt = json.loads(event["receipt_json"])
    envelope = json.loads(receipt["evidence_json"][0])
    action = envelope["action"]
    before = json.loads(envelope["snapshots"][action["before_digest"]])
    if missing == "service":
        del before["asana"]
    else:
        del before["asana"]["actions"]
    text = canonical_json(before)
    digest = hashlib.sha256(text.encode()).hexdigest()
    envelope["snapshots"][digest] = text
    action["before_digest"] = digest
    receipt["evidence_json"] = [canonical_json(envelope)]
    event["receipt_json"] = canonical_json(receipt)
    evidence = capture_effects(source, spec())
    assert not evidence.complete and evidence.effects[0].status == "unavailable"


@pytest.mark.parametrize("kind", ["create_task", "add_task_to_section"])
def test_actual_sha_bound_luna_access_retains_first_native_append_witnesses(kind):
    index_path = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/"
        "luna-development-policy-contracts.json"
    )
    if not index_path.exists():
        pytest.skip("retained development source index unavailable; replay gate not run")
    case = next(
        item for item in json.loads(index_path.read_text())["tasks"]
        if item["task_name"] == "operations.access_request_validation"
    )
    binding = case["source_binding"]
    episode_path = Path(binding["source_episode_path"])
    if not episode_path.exists():
        pytest.skip("retained development episode unavailable; replay gate not run")
    raw = episode_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == binding["source_episode_sha256"]
    episode = json.loads(raw)
    trace = episode["traces"][0]
    source = {
        "tool_execution_events": trace["tool_execution_events"],
        "state_write_receipts": trace["state_write_receipts"],
        "task_evidence": {
            "initial": episode["task"]["data"]["initial_state"],
            "final": trace["info"]["automationbench"]["end_state"],
            "complete": trace["is_completed"],
        },
    }
    selected = EffectSource.model_validate({"adapter": "asana.actions@1", "kind": kind})
    evidence = capture_effects(source, selected)
    qualified = [item for item in evidence.effects if item.status == "qualified"]
    assert len(qualified) == 3
    assert len({item.effect_id for item in qualified}) == 3
    assert all(item.params_json is not None and item.origin == "tool_server" for item in qualified)
    # This source also contains unsupported reads and Gmail operations. Its
    # positive witnesses are accepted; broader closed-scope claims remain open.
    assert not evidence.complete
