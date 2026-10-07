"""Bounded public-policy declarations; actual Luna replay is separate from fixtures."""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import penalties, terminal_records
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.gmail.message import gmail_send_email
from automationbench.tools.zapier.salesforce.record import salesforce_update_record
from automationbench_v1.contracts import (
    InitialCollectionSource,
    NotificationEffectSource,
    ObligationCheck,
    load_task_contract,
)
from automationbench_v1.contracts.credit import select_credit
from automationbench_v1.contracts.engine import evaluate_contract
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import AutomationBenchData, AutomationBenchTaskConfig
from automationbench_v1.tools import AutomationBenchState

SELECTION = Path('/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate/cross-category-selection.json')


def recorded(name):
    if not SELECTION.exists():
        pytest.skip("development trace selection unavailable")
    entry = next(item for item in json.loads(SELECTION.read_bytes())["tasks"] if item["task_name"] == name)
    path = Path(entry["source_episode_path"])
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["source_episode_sha256"]
    episode = vf.WireEpisode.model_validate_json(raw)
    trace = cast(Any, episode.traces[0])
    data = AutomationBenchData.model_validate(trace.task.data.model_dump(mode="json"))
    return path, raw, episode, trace, data


@pytest.mark.parametrize("name,signal", [
    ("sales.multi_hop_lookup", "sales.requested_stage"),
    ("sales.docusign_void_resend", "sales.negotiated_amount"),
    ("simple.email_airtable_customer_welcome", "simple.customer_recipient_delivery"),
])
def test_actual_recorded_component_manifest_retains_findings_and_credit_without_scalar_changes(name, signal):
    path, raw, episode, trace, data = recorded(name)
    trace.state = AutomationBenchState(world=trace.info["automationbench"]["end_state"], initial_state=data.initial_state,
                                      assertions=data.assertions, artifacts=dict(trace.state.artifacts))
    task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    assert trace.rewards == scalar
    findings = [item for item in terminal_records(trace) if item.signal.signal_id == signal]
    assert len(findings) == 1 and findings[0].value == 1
    contributions = penalties(trace)
    if name.startswith("sales."):
        assert len(contributions) == 1 and contributions[0].value == 1
        assert contributions[0].recipient.kind == "execution"
    else:
        # Recipient-only delivery is factual evidence, not useful welcome credit.
        assert not contributions
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = cast(Any, loaded.traces[0])
    replay.state = trace.state
    assert replay.assessment_batches == trace.assessment_batches
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors
    assert len(penalties(replay)) == len(contributions)
    assert path.read_bytes() == raw


def sales_material(*, operations=(), prompt_changed=False, extra_target=False, name="sales.multi_hop_lookup"):
    _, _, _, _, data = recorded(name)
    initial = copy.deepcopy(data.initial_state)
    if extra_target:
        initial["salesforce"]["opportunities"].append({
            **initial["salesforce"]["opportunities"][0], "id": "other", "name": "Other deal",
        })
    material = run_operations(initial, list(operations))
    material["task_evidence"]["initial"] = initial
    material["task_evidence"]["prompt"] = data.model_dump(mode="json")["prompt"]
    if prompt_changed:
        material["task_evidence"]["prompt"][1]["content"] = "Change the public request"
    return material


def won(*, target="006xx000004MER1", stage="Closed Won"):
    args = {"object_type": "Opportunity", "record_id": target, "fields": {"StageName": stage}}
    return zapier("salesforce_update_record", args, lambda world: salesforce_update_record(world, **args))


def amount(value=175000, target="006xx000004APX1"):
    args = {"object_type": "Opportunity", "record_id": target, "fields": {"Amount": value}}
    return zapier("salesforce_update_record", args, lambda world: salesforce_update_record(world, **args))


def test_negotiated_amount_rejects_wrong_target_changed_policy_and_duplicate_progress():
    name = "sales.docusign_void_resend"
    declared = load_task_contract(name)
    for operations, expected, credits in [
        ([], 0, 0), ([amount(), amount()], 1, 1),
        ([amount(target="other")], 0, 0),
        ([amount(), amount(100000), amount()], 1, 0),
    ]:
        result = evaluate_contract(sales_material(name=name, operations=operations, extra_target=True), declared)
        assert result.results[0].value == expected
        assert len(select_credit(declared, result)) == credits
    result = evaluate_contract(sales_material(name=name, operations=[amount()], prompt_changed=True), declared)
    assert result.results[0].value is None and not select_credit(declared, result)


def test_sales_declared_transition_needs_verified_effect_and_duplicate_noop_does_not_multiply():
    declared = load_task_contract("sales.multi_hop_lookup")
    missing = evaluate_contract(sales_material(), declared)
    assert missing.results[0].value == 0 and not select_credit(declared, missing)
    result = evaluate_contract(sales_material(operations=[won(), won()]), declared)
    assert result.results[0].value == 1
    selected = select_credit(declared, result)
    assert len(selected) == 1 and selected[0].occurrence == "execution-0"


def test_sales_public_authority_mismatch_cannot_mint_credit():
    declared = load_task_contract("sales.multi_hop_lookup")
    result = evaluate_contract(sales_material(operations=[won()], prompt_changed=True), declared)
    assert result.results[0].value is None and not select_credit(declared, result)


def test_sales_wrong_record_does_not_satisfy_the_declared_target():
    declared = load_task_contract("sales.multi_hop_lookup")
    result = evaluate_contract(sales_material(operations=[won(target="other")], extra_target=True), declared)
    assert result.results[0].value == 0 and not select_credit(declared, result)


def test_sales_damage_and_restore_retains_outcome_without_repeated_progress_credit():
    declared = load_task_contract("sales.multi_hop_lookup")
    result = evaluate_contract(sales_material(operations=[won(), won(stage="Prospecting"), won()]), declared)
    assert result.results[0].value == 1 and not select_credit(declared, result)


def test_unrelated_customer_message_has_no_welcome_action_credit():
    # This known false positive for purpose checking remains explicit. No hidden
    # assertion or lexical surrogate defines what counts as a welcome message.
    from automationbench_v1.contracts.effects import EffectEvidence
    from automationbench_v1.contracts.notification_effects import capture_notification_effects
    from automationbench_v1.contracts.obligations import (
        evaluate_obligations,
        select_obligation_credit,
    )
    from automationbench_v1.contracts.populations import capture_population

    _, _, _, _, data = recorded("simple.email_airtable_customer_welcome")
    args = {"to": "lucas.grant@pinnacle.example.com", "subject": "Onboarding cancelled", "body": "Your account was rejected."}
    material = run_operations(copy.deepcopy(data.initial_state), [
        zapier("gmail_send_email", args, lambda world: gmail_send_email(world, **args))])
    material["task_evidence"]["prompt"] = data.model_dump(mode="json")["prompt"]
    declared = load_task_contract(data.task_name)
    incoming, sends, check = declared.sources["incoming"], declared.sources["sends"], declared.checks[0]
    assert isinstance(incoming, InitialCollectionSource)
    assert isinstance(sends, NotificationEffectSource) and isinstance(check, ObligationCheck)
    population = capture_population(material, incoming)
    effects: EffectEvidence = capture_notification_effects(material, sends)
    evaluation = evaluate_obligations(material, check, {"incoming": population}, effects,
        effect_source=sends, population_sources={"incoming": incoming})
    assert evaluation.findings[0].value == 1  # delivery only; purpose remains unqualified
    assert select_obligation_credit(evaluation)  # mechanism could allocate if explicitly selected
    assert not declared.credit  # installed policy deliberately does not select it
