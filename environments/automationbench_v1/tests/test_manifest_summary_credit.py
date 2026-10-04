"""Physical summary penalties through native scoring; no semantic model calls.

Real simulator writes are wrapped in explicitly manufactured SDK/native
envelopes. Controlled certificates test credit admission, not prose accuracy.
"""

import asyncio
import copy
import json

import pytest
import verifiers.v1 as vf
from test_contact_task_manifests import manufactured, update
from test_manifest_guard_assessments import penalties
from test_manifest_summary_assessments import (
    ControlledBackend,
    _manufactured_sdk_for_real_handler_trace,
    evidence,
    summary_batch,
)
from test_summary_policy import configured, decision

from automationbench_v1 import manifest_assessments, manifest_summary_credit
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.loader import load_contract, load_task_contract
from automationbench_v1.manifest_summary_assessments import SUMMARY_ACTION_OUTPUT, SUMMARY_OUTPUT

NAME = "simple.email_sf_contact_assistant_update"


def setup(monkeypatch, *, calls=None, missing_ack=None, states=None, assistant=None):
    _, trace, task = manufactured(
        NAME, calls=calls if calls is not None else [update(NAME)], missing_ack=missing_ack
    )
    _manufactured_sdk_for_real_handler_trace(trace, task, text=assistant)
    from test_external_output_source import material

    check = configured(material(trace, task))
    assert check.assessor is not None
    declaration = load_task_contract(NAME).model_dump(mode="json")
    declaration["revision"] = "development_summary_physical_penalty@1"
    declaration["sources"] = {
        "assistant": {"adapter": "assistant.outputs@1", "kind": "assistant_text"},
        "external": {"adapter": "external.outputs@1", "kind": "authored_text"},
    }
    declaration["checks"] = [check.model_dump(mode="json")]
    declaration["credit"] = [
        {
            "check": check.check_id,
            "policy": "summary_action_negative_once@1",
            "channel": "summary-harm",
        }
    ]
    contract = load_contract(canonical_json(declaration))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    monkeypatch.setattr(manifest_summary_credit, "load_task_contract", lambda _: contract)
    backend = ControlledBackend(check.assessor)

    def parse(_exchange, prepared):
        return tuple(
            decision(prepared, output, state=(states or {}).get(index, "violation"))
            for index, output in enumerate(prepared.outputs)
            if output.text
        )

    monkeypatch.setattr(backend, "parse", parse)
    task.summary_backends = {check.assessor.assessor_id: backend}
    return trace, task, contract, check, backend


def score(trace, task):
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    return tuple(part for part in penalties(trace) if part.channel == "summary-harm")


def planned(trace, task, contract, *, batches=None, prior=None):
    batch = summary_batch(trace)
    source = batch.source
    assert isinstance(source, vf.SourceSnapshot)
    context = vf.CreditPlanningContext(
        source=source.identity,
        current_assessment_runs=(batch.run,),
        prior_assignments=tuple(trace.credit_assignments if prior is None else prior),
    )
    return manifest_summary_credit.plan_summary_credit(
        task, source, (batch,) if batches is None else batches, context, contract
    )


def test_two_bad_fields_one_physical_penalty_and_rescore_reload_once(monkeypatch):
    trace, task, contract, _, backend = setup(monkeypatch)
    scalar = copy.deepcopy(trace.rewards)
    parts = score(trace, task)
    assert len(parts) == 1 and parts[0].value == -1
    assert trace.credit_assignments[-1].request.overlap_policy == "sum"
    assert parts[0].recipient.execution.invocation_id == "execution-0"
    assert parts[0].signal.minimum == -1 and parts[0].signal.maximum == 0
    assert parts[0].signal.direction == "higher"
    action = evidence(summary_batch(trace), SUMMARY_ACTION_OUTPUT)[0]
    assert len(action["findings"]) == 1 and len(action["findings"][0]["group"]["output_keys"]) == 2
    assert not planned(trace, task, contract)
    assert len(score(trace, task)) == 1 and backend.calls == 2
    loaded = vf.Trace.model_validate_json(trace.model_dump_json())
    loaded.state = trace.state
    assert len(score(loaded, task)) == 1
    assert trace.rewards == loaded.rewards == scalar


def test_two_repeated_submissions_are_two_physical_penalties(monkeypatch):
    trace, task, _, _, _ = setup(monkeypatch, calls=[update(NAME), update(NAME)])
    parts = score(trace, task)
    assert len(parts) == 2 and {part.value for part in parts} == {-1}
    assert {part.recipient.execution.invocation_id for part in parts} == {
        "execution-0",
        "execution-1",
    }


def test_known_action_harm_survives_later_missing_ack(monkeypatch):
    trace, task, _, _, _ = setup(monkeypatch, calls=[update(NAME), update(NAME)], missing_ack=1)
    parts = score(trace, task)
    assert len(parts) == 1 and parts[0].recipient.execution.invocation_id == "execution-0"
    aggregate = evidence(summary_batch(trace), SUMMARY_OUTPUT)[0]["evaluation"]
    assert aggregate["compliance"] == 0


def test_assistant_harm_has_no_invented_action_recipient(monkeypatch):
    trace, task, _, _, _ = setup(
        monkeypatch,
        assistant="Skipped a requested update.",
        states={0: "inapplicable", 1: "inapplicable"},
    )
    # Explicitly identify surfaces rather than relying on invented token mapping.
    backend = next(iter(task.summary_backends.values()))
    monkeypatch.setattr(
        backend,
        "parse",
        lambda exchange, prepared: tuple(
            decision(
                prepared,
                output,
                state="violation" if output.surface == "assistant_text" else "inapplicable",
            )
            for output in prepared.outputs
            if output.text
        ),
    )
    assert not score(trace, task)
    assert evidence(summary_batch(trace), SUMMARY_OUTPUT)[0]["evaluation"]["compliance"] == 0


@pytest.mark.parametrize(
    "tamper", ["action-harm", "parent", "aggregate", "missing-exchange", "foreign-view"]
)
def test_current_receipt_parent_or_exchange_tamper_rejected(monkeypatch, tamper):
    trace, task, contract, _, _ = setup(monkeypatch)
    score(trace, task)
    original = summary_batch(trace)
    batch = original.model_copy(deep=True)
    if tamper == "parent":
        batch = batch.model_copy(
            update={
                "assessments": (
                    batch.assessments[0],
                    batch.assessments[1].model_copy(update={"reason": "invented"}),
                )
            }
        )
    elif tamper == "foreign-view":
        view = batch.views[0]
        material = json.loads(view.input_json)
        material["source"]["task_evidence"]["complete"] = False
        replacement = vf.ObservationView.capture(
            material,
            snapshot_id=view.snapshot_id,
            builder_revision=view.builder_revision,
            scope=view.scope,
            subjects=view.subjects,
        )
        batch = batch.model_copy(update={"views": (replacement,)})
    else:
        records = []
        from automationbench_v1.manifest_summary_assessments import SUMMARY_EXCHANGE

        for record in batch.run.execution_evidence:
            if tamper == "missing-exchange" and record.kind == SUMMARY_EXCHANGE:
                continue
            payload = json.loads(record.payload_json)
            if tamper == "action-harm" and record.kind == SUMMARY_ACTION_OUTPUT:
                payload["findings"][0]["harm"] = 0
            if tamper == "aggregate" and record.kind == SUMMARY_OUTPUT:
                payload["evaluation"]["compliance"] = 1
            records.append(
                vf.ExecutionEvidence.capture(
                    record.kind, payload, invocation_id=record.invocation_id
                )
            )
        batch = batch.model_copy(
            update={"run": batch.run.model_copy(update={"execution_evidence": tuple(records)})}
        )
    with pytest.raises(ValueError, match="summary_credit"):
        planned(trace, task, contract, batches=(batch,), prior=())


def test_partial_failed_assignment_valid_contribution_still_consumes(monkeypatch):
    trace, task, contract, _, _ = setup(monkeypatch)
    score(trace, task)
    assignment = trace.credit_assignments[-1]
    for status in ("partial", "failed", "interrupted"):
        previous = assignment.model_copy(update={"status": status})
        assert not planned(trace, task, contract, prior=(previous,))


def test_current_failed_attempt_cannot_reuse_old_positive_parent(monkeypatch):
    trace, task, contract, _, _ = setup(monkeypatch)
    score(trace, task)
    old = summary_batch(trace)
    failed = old.model_copy(update={"run": old.run.model_copy(update={"status": "failed"})})
    assert not planned(trace, task, contract, batches=(failed,), prior=())


def test_projector_rejects_retarget_to_other_real_action(monkeypatch):
    trace, task, contract, _, _ = setup(monkeypatch, calls=[update(NAME), update(NAME)])
    score(trace, task)
    requests = planned(trace, task, contract, prior=())
    assert len(requests) == 2
    request = requests[0][1].model_copy(update={"targets": requests[1][1].targets})
    with pytest.raises(ValueError, match="summary_penalty"):
        asyncio.run(manifest_summary_credit.manifest_summary_penalty(task, request))


def test_lazy_parser_failure_keeps_independent_action_harm(monkeypatch):
    trace, task, _, _, backend = setup(monkeypatch)

    def parse(exchange, prepared):
        yield decision(prepared, prepared.outputs[0], state="violation")
        raise ValueError("controlled malformed peer certificate")

    monkeypatch.setattr(backend, "parse", parse)
    parts = score(trace, task)
    assert len(parts) == 1 and parts[0].value == -1
    evaluation = evidence(summary_batch(trace), SUMMARY_OUTPUT)[0]["evaluation"]
    assert evaluation["decision_errors"] and evaluation["compliance"] == 0


@pytest.mark.parametrize("invalid_first", [True, False])
@pytest.mark.parametrize("fault", ["uncited-resolved", "foreign-output"])
def test_sdk_parser_peer_failure_preserves_native_action_penalty(
    monkeypatch, invalid_first, fault
):
    from test_codex_sdk_summary_backend import Process, backend, decisions, records, stream

    from automationbench_v1.summary_backends import codex_sdk as sdk_module

    trace, task, contract, _, _ = setup(monkeypatch)
    driver = backend()
    declaration = contract.model_dump(mode="json")
    declaration["checks"][0]["assessor"] = driver.identity.model_dump(mode="json")
    contract = load_contract(canonical_json(declaration))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    monkeypatch.setattr(manifest_summary_credit, "load_task_contract", lambda _: contract)
    processes = []

    async def spawn(_path):
        return processes[-1]

    async def controlled_execute(prepared, raw_source, request, context):
        # Installed simulator writes and production SDK parsing are real;
        # these semantic certificates and worker events are controlled fixtures.
        certificates = decisions(prepared, "violation")
        assert len(certificates) == 2
        valid, invalid = certificates
        if fault == "uncited-resolved":
            invalid["state"] = "inapplicable"
            invalid["citations"] = []
        else:
            invalid["output_key"] = "foreign-output"
        ordered = [invalid, valid] if invalid_first else [valid, invalid]
        processes.append(Process(stream(records(prepared, ordered))))
        return await driver.execute(prepared, raw_source, request, context)

    class FixtureBackend:
        identity = driver.identity
        execute = staticmethod(controlled_execute)
        parse = staticmethod(driver.parse)

    fixture = FixtureBackend()
    monkeypatch.setattr(sdk_module, "_spawn", spawn)
    task.summary_backends = {driver.identity.assessor_id: fixture}
    scalar = copy.deepcopy(trace.rewards)
    parts = score(trace, task)
    assert len(parts) == 1 and parts[0].value == -1
    assert parts[0].recipient.execution.invocation_id == "execution-0"
    evaluation = evidence(summary_batch(trace), SUMMARY_OUTPUT)[0]["evaluation"]
    assert evaluation["compliance"] == 0 and evaluation["decision_errors"]
    retained = tuple(trace.credit_assignments)
    restored = vf.Trace.model_validate_json(trace.model_dump_json())
    restored.state = trace.state
    assert len(score(restored, task)) == 1
    assert tuple(restored.credit_assignments) == retained
    assert restored.rewards == scalar


def test_unavailable_public_policy_current_attempt_has_no_penalty(monkeypatch):
    trace, task, contract, _, backend = setup(monkeypatch)
    declaration = contract.model_dump(mode="json")
    declaration["checks"][0]["policy_digest"] = "0" * 64
    changed = load_contract(canonical_json(declaration))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: changed)
    monkeypatch.setattr(manifest_summary_credit, "load_task_contract", lambda _: changed)
    assert not score(trace, task) and backend.calls == 0
    assert all(parent.status == "abstained" for parent in summary_batch(trace).assessments)
    assert not planned(trace, task, changed, prior=())


def test_new_current_failure_never_falls_back_to_old_harm(monkeypatch):
    trace, task, _, _, _ = setup(monkeypatch)
    assert len(score(trace, task)) == 1

    async def fail(task, request, context):
        raise RuntimeError("new current producer failure")

    monkeypatch.setattr(manifest_assessments, "assess_summary", fail)
    count = len(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert summary_batch(trace).run.status == "failed"
    assert len(trace.credit_assignments) == count
    assert len([part for part in penalties(trace) if part.channel == "summary-harm"]) == 1


@pytest.mark.parametrize("value", [True, False])
def test_copied_numeric_parent_bool_does_not_authenticate(monkeypatch, value):
    trace, task, contract, _, _ = setup(monkeypatch)
    score(trace, task)
    batch = summary_batch(trace)
    forged = batch.model_copy(
        update={
            "assessments": (
                batch.assessments[0],
                batch.assessments[1].model_copy(update={"value": value}),
            )
        }
    )
    with pytest.raises(ValueError, match="summary_credit_parent_mismatch"):
        planned(trace, task, contract, batches=(forged,), prior=())


def test_batch_configuration_must_match_current_planned_run(monkeypatch):
    trace, task, contract, _, _ = setup(monkeypatch)
    score(trace, task)
    batch = summary_batch(trace)
    assert isinstance(batch.source, vf.SourceSnapshot)
    different = batch.run.model_copy(
        update={"configuration_json": '{"different":"current controller plan"}'}
    )
    context = vf.CreditPlanningContext(
        source=batch.source.identity, current_assessment_runs=(different,)
    )
    with pytest.raises(ValueError, match="summary_credit_current_targets_mismatch"):
        manifest_summary_credit.plan_summary_credit(task, batch.source, (batch,), context, contract)


@pytest.mark.parametrize("status", ["partial", "complete", "failed", "interrupted"])
@pytest.mark.parametrize("field", ["rubric_revision", "snapshot_id", "producer_id"])
def test_multitarget_history_cannot_change_static_metadata(monkeypatch, status, field):
    trace, task, _, _, _ = setup(monkeypatch)
    score(trace, task)
    terminal = summary_batch(trace)
    partial = next(
        batch for batch in trace.assessment_batches
        if batch.run.run_id == terminal.run.run_id and batch.run.status == "partial"
    )
    assert isinstance(terminal.source, vf.SourceSnapshot)
    context = vf.CreditPlanningContext(
        source=terminal.source.identity,
        current_assessment_runs=(terminal.run,),
        prior_assignments=tuple(trace.credit_assignments),
    )
    # Another registered producer is still a forbidden change within this run.
    changed = (
        manifest_assessments.OBLIGATION_PRODUCER if field == "producer_id" else "changed"
    )
    advanced = terminal.model_copy(update={
        "run": terminal.run.model_copy(update={field: changed, "status": status}),
    })
    with pytest.raises(ValueError, match="manifest_assessment_history_conflict"):
        task.plan_credit(terminal.source, (partial, advanced), context)


@pytest.mark.parametrize("mutation", ["reordered", "dropped", "changed", "undeclared"])
def test_multitarget_history_rejects_invalid_finding_advancement(monkeypatch, mutation):
    trace, task, _, _, _ = setup(monkeypatch)
    score(trace, task)
    terminal = summary_batch(trace)
    partial = next(
        batch for batch in trace.assessment_batches
        if batch.run.run_id == terminal.run.run_id and batch.run.status == "partial"
    )
    assert isinstance(terminal.source, vf.SourceSnapshot)
    context = vf.CreditPlanningContext(
        source=terminal.source.identity, current_assessment_runs=(terminal.run,),
        prior_assignments=tuple(trace.credit_assignments),
    )
    records = terminal.assessments
    if mutation == "reordered":
        records = tuple(reversed(records))
    elif mutation == "dropped":
        records = records[1:]
    elif mutation == "changed":
        records = (records[0].model_copy(update={"reason": "changed"}), *records[1:])
    else:
        extra = records[-1].model_copy(update={
            "assessment_id": "undeclared-assessment",
            "signal": records[-1].signal.model_copy(update={"signal_id": "undeclared"}),
        })
        records = (*records, extra)
    advanced = terminal.model_copy(update={"assessments": records})
    with pytest.raises(ValueError, match="history_conflict|unexpected or duplicate reply target"):
        task.plan_credit(terminal.source, (partial, advanced), context)


@pytest.mark.parametrize("status", ["failed", "interrupted"])
def test_multitarget_failure_can_append_output_and_update_reason(monkeypatch, status):
    trace, task, _, _, _ = setup(monkeypatch)
    score(trace, task)
    terminal = summary_batch(trace)
    partial = next(
        batch for batch in trace.assessment_batches
        if batch.run.run_id == terminal.run.run_id and batch.run.status == "partial"
    )
    assert isinstance(terminal.source, vf.SourceSnapshot)
    context = vf.CreditPlanningContext(
        source=terminal.source.identity, current_assessment_runs=(terminal.run,),
        prior_assignments=tuple(trace.credit_assignments),
    )
    # Only the lifecycle reducer is under test; artifact bytes remain owned by
    # their transport and these explicit references make no capture claim.
    artifact = vf.ArtifactRef(uri="fixture://failure-log", digest="f" * 64)
    failed = partial.model_copy(update={"run": partial.run.model_copy(update={
        "status": status, "reason": "controlled terminal failure",
        "output_evidence": (*partial.run.output_evidence, artifact),
    })})
    assert not task.plan_credit(terminal.source, (partial, failed), context)
    with_output = partial.model_copy(update={"run": partial.run.model_copy(update={
        "output_evidence": (*partial.run.output_evidence, artifact),
    })})
    dropped = failed.model_copy(update={"run": failed.run.model_copy(update={
        "output_evidence": partial.run.output_evidence,
    })})
    with pytest.raises(ValueError, match="manifest_assessment_history_conflict"):
        task.plan_credit(terminal.source, (with_output, dropped), context)


@pytest.mark.parametrize("status", ["complete", "failed", "interrupted"])
@pytest.mark.parametrize("mutation", ["reason", "output_evidence"])
def test_terminal_history_is_immutable_but_exact_duplicate_is_valid(monkeypatch, status, mutation):
    trace, task, _, _, _ = setup(monkeypatch)
    score(trace, task)
    actual = summary_batch(trace)
    # Explicit lifecycle-reducer fixture. Actual failed-after-yield execution
    # is qualified separately; copied statuses here make no producer-run claim.
    terminal = actual.model_copy(update={"run": actual.run.model_copy(update={
        "status": status, "reason": None if status == "complete" else "controlled failure",
    })})
    assert isinstance(terminal.source, vf.SourceSnapshot)
    context = vf.CreditPlanningContext(
        source=terminal.source.identity, current_assessment_runs=(terminal.run,),
        prior_assignments=tuple(trace.credit_assignments),
    )
    assert not task.plan_credit(terminal.source, (terminal, terminal), context)
    change = (
        {"reason": "changed after terminal"} if mutation == "reason" else
        {"output_evidence": (*terminal.run.output_evidence,
                             vf.ArtifactRef(uri="fixture://late-artifact", digest="e" * 64))}
    )
    changed = terminal.model_copy(update={"run": terminal.run.model_copy(update=change)})
    with pytest.raises(ValueError, match="manifest_assessment_history_regression"):
        task.plan_credit(terminal.source, (terminal, changed), context)
