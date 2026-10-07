"""Physical-action membership with controlled certificates, without model calls.

Simulator handlers are genuine; native envelopes are labelled manufactured
fixtures. Semantic certificates test admission/grouping, not prose accuracy.
"""

import copy
import json

import pytest
import verifiers.v1 as vf
from test_contact_task_manifests import manufactured, update
from test_external_output_source import actual
from test_gmail_zendesk_external_outputs import send
from test_summary_policy import configured, decision
from verifiers.v1.assessment_source import capture_trace_source

from automationbench_v1.contracts.authored_outputs import (
    AuthoredOutputSource,
    capture_authored_outputs,
)
from automationbench_v1.contracts.external_outputs import (
    ExternalOutputSource,
    capture_external_outputs,
)
from automationbench_v1.contracts.summary_policy import (
    evaluate_summary_policy,
    prepare_summary_context,
)
from automationbench_v1.manifest_summary_actions import plan_summary_actions, reduce_summary_actions

NAME = "simple.email_sf_contact_assistant_update"
SOURCES = {"assistant_source": AuthoredOutputSource(), "external_source": ExternalOutputSource()}


def seal(trace, task):
    source = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    raw = json.loads(source.source_json)
    safe = {
        "task_evidence": raw["task_evidence"],
        "tool_execution_events": raw.get("tool_execution_events", []),
        "state_write_receipts": raw.get("state_write_receipts", []),
    }
    return source, safe, configured(safe)


def fixture(calls=None, *, missing_ack=None):
    _, trace, task = manufactured(
        NAME, calls=calls if calls is not None else [update(NAME)], missing_ack=missing_ack
    )
    return seal(trace, task)


def evaluated(source, raw, check, states=None, *, omit=(), modify=None, extra=()):
    assistant = capture_authored_outputs(raw, SOURCES["assistant_source"])
    external = capture_external_outputs(raw, SOURCES["external_source"], native_source=source)
    context = prepare_summary_context(
        raw, check, assistant, external, native_source=source, **SOURCES
    )
    decisions = []
    for index, output in enumerate(context.outputs):
        if index in omit:
            continue
        item = decision(context, output, state=(states or {}).get(index, "compliant"))
        decisions.append(modify(item, index) if modify else item)
    return evaluate_summary_policy(
        raw,
        check,
        assistant,
        external,
        native_source=source,
        decisions=(*decisions, *extra),
        producer=check.assessor,
        full_output_ids=tuple(output.output_key for output in context.outputs),
        **SOURCES,
    )


def reduced(inputs, evaluation, **kwargs):
    source, raw, check = inputs
    return reduce_summary_actions(source, raw, check, evaluation, **SOURCES, **kwargs)


def invocation(finding):
    execution = finding.group.recipient.execution
    assert execution is not None
    return execution.invocation_id


def test_many_violating_fields_are_one_original_physical_action_and_keep_members():
    inputs = fixture()
    plan = plan_summary_actions(*inputs, **SOURCES)
    assert len(plan.groups) == 1 and len(plan.groups[0].output_keys) == 2
    evaluation = evaluated(*inputs, {0: "violation", 1: "violation"})
    result = reduced(inputs, evaluation, plan=plan)
    assert len(result.findings) == 1 and result.findings[0].harm == 1
    assert len(result.findings[0].members) == 2
    recipient = result.findings[0].group.recipient
    assert recipient.execution is not None and recipient.execution.invocation_id == "execution-0"
    assert result.findings[0].group.action_key == recipient.execution.occurrence_id
    assert recipient.snapshot_id == inputs[0].snapshot_id
    assert not result.unassigned_violations


def test_repeated_real_submissions_are_distinct_actions_even_if_second_is_noop():
    inputs = fixture([update(NAME), update(NAME)])
    evaluation = evaluated(*inputs, {index: "violation" for index in range(4)})
    result = reduced(inputs, evaluation)
    assert [finding.harm for finding in result.findings] == [1, 1]
    assert len({finding.group.action_key for finding in result.findings}) == 2
    assert {invocation(finding) for finding in result.findings} == {
        "execution-0",
        "execution-1",
    }


def test_local_clean_action_survives_unrelated_global_inventory_gap():
    inputs = fixture()
    evaluation = evaluated(*inputs)
    assert evaluation.context is not None and not evaluation.context.invocation_closed
    assert evaluation.compliance is None  # Native fixture has no original model-call inventory.
    result = reduced(inputs, evaluation)
    assert result.findings[0].group.local_closed and result.findings[0].harm == 0


@pytest.mark.parametrize("state,expected", [("violation", 1), ("compliant", None)])
def test_partial_local_footprint_keeps_known_harm_but_cannot_assert_clean(state, expected):
    inputs = fixture([send(file="unobserved-attachment.txt")])
    evaluation = evaluated(*inputs, {0: state})
    result = reduced(inputs, evaluation)
    assert len(result.findings) == 1 and not result.findings[0].group.local_closed
    assert result.findings[0].harm == expected


def test_gmail_signature_headers_and_labels_share_one_send_recipient():
    inputs = fixture(
        [
            send(
                signature="Signature prose",
                from_name="Sender prose",
                to="Name <x@example.com>",
                label_ids="Custom prose",
            )
        ]
    )
    result = reduced(inputs, evaluated(*inputs, {index: "violation" for index in range(5)}))
    assert len(result.findings) == 1 and result.findings[0].harm == 1
    context = evaluated(*inputs).context
    assert context is not None
    fields = {json.loads(output.fact_json)["field"] for output in context.outputs}
    assert fields == {"subject", "body_plain", "to.0", "from_name", "label_ids.1"}


@pytest.mark.parametrize("bad", ["omitted", "invalid-citation", "duplicate", "retained-abstained"])
def test_invalid_peer_never_reconstructed_clean_but_independent_violation_survives(bad):
    inputs = fixture()
    kwargs = {}
    if bad == "omitted":
        kwargs["omit"] = (1,)
    elif bad == "invalid-citation":
        kwargs["modify"] = lambda item, index: (
            item.model_copy(update={"citations": ()}) if index == 1 else item
        )
    elif bad == "duplicate":
        original = evaluated(*inputs)
        kwargs["extra"] = (original.findings[1].decision,)
    for first_state, expected in (("compliant", None), ("violation", 1)):
        evaluation = evaluated(
            *inputs,
            {0: first_state, 1: "abstained" if bad == "retained-abstained" else "compliant"},
            **kwargs,
        )
        result = reduced(inputs, evaluation)
        assert result.findings[0].harm == expected
        assert result.findings[0].members[1].state == "abstained"


def test_missing_retained_finding_is_unknown_and_not_recreated_from_clean_scope():
    inputs = fixture()
    evaluation = evaluated(*inputs).model_copy(update={"findings": evaluated(*inputs).findings[:1]})
    result = reduced(inputs, evaluation)
    assert result.findings[0].harm is None and result.validation_errors


def test_unrelated_invalid_action_member_does_not_poison_locally_clean_group():
    inputs = fixture([update(NAME), update(NAME)])
    evaluation = evaluated(*inputs, omit=(2,))
    result = reduced(inputs, evaluation)
    assert [finding.harm for finding in result.findings] == [0, None]


@pytest.mark.parametrize("forgery", ["finding-state", "producer", "driver-coverage"])
def test_retained_verdict_cannot_replace_admissible_semantic_certificate(forgery):
    inputs = fixture()
    evaluation = evaluated(*inputs, {0: "violation"})
    if forgery == "finding-state":
        evaluation = evaluated(*inputs)
        evaluation = evaluation.model_copy(
            update={
                "findings": (
                    evaluation.findings[0].model_copy(update={"state": "violation"}),
                    evaluation.findings[1],
                )
            }
        )
    elif forgery == "producer":
        assert evaluation.producer is not None
        evaluation = evaluation.model_copy(
            update={"producer": evaluation.producer.model_copy(update={"revision": "wrong"})}
        )
    else:
        evaluation = evaluation.model_copy(update={"full_output_ids": ()})
    result = reduced(inputs, evaluation)
    assert result.findings[0].harm is None
    assert result.validation_errors


def test_judge_context_citations_cannot_retarget_output_to_another_execution():
    inputs = fixture([update(NAME), update(NAME)])
    evaluation = evaluated(
        *inputs,
        {0: "violation"},
        modify=lambda item, index: (
            item.model_copy(update={"invocation_ids": ("execution-1",)}) if index == 0 else item
        ),
    )
    result = reduced(inputs, evaluation)
    assert [(invocation(finding), finding.harm) for finding in result.findings] == [
        ("execution-0", 1),
        ("execution-1", 0),
    ]
    forged = evaluated(
        *inputs,
        {0: "violation"},
        modify=lambda item, index: (
            item.model_copy(update={"invocation_ids": ("judge-invocation",)})
            if index == 0
            else item
        ),
    )
    assert reduced(inputs, forged).findings[0].harm is None


def test_missing_later_ack_does_not_erase_earlier_original_action_harm():
    inputs = fixture([update(NAME), update(NAME)], missing_ack=1)
    result = reduced(inputs, evaluated(*inputs, {0: "violation"}))
    assert len(result.findings) == 1 and result.findings[0].harm == 1
    assert invocation(result.findings[0]) == "execution-0"


def test_stale_source_retargeted_group_or_projection_is_rejected():
    inputs = fixture([update(NAME), update(NAME)])
    plan = plan_summary_actions(*inputs, **SOURCES)
    evaluation = evaluated(*inputs)
    changed = copy.deepcopy(inputs[1])
    changed["task_evidence"]["final"]["salesforce"]["contacts"][0]["assistant_name"] = "Forged"
    with pytest.raises(ValueError, match="executor_source_mismatch"):
        reduce_summary_actions(inputs[0], changed, inputs[2], evaluation, **SOURCES)
    forged = plan.model_copy(
        update={
            "groups": (
                plan.groups[0].model_copy(
                    update={
                        "recipient": plan.groups[1].recipient,
                        "action_key": plan.groups[1].action_key,
                    }
                ),
                plan.groups[1],
            )
        }
    )
    with pytest.raises(ValueError, match="plan_source_or_membership_changed"):
        reduced(inputs, evaluation, plan=forged)
    with pytest.raises(ValueError, match="evaluation_context_changed"):
        reduced(fixture(), evaluation)


def test_copied_strict_bool_and_execution_identity_metadata_cannot_launder():
    inputs = fixture()
    plan = plan_summary_actions(*inputs, **SOURCES)
    forged = plan.model_copy(
        update={"groups": (plan.groups[0].model_copy(update={"local_closed": 1}),)}
    )
    with pytest.raises(ValueError):
        reduced(inputs, evaluated(*inputs), plan=forged)
    reference = inputs[0].executions[0].model_copy(update={"invocation_id": b"execution-0"})
    source = inputs[0].model_copy(update={"executions": (reference,)})
    with pytest.raises(ValueError):
        plan_summary_actions(source, inputs[1], inputs[2], **SOURCES)


def test_sdk_assistant_violation_has_no_action_recipient_and_original_archive_stays_intact():
    path, raw_bytes, envelope, _, trace, task = actual()
    inputs = seal(trace, task)
    evaluation = evaluated(*inputs, {0: "violation"})
    assert evaluation.context is not None and evaluation.context.outputs[0].inventory == "assistant"
    result = reduced(inputs, evaluation)
    assert len(result.unassigned_violations) == 1
    assert result.unassigned_violations[0].output_key == evaluation.findings[0].output_key
    assert len(result.findings) == 1 and result.findings[0].harm == 0
    assert trace.nodes == []
    assert (
        path.read_bytes() == raw_bytes
        and (path.parent / "trace-0-artifacts.json").read_bytes() == envelope
    )
    restored = vf.SourceSnapshot.model_validate_json(inputs[0].model_dump_json())
    assert reduced((restored, inputs[1], inputs[2]), evaluation) == result


@pytest.mark.parametrize("change", ["changed", "missing", "not-text", "empty", "missing-prompt"])
def test_fresh_sealed_missing_or_changed_policy_preserves_action_membership_not_context(change):
    inputs = fixture()
    original = plan_summary_actions(*inputs, **SOURCES)
    assert original.context_digest is not None
    payload = json.loads(inputs[0].source_json)
    policy = payload["task_evidence"]["prompt"][0]
    if change == "changed":
        policy["content"] += " Different policy."
    elif change == "missing":
        del policy["content"]
    elif change == "not-text":
        policy["content"] = {"unqualified": "policy"}
    elif change == "empty":
        policy["content"] = ""
    else:
        del payload["task_evidence"]["prompt"]
    # A genuinely fresh sealed counterfactual source; raw policy drift alone
    # must not change physical-action ownership or invent semantic authority.
    native = vf.SourceSnapshot.capture(
        payload,
        episode_id=inputs[0].episode_id,
        trace_ids=inputs[0].trace_ids,
        nodes=inputs[0].nodes,
        executions=inputs[0].executions,
    )
    raw = {
        key: payload.get(key, [])
        for key in ("task_evidence", "tool_execution_events", "state_write_receipts")
    }
    current = plan_summary_actions(native, raw, inputs[2], **SOURCES)
    assert current.context_digest is None and current.source_digest != original.source_digest
    assert current.check_digest == original.check_digest
    assert [(g.action_key, g.output_keys, g.local_closed) for g in current.groups] == [
        (g.action_key, g.output_keys, g.local_closed) for g in original.groups
    ]
    assert all(group.recipient.snapshot_id == native.snapshot_id for group in current.groups)
    assert [g.recipient.execution for g in current.groups] == [
        g.recipient.execution for g in original.groups
    ]
    with pytest.raises((ValueError, TypeError), match="summary_policy_source_"):
        reduce_summary_actions(native, raw, inputs[2], evaluated(*inputs), plan=current, **SOURCES)


def test_policy_absence_does_not_hide_unsealed_projection_or_context_capture_error(monkeypatch):
    from automationbench_v1 import manifest_summary_actions as actions

    inputs = fixture()
    raw = copy.deepcopy(inputs[1])
    del raw["task_evidence"]["prompt"]
    with pytest.raises(ValueError, match="executor_source_mismatch"):
        plan_summary_actions(inputs[0], raw, inputs[2], **SOURCES)

    def failed_capture(*_args, **_kwargs):
        raise ValueError("unrelated_capture_integrity_failure")

    monkeypatch.setattr(actions, "prepare_summary_context", failed_capture)
    with pytest.raises(ValueError, match="unrelated_capture_integrity_failure"):
        plan_summary_actions(*inputs, **SOURCES)
