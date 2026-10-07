"""Real native source/retention with controlled semantic certificates, no model."""

import asyncio
import copy
import json
from typing import cast

import pytest
import verifiers.v1 as vf
from test_external_output_source import actual, material
from test_summary_policy import configured, decision

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.engine import compile_contract
from automationbench_v1.contracts.loader import load_contract, load_task_contract
from automationbench_v1.manifest_summary_assessments import (
    SUMMARY_EXCHANGE,
    SUMMARY_OUTPUT,
    SUMMARY_PRODUCER,
    SUMMARY_REQUEST,
    SummaryBackendExchange,
)


class ControlledBackend:
    """Driver fixture qualifies source and exchange transport, not prose accuracy."""

    def __init__(
        self,
        identity,
        *,
        fail_parse=False,
        fail_execute=False,
        journal=True,
        producer=SUMMARY_PRODUCER,
        request_kind=SUMMARY_REQUEST,
    ):
        self.identity = identity
        self.fail_parse = fail_parse
        self.calls = 0
        self.fail_execute = fail_execute
        self.journal = journal
        self.producer = producer
        self.request_kind = request_kind

    async def execute(self, prepared, raw_source, request, context):
        self.calls += 1
        assert raw_source["task_evidence"] and request.run.producer_id == self.producer
        exchange = SummaryBackendExchange(
            request_text=canonical_json(
                {"messages": [{"role": "user", "content": prepared.model_dump_json()}]}
            ),
            response_text='{"controlled":"all compliant"}',
            provider_identity="controlled-semantic-driver",
            usage_json='{"test_only":true}',
            full_output_ids=tuple(output.output_key for output in prepared.outputs),
        )
        if self.journal:
            context.record_evidence(
                self.request_kind,
                {
                    "context_digest": prepared.context_digest,
                    "producer": self.identity.model_dump(mode="json"),
                    "request_text": exchange.request_text,
                    "full_output_ids": list(exchange.full_output_ids),
                },
                invocation_id=request.run.invocation_id,
            )
        await asyncio.sleep(0)
        if self.fail_execute:
            raise TimeoutError("controlled backend timeout")
        return exchange

    def parse(self, exchange, prepared):
        if self.fail_parse:
            raise ValueError("controlled parser failure")
        return tuple(decision(prepared, output) for output in prepared.outputs)


def setup(monkeypatch):
    _, _, _, _, trace, task = actual()
    trace.assessment_batches = []
    trace.credit_assignments = []
    check = configured(material(trace, task))
    raw = load_task_contract(task.data.task_name).model_dump(mode="json")
    raw["revision"] = "development_summary_transport@1"
    raw["sources"] = {
        "assistant": {"adapter": "assistant.outputs@1", "kind": "assistant_text"},
        "external": {"adapter": "external.outputs@1", "kind": "authored_text"},
    }
    raw["checks"] = [check.model_dump(mode="json")]
    raw["credit"] = []
    contract = load_contract(canonical_json(raw))
    assert compile_contract(contract) == (check.check_id,)
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    return trace, task, contract, check


def summary_batch(trace):
    return next(
        batch
        for batch in reversed(trace.assessment_batches)
        if batch.run.producer_id == SUMMARY_PRODUCER
    )


def evidence(batch, kind):
    return [
        json.loads(record.payload_json)
        for record in batch.run.execution_evidence
        if record.kind == kind
    ]


def setup_no_clarification(monkeypatch):
    from automationbench_v1.contracts.no_clarification import NoClarificationCheck

    trace, task, contract, original = setup(monkeypatch)
    check = NoClarificationCheck.model_validate(
        {
            **original.model_dump(mode="json"),
            "operator": "no_clarification@1",
            "check_id": "clarification",
            "signal_id": "clarification-compliance",
        }
    )
    raw = contract.model_dump(mode="json")
    raw["checks"] = [check.model_dump(mode="json")]
    contract = load_contract(canonical_json(raw))
    assert compile_contract(contract) == (check.check_id,)
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    return trace, task, check


@pytest.mark.parametrize("fault", [None, "parse", "execute", "wrong_journal"])
def test_native_no_clarification_uses_independent_current_exchange(monkeypatch, fault):
    from automationbench_v1.manifest_no_clarification_assessments import (
        NO_CLARIFICATION_EXCHANGE,
        NO_CLARIFICATION_OUTPUT,
        NO_CLARIFICATION_PRODUCER,
        NO_CLARIFICATION_REQUEST,
    )

    trace, task, check = setup_no_clarification(monkeypatch)
    assert check.assessor is not None
    backend = ControlledBackend(
        check.assessor,
        fail_parse=fault == "parse",
        fail_execute=fault == "execute",
        producer=NO_CLARIFICATION_PRODUCER,
        request_kind=SUMMARY_REQUEST if fault == "wrong_journal" else NO_CLARIFICATION_REQUEST,
    )
    task.no_clarification_backends = {check.assessor.assessor_id: backend}
    asyncio.run(task.score(trace))
    batch = trace.assessment_batches[-1]
    assert batch.run.producer_id == NO_CLARIFICATION_PRODUCER
    assert batch.run.status == "complete" and backend.calls == 1
    assert len(batch.assessments) == 1
    assert batch.assessments[0].value == (1 if fault is None else None)
    assert evidence(batch, NO_CLARIFICATION_OUTPUT)
    assert evidence(batch, NO_CLARIFICATION_EXCHANGE)
    assert not evidence(batch, SUMMARY_OUTPUT)
    assert not trace.credit_assignments
    assert trace.reward == 1  # Legacy scalar remains independent of this guard.
    restored = vf.WireTrace.model_validate_json(trace.model_dump_json())
    assert restored.assessment_batches[-1] == batch


def test_native_no_clarification_without_backend_cannot_borrow_summary_result(monkeypatch):
    trace, task, check = setup_no_clarification(monkeypatch)
    assert check.assessor is not None
    backend = ControlledBackend(check.assessor)
    task.summary_backends = {check.assessor.assessor_id: backend}
    asyncio.run(task.score(trace))
    assert backend.calls == 0
    assert trace.assessment_batches[-1].assessments[0].value is None
    assert trace.reward == 1


def test_native_no_clarification_retains_known_request_before_lazy_parser_fault(monkeypatch):
    from automationbench_v1.manifest_no_clarification_assessments import (
        NO_CLARIFICATION_OUTPUT,
        NO_CLARIFICATION_PRODUCER,
        NO_CLARIFICATION_REQUEST,
    )

    class PartialBackend(ControlledBackend):
        def parse(self, exchange, prepared):
            yield decision(prepared, prepared.outputs[0], "violation")
            raise ValueError("controlled malformed peer after known request")

    trace, task, check = setup_no_clarification(monkeypatch)
    assert check.assessor is not None
    backend = PartialBackend(
        check.assessor,
        producer=NO_CLARIFICATION_PRODUCER,
        request_kind=NO_CLARIFICATION_REQUEST,
    )
    task.no_clarification_backends = {check.assessor.assessor_id: backend}
    asyncio.run(task.score(trace))
    batch = trace.assessment_batches[-1]
    assert batch.assessments[0].status == "valid" and batch.assessments[0].value == 0
    result = evidence(batch, NO_CLARIFICATION_OUTPUT)[0]["evaluation"]
    assert result["status"] == "violation" and result["decision_errors"]
    assert trace.reward == 1 and not trace.credit_assignments
    saved = vf.WireTrace.model_validate_json(trace.model_dump_json())
    assert saved.assessment_batches[-1] == batch
    # A WireTrace retains evidence, not the live simulator runtime object.
    saved.state = trace.state
    asyncio.run(task.score(cast(vf.Trace, saved)))
    assert saved.assessment_batches[-1].assessments[0].value == 0
    assert saved.reward == 1 and not saved.credit_assignments


@pytest.mark.parametrize("fault", [None, "harm", "parse", "execute"])
def test_no_clarification_outcome_does_not_block_original_contact_credit(monkeypatch, fault):
    from automationbench_v1.contracts.no_clarification import NoClarificationCheck
    from automationbench_v1.manifest_no_clarification_assessments import (
        NO_CLARIFICATION_PRODUCER,
        NO_CLARIFICATION_REQUEST,
    )

    _, _, _, _, trace, task = actual()
    trace.assessment_batches = []
    trace.credit_assignments = []
    raw = load_task_contract(task.data.task_name).model_dump(mode="json")
    check = NoClarificationCheck.model_validate(
        {
            **configured(material(trace, task)).model_dump(mode="json"),
            "operator": "no_clarification@1",
            "check_id": "clarification",
            "signal_id": "clarification-compliance",
        }
    )
    raw["revision"] = "development_mixed_clarification_transport@1"
    raw["sources"].update(
        {
            "assistant": {"adapter": "assistant.outputs@1", "kind": "assistant_text"},
            "external": {"adapter": "external.outputs@1", "kind": "authored_text"},
        }
    )
    raw["checks"].append(check.model_dump(mode="json"))
    contract = load_contract(canonical_json(raw))
    compile_contract(contract)
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    assert check.assessor is not None
    backend = ControlledBackend(
        check.assessor,
        producer=NO_CLARIFICATION_PRODUCER,
        request_kind=NO_CLARIFICATION_REQUEST,
        fail_parse=fault == "parse",
        fail_execute=fault == "execute",
    )
    if fault == "harm":
        monkeypatch.setattr(
            backend,
            "parse",
            lambda _exchange, prepared: tuple(
                decision(prepared, output, "violation") for output in prepared.outputs
            ),
        )
    task.no_clarification_backends = {check.assessor.assessor_id: backend}
    asyncio.run(task.score(trace))
    assert not trace.credit_errors and not trace.assessment_errors
    contributions = [
        item
        for batch in trace.credit_assignments
        if batch.status == "complete"
        for item in batch.contributions
    ]
    assert len(contributions) == 2 and all(item.value == 1 for item in contributions)
    assert trace.reward == 1
    consumed = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert not trace.credit_errors and tuple(trace.credit_assignments) == consumed


def test_summary_bridge_forwards_one_executor_snapshot(monkeypatch):
    from automationbench_v1 import manifest_summary_assessments as bridge

    trace, task, _, check = setup(monkeypatch)
    assert check.assessor is not None
    task.summary_backends = {check.assessor.assessor_id: ControlledBackend(check.assessor)}
    captured = []

    def forwarding(original):
        def wrapped(*args, **kwargs):
            snapshot = kwargs.get("native_source")
            assert isinstance(snapshot, vf.SourceSnapshot)
            captured.append(snapshot)
            return original(*args, **kwargs)

        return wrapped

    for name in ("capture_external_outputs", "prepare_summary_context", "evaluate_summary_policy"):
        monkeypatch.setattr(bridge, name, forwarding(getattr(bridge, name)))
    asyncio.run(task.score(trace))
    batch = summary_batch(trace)
    assert batch.assessments[0].value == 1 and trace.reward == 1
    assert len(captured) == 3
    assert all(snapshot is captured[0] for snapshot in captured)
    assert captured[0].snapshot_id == batch.run.snapshot_id


def test_native_summary_guard_retains_exchange_and_current_failed_parser(monkeypatch):
    trace, task, _, check = setup(monkeypatch)
    assert check.assessor is not None
    backend = ControlledBackend(check.assessor)
    task.summary_backends = {check.assessor.assessor_id: backend}
    asyncio.run(task.score(trace))
    first = summary_batch(trace)
    assert first.run.status == "complete" and first.assessments[0].value == 1
    assert backend.calls == 1 and trace.reward == 1
    receipts = evidence(first, SUMMARY_EXCHANGE)
    assert receipts[0]["exchange"]["response_text"] == '{"controlled":"all compliant"}'
    output = evidence(first, SUMMARY_OUTPUT)[0]["evaluation"]
    assert len(output["findings"]) == 3 and len(output["context"]["relations"]) == 2
    assert len(output["context"]["invocations"]) == 7
    retained = vf.WireTrace.model_validate_json(trace.model_dump_json())
    assert summary_batch(retained).run.execution_evidence == first.run.execution_evidence
    backend.fail_parse = True
    asyncio.run(task.score(trace))
    current = summary_batch(trace)
    assert current.run.run_id != first.run.run_id
    assert current.assessments[0].status == "abstained" and current.assessments[0].value is None
    assert evidence(current, SUMMARY_EXCHANGE)[0]["exchange"]["response_text"]
    assert evidence(current, SUMMARY_OUTPUT)[0]["backend_error"]
    assert trace.reward == 1 and first.assessments[0].value == 1


def test_summary_backend_configuration_mismatch_prevents_execution(monkeypatch):
    trace, task, _, check = setup(monkeypatch)
    assert check.assessor is not None
    changed = check.assessor.model_copy(update={"parser_revision": "different"})
    backend = ControlledBackend(changed)
    task.summary_backends = {check.assessor.assessor_id: backend}
    asyncio.run(task.score(trace))
    batch = summary_batch(trace)
    assert backend.calls == 0 and batch.assessments[0].status == "abstained"
    assert evidence(batch, SUMMARY_EXCHANGE)[0]["error"]


@pytest.mark.parametrize("failure", ["timeout", "missing-journal"])
def test_summary_unavailable_backend_never_establishes_compliance(monkeypatch, failure):
    trace, task, _, check = setup(monkeypatch)
    assert check.assessor is not None
    backend = ControlledBackend(
        check.assessor, fail_execute=failure == "timeout", journal=failure != "missing-journal"
    )
    task.summary_backends = {check.assessor.assessor_id: backend}
    asyncio.run(task.score(trace))
    batch = summary_batch(trace)
    assert batch.assessments[0].status == "abstained" and batch.assessments[0].value is None
    assert trace.reward == 1
    if failure == "timeout":
        assert evidence(batch, SUMMARY_REQUEST)[0]["request_text"]
    else:
        assert evidence(batch, SUMMARY_EXCHANGE)[0]["exchange"]["response_text"]


def test_summary_run_configuration_cannot_add_backend_parameters(monkeypatch):
    trace, task, _, check = setup(monkeypatch)
    assert check.assessor is not None
    backend = ControlledBackend(check.assessor)
    task.summary_backends = {check.assessor.assessor_id: backend}
    original = type(task).assessment_requests

    def extra_parameter(self, source):
        requests = original(self, source)
        result = []
        for name, request in requests:
            if request.run.producer_id == SUMMARY_PRODUCER:
                configuration = json.loads(request.run.configuration_json)
                configuration["model_override"] = "unapproved"
                run = request.run.model_copy(
                    update={"configuration_json": canonical_json(configuration)}
                )
                request = request.model_copy(update={"run": run})
            result.append((name, request))
        return result

    monkeypatch.setattr(type(task), "assessment_requests", extra_parameter)
    asyncio.run(task.score(trace))
    assert summary_batch(trace).run.status == "failed" and backend.calls == 0


@pytest.mark.parametrize("bad", [None, "bad", {"state": "compliant"}])
def test_summary_malformed_parser_return_abstains_with_raw_exchange_retained(monkeypatch, bad):
    trace, task, _, check = setup(monkeypatch)
    assert check.assessor is not None
    backend = ControlledBackend(check.assessor)
    monkeypatch.setattr(backend, "parse", lambda _exchange, _prepared: bad)
    task.summary_backends = {check.assessor.assessor_id: backend}
    asyncio.run(task.score(trace))
    batch = summary_batch(trace)
    assert batch.run.status == "complete" and batch.assessments[0].status == "abstained"
    assert evidence(batch, SUMMARY_EXCHANGE)[0]["exchange"]["response_text"]


def test_native_partial_parser_preserves_known_violation_and_errors(monkeypatch):
    trace, task, _, check = setup(monkeypatch)
    assert check.assessor is not None
    backend = ControlledBackend(check.assessor)

    def interrupted(_exchange, prepared):
        yield decision(prepared, prepared.outputs[0], state="violation")
        raise RuntimeError("controlled interrupted decision stream")

    monkeypatch.setattr(backend, "parse", interrupted)
    task.summary_backends = {check.assessor.assessor_id: backend}
    asyncio.run(task.score(trace))
    batch = summary_batch(trace)
    assert batch.run.status == "complete" and batch.assessments[0].value == 0
    output = evidence(batch, SUMMARY_OUTPUT)[0]["evaluation"]
    assert output["decision_errors"] and output["findings"][0]["state"] == "violation"


@pytest.mark.parametrize(
    "summary_state", ["compliant", "violation", "parse-failure", "assessment-failure"]
)
def test_summary_coexists_with_original_contact_credit_without_remint(monkeypatch, summary_state):
    """Controlled verdicts exercise credit composition, not semantic accuracy."""
    from test_manifest_guard_assessments import penalties

    path, raw_bytes, _, _, trace, task = actual()
    trace.assessment_batches = []
    trace.credit_assignments = []
    scalar = copy.deepcopy(trace.rewards)
    check = configured(material(trace, task))
    assert check.assessor is not None
    original = load_task_contract(task.data.task_name)
    declaration = original.model_dump(mode="json")
    declaration["revision"] = "development_summary_with_contact_credit@1"
    declaration["sources"].update(
        {
            "assistant": {"adapter": "assistant.outputs@1", "kind": "assistant_text"},
            "external": {"adapter": "external.outputs@1", "kind": "authored_text"},
        }
    )
    declaration["checks"].append(check.model_dump(mode="json"))
    contract = load_contract(canonical_json(declaration))
    assert contract.credit == original.credit and contract.bindings == original.bindings
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    backend = ControlledBackend(check.assessor, fail_parse=summary_state == "parse-failure")
    if summary_state == "violation":
        monkeypatch.setattr(
            backend,
            "parse",
            lambda _exchange, prepared: tuple(
                decision(prepared, output, state="violation") for output in prepared.outputs
            ),
        )
    if summary_state == "assessment-failure":

        async def failed_assessment(*_args):
            raise RuntimeError("controlled summary assessment failure")

        monkeypatch.setattr(manifest_assessments, "assess_summary", failed_assessment)
    task.summary_backends = {check.assessor.assessor_id: backend}
    asyncio.run(task.score(trace))
    assert not trace.credit_errors
    if summary_state == "assessment-failure":
        assert summary_batch(trace).run.status == "failed"
        assert not summary_batch(trace).assessments
    else:
        assert not trace.assessment_errors
        expected = None if summary_state == "parse-failure" else int(summary_state == "compliant")
        assert summary_batch(trace).assessments[0].value == expected
    contributions = penalties(trace)
    assert {item.channel for item in contributions} == {"goal", "original-message-read"}
    assert len(contributions) == 2 and all(item.value == 1 for item in contributions)
    assert {item.recipient.execution.invocation_id for item in contributions} == {
        "eb45e8e2c5c648c1bce3fdb9994f3c29",
        "8baf7cd9ff6549b49fd1f565a59ad93a",
    }
    consumed = tuple(trace.credit_assignments)
    asyncio.run(task.score(trace))
    assert not trace.credit_errors and tuple(trace.credit_assignments) == consumed
    replay = cast(vf.Trace, vf.WireTrace.model_validate_json(trace.model_dump_json()))
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.credit_errors and tuple(replay.credit_assignments) == consumed
    assert trace.rewards == replay.rewards == scalar
    assert path.read_bytes() == raw_bytes


@pytest.mark.parametrize("change", ["wrong-source", "credit", "final-policy"])
def test_summary_manifest_rejects_unsupported_source_credit_or_policy(monkeypatch, change):
    _, _, contract, _ = setup(monkeypatch)
    raw = copy.deepcopy(contract.model_dump(mode="json"))
    if change == "wrong-source":
        raw["checks"][0]["source"] = "external"
    elif change == "final-policy":
        raw["checks"][0]["policy_path"] = ["task_evidence", "final", "instructions"]
    else:
        raw["credit"] = [{"check": "summary", "channel": "harm", "policy": "per_effect_negative@1"}]
    with pytest.raises(ValueError):
        load_contract(canonical_json(raw))


FORBIDDEN_SUMMARY = "My work summary: I skipped Bob."
CONTACT_TASK = "simple.email_sf_contact_assistant_update"


def _mixed_summary_contract(monkeypatch, trace, task, *, semantic=True):
    """Keep every installed public check and credit rule, adding only the guard."""
    original = load_task_contract(task.data.task_name)
    check = configured(material(trace, task))
    if not semantic:
        check = check.model_copy(update={"assessor": None})
    declaration = original.model_dump(mode="json")
    declaration["revision"] = "development_summary_negative_controls@1"
    declaration["sources"].update(
        {
            "assistant": {"adapter": "assistant.outputs@1", "kind": "assistant_text"},
            "external": {"adapter": "external.outputs@1", "kind": "authored_text"},
        }
    )
    declaration["checks"].append(check.model_dump(mode="json"))
    contract = load_contract(canonical_json(declaration))
    assert contract.bindings == original.bindings and contract.credit == original.credit
    assert contract.checks[:-1] == original.checks
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    if semantic:
        assert check.assessor is not None
        backend = ControlledBackend(check.assessor)

        def parse(_exchange, prepared):
            # Deliberately controlled semantic certificates. This exact fixture
            # sentence is not a production prose detector or accuracy test.
            return tuple(
                decision(
                    prepared,
                    output,
                    state=("violation" if output.text == FORBIDDEN_SUMMARY else "inapplicable"),
                )
                for output in prepared.outputs
                if output.text
            )

        monkeypatch.setattr(backend, "parse", parse)
        task.summary_backends = {check.assessor.assessor_id: backend}
    return check


def _set_sdk_fixture(trace, payload):
    """Install explicitly counterfactual SDK bytes and matching retained info."""
    trace.info["codex_sdk"] = copy.deepcopy(payload)
    trace.state.artifacts["codex_sdk/events.json"] = canonical_json(payload).encode()


def _replace_actual_assistant_text(trace, text):
    payload = json.loads(trace.state.artifacts["codex_sdk/events.json"])
    events = []
    for record in payload["events"]:
        event = record.get("event", {})
        params = event.get("params", {})
        # Replace the completed authoritative text and turn summary together.
        # Remove old streaming/response copies rather than relabeling verdicts.
        if event.get("method") in {"item/agentMessage/delta", "rawResponse/completed"}:
            continue
        item = params.get("item", {})
        if item.get("type") == "agentMessage":
            item["text"] = text if event.get("method") == "item/completed" else ""
        for item in params.get("turn", {}).get("items", []):
            if item.get("type") == "agentMessage":
                item["text"] = text
        events.append(record)
    payload["events"] = events
    _set_sdk_fixture(trace, payload)


def _manufactured_sdk_for_real_handler_trace(trace, task, *, text=None):
    """Manufactured SDK envelope; real simulator captures supply calls/results.

    This fixture proves mixed native assessment behavior, not an SDK rollout or
    production parser. It retains no old model responses/token usage claims.
    """
    from automationbench_v1.contracts.invocation_inventory import capture_invocation_inventory

    _, _, _, _, archived, _ = actual()
    template = json.loads(archived.state.artifacts["codex_sdk/events.json"])
    original = template["events"]
    completed = next(
        record
        for record in original
        if record.get("event", {}).get("method") == "item/completed"
        and record["event"]["params"].get("item", {}).get("type") == "mcpToolCall"
    )
    started = next(
        record
        for record in original
        if record.get("event", {}).get("method") == "item/started"
        and record["event"]["params"].get("item", {}).get("type") == "mcpToolCall"
    )
    tail = [
        copy.deepcopy(record)
        for record in original
        if record.get("kind") == "finished"
        or record.get("event", {}).get("method") == "turn/completed"
    ]
    events = [
        copy.deepcopy(record)
        for record in original
        if record.get("kind") not in {"event", "finished"}
        or record.get("event", {}).get("method") == "turn/started"
    ]
    inventory = capture_invocation_inventory(material(trace, task))
    for ordinal, entry in enumerate(inventory.entries):
        # For a missing ACK, use only the already retained native terminal call
        # and result to construct the counterfactual SDK event. Do not fill an
        # admitted inventory entry or invent persistence acknowledgement.
        receipt = next(
            json.loads(event.receipt_json)
            for event in trace.tool_execution_events
            if event.source == "tool_server"
            and event.phase == "returned"
            and event.invocation_id == entry.invocation_id
        )
        native_result = json.loads(receipt["result_json"])
        native_arguments = json.loads(receipt["arguments_json"])["kwargs"]
        for base, phase in ((started, "started"), (completed, "completed")):
            record = copy.deepcopy(base)
            item = record["event"]["params"]["item"]
            item.update(
                id=f"manufactured-call-{ordinal}",
                tool=receipt["tool_name"],
                arguments=native_arguments,
            )
            item["result"] = (
                None
                if phase == "started"
                else {
                    "content": [
                        {
                            "type": "text",
                            "text": native_result
                            if isinstance(native_result, str)
                            else canonical_json(native_result),
                        }
                    ],
                    "structuredContent": {"result": native_result},
                }
            )
            events.append(record)
    for record in tail:
        turn = record.get("event", {}).get("params", {}).get("turn")
        if turn is not None:
            turn["items"] = []
    if text is not None:
        record = copy.deepcopy(completed)
        record["event"]["params"]["item"] = {
            "id": "manufactured-assistant-output",
            "type": "agentMessage",
            "text": text,
        }
        events.append(record)
    template["events"] = events + tail
    _set_sdk_fixture(trace, template)


def _mixed_values(trace):
    from test_manifest_guard_assessments import terminal_records

    signals = {"simple.requested_state", "simple.original_introduction_returned", "excluded-prose"}
    result = {}
    for item in terminal_records(trace):
        if item.signal.signal_id in signals:
            result[item.signal.signal_id] = item.value
    return result


def _score_and_replay_once(trace, task):
    from test_manifest_guard_assessments import penalties

    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    values = _mixed_values(trace)
    credits = tuple(trace.credit_assignments)
    contributions = penalties(trace)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    assert _mixed_values(trace) == values and tuple(trace.credit_assignments) == credits
    replay = cast(vf.Trace, vf.WireTrace.model_validate_json(trace.model_dump_json()))
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors
    assert _mixed_values(replay) == values and tuple(replay.credit_assignments) == credits
    assert trace.rewards == replay.rewards == scalar
    return values, contributions


def test_actual_contact_actions_with_counterfactual_forbidden_assistant_summary(monkeypatch):
    path, raw, envelope, _, trace, task = actual()
    original_events = tuple(trace.tool_execution_events)
    _replace_actual_assistant_text(trace, FORBIDDEN_SUMMARY)
    _mixed_summary_contract(monkeypatch, trace, task)
    values, contributions = _score_and_replay_once(trace, task)
    assert values == {
        "simple.requested_state": 1,
        "simple.original_introduction_returned": 1,
        "excluded-prose": 0,
    }
    assert {part.channel for part in contributions} == {"goal", "original-message-read"}
    assert {part.recipient.execution.invocation_id for part in contributions} == {
        "eb45e8e2c5c648c1bce3fdb9994f3c29",
        "8baf7cd9ff6549b49fd1f565a59ad93a",
    }
    assert tuple(trace.tool_execution_events) == original_events
    assert (
        path.read_bytes() == raw
        and (path.parent / "trace-0-artifacts.json").read_bytes() == envelope
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "external-repaired",
        "wrong-email",
        "wrong-contact",
        "missing-read",
        "damaged-terminal",
        "silence",
        "missing-ack",
        "harm-plus-gap",
    ],
)
def test_mixed_contact_native_counterexamples_keep_independent_goal_read_and_summary(
    monkeypatch, scenario
):
    from test_contact_assistant_read_manifest import read
    from test_contact_task_manifests import manufactured, update

    requested = update(CONTACT_TASK)
    calls = [read(), requested]
    missing_ack = None
    if scenario == "external-repaired":
        calls = [
            read(),
            update(CONTACT_TASK, fields={"assistant_name": FORBIDDEN_SUMMARY}),
            requested,
        ]
    elif scenario == "wrong-email":
        calls = [
            read(),
            update(
                CONTACT_TASK,
                fields={"assistant_name": "Kevin Torres", "assistant_email": "wrong@example.com"},
            ),
        ]
    elif scenario == "wrong-contact":
        calls = [read(), update(CONTACT_TASK, identity="nonexistent-contact")]
    elif scenario == "missing-read":
        calls = [requested]
    elif scenario == "damaged-terminal":
        calls.append(update(CONTACT_TASK, fields={"assistant_email": "damaged@example.com"}))
    elif scenario == "silence":
        # A real read supplies the acknowledged schema hydration boundary. The
        # sparse public initial state alone cannot prove an empty invocation
        # inventory equals a fully hydrated simulator world.
        calls = [read()]
    elif scenario == "missing-ack":
        missing_ack = 0
    else:
        calls = [
            read(),
            update(CONTACT_TASK, fields={"assistant_name": FORBIDDEN_SUMMARY}),
            requested,
        ]
        missing_ack = 2
    _, trace, task = manufactured(CONTACT_TASK, calls=calls, missing_ack=missing_ack)
    _manufactured_sdk_for_real_handler_trace(trace, task)
    _mixed_summary_contract(monkeypatch, trace, task, semantic=scenario != "silence")
    values, contributions = _score_and_replay_once(trace, task)
    state = values["simple.requested_state"]
    read_value = values["simple.original_introduction_returned"]
    guard = values["excluded-prose"]
    channels = {part.channel for part in contributions}
    if scenario == "external-repaired":
        assert state == read_value == 1 and guard == 0
        assert channels == {"goal", "original-message-read"}
        assert (
            next(
                part for part in contributions if part.channel == "goal"
            ).recipient.execution.invocation_id
            == "execution-2"
        )
    elif scenario in {"wrong-email", "wrong-contact", "damaged-terminal"}:
        assert state == 0 and read_value == 1
        assert channels == {"original-message-read"}
        assert guard == (None if scenario == "wrong-contact" else 1)
    elif scenario == "missing-read":
        assert state == 1 and read_value != 1 and guard == 1
        assert channels == {"goal"}
    elif scenario == "silence":
        assert state == 0 and read_value == 1 and guard == 1
        assert channels == {"original-message-read"}
        output = evidence(summary_batch(trace), SUMMARY_OUTPUT)[0]["evaluation"]
        assert output["basis"] == "empty_inventory"
    elif scenario == "missing-ack":
        assert state == 1 and read_value is None and guard is None
        assert not contributions
    else:
        assert state == read_value == 1 and guard == 0
        assert channels == {"original-message-read"}


def _action_publication_fixture(monkeypatch, *, policy_change=None):
    """Execute only assessment publication; negative-credit hooks are separate."""
    from verifiers.v1.assessment_source import capture_trace_source

    path, raw_bytes, envelope, _, trace, task = actual()
    check = _mixed_summary_contract(monkeypatch, trace, task)
    original = load_task_contract(task.data.task_name)
    declaration = manifest_assessments.load_task_contract(task.data.task_name).model_dump(
        mode="json"
    )
    declaration["credit"].append(
        {
            "check": check.check_id,
            "policy": "summary_action_negative_once@1",
            "channel": "summary-harm",
        }
    )
    if policy_change == "wrong-check-digest":
        declaration["checks"][-1]["policy_digest"] = "0" * 64
    contract = load_contract(canonical_json(declaration))
    assert contract.credit[:-1] == original.credit and contract.bindings == original.bindings
    assert contract.checks[:-1] == original.checks
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    assert check.assessor is not None
    backend = ControlledBackend(check.assessor)
    monkeypatch.setattr(
        backend,
        "parse",
        lambda _exchange, prepared: tuple(
            decision(
                prepared,
                output,
                state="violation" if output.inventory == "external" else "compliant",
            )
            for output in prepared.outputs
        ),
    )
    task.summary_backends = {check.assessor.assessor_id: backend}
    source = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    if policy_change in {"changed-public-prompt", "missing-policy"}:
        payload = json.loads(source.source_json)
        policy = payload["task_evidence"]["prompt"][0]
        if policy_change == "changed-public-prompt":
            policy["content"] += " Changed public policy."
        else:
            del policy["content"]
        # The executor receives a fresh, internally valid counterfactual source;
        # no prepared view is substituted beneath an unchanged source identity.
        source = vf.SourceSnapshot.capture(
            payload,
            episode_id=source.episode_id,
            trace_ids=source.trace_ids,
            nodes=source.nodes,
            executions=source.executions,
        )
    planned = [
        request
        for _, request in task.assessment_requests(source)
        if request.run.producer_id == SUMMARY_PRODUCER
    ]
    assert len(planned) == 1
    return path, raw_bytes, envelope, trace, task, backend, source, planned[0]


def _execute_summary_publication(task, source, request):
    from verifiers.v1.assessment_runtime import execute_assessment

    from automationbench_v1.manifest_summary_assessments import assess_summary

    async def execute():
        return await execute_assessment(
            lambda request, context: assess_summary(task, request, context), request, source, []
        )

    batch = asyncio.run(execute())
    assert batch.run.status == "complete", batch.run.reason
    assert len(batch.assessments) == len(request.run.expected)
    assert {
        (assessment.subject.subject_id, assessment.signal.signal_id)
        for assessment in batch.assessments
    } == {(target.subject.subject_id, target.signal.signal_id) for target in request.run.expected}
    return batch


def test_credit_enabled_summary_publishes_one_action_for_two_fields_with_one_backend_call(
    monkeypatch,
):
    from automationbench_v1.manifest_summary_assessments import SUMMARY_ACTION_OUTPUT

    path, raw, envelope, trace, task, backend, source, request = _action_publication_fixture(
        monkeypatch
    )
    before = (copy.deepcopy(trace.rewards), tuple(trace.credit_assignments))
    assert len(request.run.expected) == 2
    assert [target.subject.kind for target in request.run.expected] == ["trace", "execution"]
    recipient = request.run.expected[1].subject.execution
    assert recipient is not None and recipient.invocation_id == "8baf7cd9ff6549b49fd1f565a59ad93a"
    batch = _execute_summary_publication(task, source, request)
    assert backend.calls == 1
    assert [(item.signal.signal_id, item.value, item.status) for item in batch.assessments] == [
        ("excluded-prose", 0, "valid"),
        ("excluded-prose.action_harm", 1, "valid"),
    ]
    grouped = evidence(batch, SUMMARY_ACTION_OUTPUT)[0]["findings"]
    assert len(grouped) == 1 and grouped[0]["harm"] == 1
    assert len(grouped[0]["group"]["output_keys"]) == 2
    semantic = evidence(batch, SUMMARY_OUTPUT)[0]["evaluation"]
    assert sum(member["state"] == "violation" for member in semantic["findings"]) == 2
    assert (
        grouped[0]["group"]["recipient"]["execution"]["invocation_id"] != request.run.invocation_id
    )
    restored = vf.AssessmentBatch.model_validate_json(batch.model_dump_json())
    assert (
        restored.assessments == batch.assessments
        and restored.run.execution_evidence == batch.run.execution_evidence
    )
    assert (trace.rewards, tuple(trace.credit_assignments)) == before
    assert (
        path.read_bytes() == raw
        and (path.parent / "trace-0-artifacts.json").read_bytes() == envelope
    )


@pytest.mark.parametrize(
    "change", ["changed-public-prompt", "missing-policy", "wrong-check-digest"]
)
def test_credit_enabled_summary_policy_failure_keeps_all_preplanned_targets_abstained(
    monkeypatch, change
):
    from automationbench_v1.manifest_summary_assessments import SUMMARY_ACTION_OUTPUT

    path, raw, envelope, trace, task, backend, source, request = _action_publication_fixture(
        monkeypatch, policy_change=change
    )
    before = (copy.deepcopy(trace.rewards), tuple(trace.credit_assignments))
    assert len(request.run.expected) == 2
    assert request.run.expected[1].subject.execution is not None
    assert (
        request.run.expected[1].subject.execution.invocation_id
        == "8baf7cd9ff6549b49fd1f565a59ad93a"
    )
    batch = _execute_summary_publication(task, source, request)
    assert backend.calls == 0
    assert all(item.status == "abstained" and item.value is None for item in batch.assessments)
    assert not evidence(batch, SUMMARY_REQUEST) and not evidence(batch, SUMMARY_EXCHANGE)
    assert not evidence(batch, SUMMARY_ACTION_OUTPUT)
    if change == "wrong-check-digest":
        assert {item.reason for item in batch.assessments} == {
            "summary_action_public_policy_unavailable"
        }
    assert (trace.rewards, tuple(trace.credit_assignments)) == before
    assert (
        path.read_bytes() == raw
        and (path.parent / "trace-0-artifacts.json").read_bytes() == envelope
    )
