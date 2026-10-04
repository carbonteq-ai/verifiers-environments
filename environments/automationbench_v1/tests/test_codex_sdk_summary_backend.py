"""Isolated fake process protocol + actual native replay; no model accuracy claim."""

import asyncio
import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import verifiers.v1 as vf
from test_external_output_source import actual, material
from test_manifest_summary_assessments import evidence, setup, summary_batch
from test_summary_policy import prepared

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.external_outputs import ExternalOutputSource
from automationbench_v1.contracts.loader import load_contract
from automationbench_v1.contracts.summary_policy import (
    SummaryPolicyContext,
    evaluate_summary_policy,
    prepare_summary_context,
)
from automationbench_v1.manifest_summary_assessments import (
    SUMMARY_EXCHANGE,
    SUMMARY_OUTPUT,
    SUMMARY_REQUEST,
    SummaryBackendExchange,
)
from automationbench_v1.summary_backends import CodexSdkSummaryBackend
from automationbench_v1.summary_backends import codex_sdk as backend_module


@pytest.fixture(scope="module")
def raw_source():
    _, _, _, _, trace, task = actual()
    return material(trace, task)


def backend(**limits):
    return CodexSdkSummaryBackend(Path("/private/test-auth.json"), **limits)


def decisions(context, state="compliant"):
    return [
        {
            "output_key": f"o{index + 1}",
            "state": state,
            "reason": "controlled certificate",
            "citations": [{"start": 0, "end": len(output.text), "quote": output.text}],
            "relation_ids": [],
            "invocation_ids": [],
        }
        for index, output in enumerate(context.outputs)
    ]


def records(context, certificates=None, *, output_tokens=200):
    """Audited worker 0.160 protocol shapes, not simulated provider identity."""
    _, profile = backend_module.worker.restricted_catalog(
        backend_module.MODEL_CATALOG, "gpt-6-luna"
    )
    item = {
        "id": "answer-1",
        "type": "agentMessage",
        "phase": "final_answer",
        "text": canonical_json(
            {"decisions": decisions(context) if certificates is None else certificates}
        ),
    }
    counts = {
        "inputTokens": 100,
        "cachedInputTokens": 0,
        "cacheWriteInputTokens": 0,
        "outputTokens": output_tokens,
        "reasoningOutputTokens": 0,
        "totalTokens": 100 + output_tokens,
    }

    def event(method, **params):
        return {
            "kind": "event",
            "event": {"method": method, "params": {"threadId": "thread-1", **params}},
        }

    return [
        {"kind": "capability_catalog", **profile},
        {"kind": "authenticated", "account_type": "chatgpt", "model": "gpt-6-luna"},
        {"kind": "initialized", "sdk_version": "0.160.0", "response": {}},
        {
            "kind": "thread_started",
            "raw_response_events_requested": True,
            "response": {
                "model": "gpt-6-luna",
                "modelProvider": "openai",
                "thread": {"id": "thread-1", "environments": []},
            },
        },
        {"kind": "mcp_inventory", "scope": "thread_bound", "servers": []},
        {
            "kind": "builtin_tool_isolation",
            "revision": backend_module.worker.BUILTIN_TOOL_ISOLATION,
            "scope": "loaded_thread",
            "thread_id": "thread-1",
            "disabled_features": dict(backend_module.worker.DISABLED_BUILTIN_FEATURES),
        },
        {
            "kind": "turn_started",
            "response": {"turn": {"id": "turn-1", "status": "inProgress", "items": []}},
        },
        event("turn/started", turn={"id": "turn-1", "status": "inProgress", "items": []}),
        event("item/started", turnId="turn-1", item={**item, "text": ""}),
        event("item/completed", turnId="turn-1", item=item),
        event(
            "rawResponse/completed",
            turnId="turn-1",
            responseId="response-1",
            usage=counts,
            usageMetadata={},
        ),
        event(
            "thread/tokenUsage/updated",
            turnId="turn-1",
            tokenUsage={"total": counts, "last": counts},
        ),
        event(
            "turn/completed",
            turn={"id": "turn-1", "status": "completed", "error": None, "items": [item]},
        ),
        {
            "kind": "finished",
            "ok": True,
            "status": "completed",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "provider_errors_observed": 0,
            "provider_retries_observed": 0,
            "output_budget_state": "observed_output_only",
        },
    ]


def stream(values):
    return ("\n".join(canonical_json(value) for value in values) + "\n").encode()


def historical_answer(exchange):
    """Inspect old raw text without assigning current worker admission proof."""
    return next(
        record["event"]["params"]["item"]["text"]
        for record in map(json.loads, exchange.response_text.splitlines())
        if record.get("kind") == "event"
        and record["event"].get("method") == "item/completed"
        and record["event"].get("params", {}).get("item", {}).get("type") == "agentMessage"
    )


class Journal:
    def __init__(self):
        self.records = []

    def record_evidence(self, kind, payload, *, invocation_id):
        self.records.append((kind, payload, invocation_id))


def journal_events(journal):
    return next(
        payload
        for kind, payload, _ in reversed(journal.records)
        if kind == backend_module.SDK_EVENTS
    )


class Process:
    def __init__(self, raw, *, block=False, code=0):
        self.chunks = [chunk for chunk in [raw[:80], raw[80:]] if chunk]
        self.stdin = self
        self.stdout = self
        self.stderr: asyncio.StreamReader | None = None
        self.input = b""
        self.returncode = None
        self.code = code
        self.block = block
        self.started = asyncio.Event()
        self.terminated = False

    def write(self, raw):
        self.input += raw

    async def drain(self):
        await asyncio.sleep(0)

    def close(self):
        pass

    async def read(self, size):
        if self.chunks:
            return self.chunks.pop(0)
        self.started.set()
        if self.block:
            await asyncio.Event().wait()
        return b""

    async def wait(self):
        self.returncode = self.code
        return self.code

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.returncode = -9


def install(monkeypatch, process, journal=None):
    async def spawn(path):
        if journal is not None:
            assert journal.records[0][0] == SUMMARY_REQUEST
        return process

    monkeypatch.setattr(backend_module, "_spawn", spawn)


def execute(monkeypatch, context, raw, *, raw_source, **limits):
    driver = backend(**limits)
    journal = Journal()
    process = Process(raw)
    install(monkeypatch, process, journal)
    exchange = asyncio.run(
        driver.execute(
            context,
            raw_source,
            SimpleNamespace(run=SimpleNamespace(invocation_id="attempt-1")),
            journal,
        )
    )
    return driver, exchange, process, journal


def test_exact_request_before_await_raw_journal_and_truthful_selection(monkeypatch, raw_source):
    _, _, _, context = prepared(raw_source)
    raw = stream(records(context))
    driver, exchange, process, journal = execute(monkeypatch, context, raw, raw_source=raw_source)
    assert exchange.response_text.encode() == raw
    assert base64.b64decode(journal_events(journal)["raw_base64"]) == raw
    assert journal.records[0][1]["request_text"] == exchange.request_text
    assert "/private/test-auth" not in str(journal.records) + driver.identity.model_selection_json
    dispatched = json.loads(process.input)
    assert dispatched["auth_file"] == "/private/test-auth.json"
    assert dispatched["mcp_urls"] == {} and dispatched["output_budget"] == 16384
    payload = json.loads(dispatched["input"][0]["text"])
    assert payload["public_context"] == {
        "prompt": raw_source["task_evidence"]["prompt"],
        "initial": raw_source["task_evidence"]["initial"],
    }
    assert payload["source_digest"] == context.source_digest
    assert "assertions" not in payload["public_context"]
    assert json.loads(exchange.usage_json)["provider_response_model"] is None
    assert len(tuple(driver.parse(exchange, context))) == len(context.outputs)
    assert driver.identity is driver.identity


@pytest.mark.parametrize(
    "field", ["request_text", "response_text", "provider_identity", "usage_json", "full_output_ids"]
)
def test_copied_exchange_cannot_rebind_response_or_context(monkeypatch, raw_source, field):
    _, _, _, context = prepared(raw_source)
    driver, exchange, _, _ = execute(
        monkeypatch, context, stream(records(context)), raw_source=raw_source
    )
    changed = () if field == "full_output_ids" else "foreign"
    with pytest.raises(ValueError):
        tuple(driver.parse(exchange.model_copy(update={field: changed}), context))


@pytest.mark.parametrize(
    "limits",
    [{"timeout": True}, {"timeout": 901}, {"max_input_bytes": 1.0}, {"max_journal_bytes": 0}],
)
def test_limits_require_strict_positive_bounded_values(limits):
    with pytest.raises(ValueError):
        backend(**limits)


def test_worker_catalog_drift_does_not_change_identity_or_dispatch(monkeypatch, raw_source):
    _, _, _, context = prepared(raw_source)
    driver = backend()
    selection = driver.identity
    monkeypatch.setattr(backend_module, "MODEL_CATALOG", {"changed": True})
    assert driver.identity == selection
    with pytest.raises(ValueError, match="selection_changed"):
        asyncio.run(driver.execute(context, raw_source, None, Journal()))


@pytest.mark.parametrize("mode", ["failed", "oversized"])
def test_failed_process_or_journal_limit_retains_exact_available_prefix(
    monkeypatch, raw_source, mode
):
    _, _, _, context = prepared(raw_source)
    raw = stream(records(context))
    journal = Journal()
    process = Process(raw, code=2 if mode == "failed" else 0)
    install(monkeypatch, process, journal)
    limit = 90 if mode == "oversized" else 33_554_432
    with pytest.raises((RuntimeError, ValueError)):
        asyncio.run(
            backend(max_journal_bytes=limit).execute(
                context,
                raw_source,
                SimpleNamespace(run=SimpleNamespace(invocation_id="attempt-1")),
                journal,
            )
        )
    retained = journal_events(journal)
    assert base64.b64decode(retained["raw_base64"]) == raw[:limit]
    assert retained["truncated"] is (mode == "oversized")


@pytest.mark.parametrize(
    "fault",
    [
        "account",
        "model",
        "provider",
        "tools",
        "catalog",
        "retry",
        "error",
        "overshoot",
        "budget_missing",
        "bool_usage",
        "thread",
        "turn",
        "tool_item",
        "truncated",
        "unknown_kind",
        "duplicate_key",
    ],
)
def test_unqualified_transport_never_admits_decisions_and_retains_bytes(
    monkeypatch, raw_source, fault
):
    _, _, _, context = prepared(raw_source)
    values = records(context, output_tokens=16385 if fault == "overshoot" else 200)
    if fault == "account":
        values[1]["account_type"] = "apiKey"
    if fault == "model":
        values[1]["model"] = "other"
    if fault == "provider":
        values[3]["response"]["modelProvider"] = "qualification"
    if fault == "tools":
        values[4]["servers"] = [{"name": "tool"}]
    if fault == "catalog":
        values[0]["changes"]["tool_mode"] = "code_mode_only"
    if fault == "retry":
        values[-1]["provider_retries_observed"] = 1
    if fault == "error":
        values.insert(-1, {"kind": "error", "error": "failure"})
    if fault == "budget_missing":
        values.pop(10)
    if fault == "bool_usage":
        values[10]["event"]["params"]["usage"]["outputTokens"] = True
    if fault == "thread":
        values[-1]["thread_id"] = "foreign"
    if fault == "turn":
        values[6]["response"]["turn"]["id"] = "foreign"
    if fault == "tool_item":
        values[9]["event"]["params"]["item"]["type"] = "mcpToolCall"
    if fault == "unknown_kind":
        values.insert(-1, {"kind": "future", "text": "hidden"})
    raw = stream(values)
    if fault == "truncated":
        raw = raw[:-10]
    if fault == "duplicate_key":
        raw = b'{"kind":"authenticated","kind":"finished"}\n' + raw
    journal = Journal()
    process = Process(raw)
    install(monkeypatch, process, journal)
    with pytest.raises((ValueError, RuntimeError)):
        asyncio.run(
            backend().execute(
                context,
                raw_source,
                SimpleNamespace(run=SimpleNamespace(invocation_id="attempt-1")),
                journal,
            )
        )
    assert base64.b64decode(journal_events(journal)["raw_base64"]) == raw


def test_valid_harm_survives_malformed_peer_certificate(monkeypatch, raw_source):
    check, assistant, external, context = prepared(raw_source)
    check = check.model_copy(update={"assessor": backend().identity})
    context = prepare_summary_context(
        raw_source,
        check,
        assistant,
        external,
        assistant_source=backend_module.AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
    )
    certificates = decisions(context, "violation")[:1] + [
        {"output_key": "invented", "state": "compliant", "reason": "bad"}
    ]
    driver, exchange, _, _ = execute(
        monkeypatch, context, stream(records(context, certificates)), raw_source=raw_source
    )
    check = check.model_copy(update={"assessor": driver.identity})
    result = evaluate_summary_policy(
        raw_source,
        check,
        assistant,
        external,
        assistant_source=backend_module.AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        producer=driver.identity,
        full_output_ids=exchange.full_output_ids,
        decisions=driver.parse(exchange, context),
    )
    assert result.status == "violation" and result.compliance == 0 and result.decision_errors


def test_input_bound_rejects_without_dispatch(monkeypatch, raw_source):
    _, _, _, context = prepared(raw_source)

    async def forbidden(path):
        pytest.fail("oversized input dispatched")

    monkeypatch.setattr(backend_module, "_spawn", forbidden)
    with pytest.raises(ValueError, match="input_size"):
        asyncio.run(backend(max_input_bytes=10).execute(context, raw_source, None, Journal()))


def test_cancel_preserves_partial_stream_and_stops_process(monkeypatch, raw_source):
    _, _, _, context = prepared(raw_source)
    raw = b'{"kind":"authenticated"}\n'

    async def run():
        journal = Journal()
        process = Process(raw, block=True)
        install(monkeypatch, process, journal)
        job = asyncio.create_task(
            backend().execute(
                context,
                raw_source,
                SimpleNamespace(run=SimpleNamespace(invocation_id="attempt-1")),
                journal,
            )
        )
        await process.started.wait()
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert process.terminated
        assert base64.b64decode(journal_events(journal)["raw_base64"]) == raw

    asyncio.run(run())


@pytest.mark.parametrize(
    "marker,value", [("finish_reason", "length"), ("refusal", "refused"), ("truncated", True)]
)
def test_exposed_nonclean_provider_markers_rejected(raw_source, marker, value):
    _, _, _, context = prepared(raw_source)
    values = records(context)
    values[10]["event"]["params"][marker] = value
    with pytest.raises(ValueError, match="exposed"):
        backend()._admit(stream(values).decode())


def test_stderr_retained_on_failed_attempt_and_raw_saved_before_admission(monkeypatch, raw_source):
    _, _, _, context = prepared(raw_source)

    async def run():
        journal = Journal()
        process = Process(stream(records(context)))
        process.stderr = asyncio.StreamReader()
        process.stderr.feed_data(b"safe worker diagnostic\n")
        process.stderr.feed_eof()
        install(monkeypatch, process, journal)
        original = CodexSdkSummaryBackend._admit

        def admitted(self, response):
            assert base64.b64decode(journal_events(journal)["raw_base64"]).decode() == response
            raise ValueError("controlled_admission_failure")

        monkeypatch.setattr(CodexSdkSummaryBackend, "_admit", admitted)
        with pytest.raises(ValueError, match="controlled_admission_failure"):
            await backend().execute(
                context,
                raw_source,
                SimpleNamespace(run=SimpleNamespace(invocation_id="attempt-1")),
                journal,
            )
        diagnostics = next(
            payload for kind, payload, _ in journal.records if kind == backend_module.SDK_STDERR
        )
        assert base64.b64decode(diagnostics["raw_base64"]) == b"safe worker diagnostic\n"
        monkeypatch.setattr(CodexSdkSummaryBackend, "_admit", original)

    asyncio.run(run())


@pytest.mark.skipif(os.name != "posix", reason="Dedicated POSIX process-group cleanup gate")
def test_real_owned_process_group_cleanup_includes_child_after_leader_exit():
    async def run():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import subprocess,sys; child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); print(child.pid,flush=True)",
            stdout=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        assert process.stdout is not None
        child = int(await process.stdout.readline())
        try:
            # asyncio wait() also waits for inherited pipes; inspect the actual
            # leader exit before cleanup instead of awaiting child-held stdout.
            async with asyncio.timeout(5):
                while process.returncode is None:
                    await asyncio.sleep(0.01)
            await backend_module._stop(process)
            status = Path(f"/proc/{child}/status")
            assert not status.exists() or "State:\tZ" in status.read_text()
        finally:
            try:
                os.killpg(process.pid, 9)
            except ProcessLookupError:
                pass

    asyncio.run(run())


def test_native_actual_archive_transport_reload_and_rescore(monkeypatch):
    trace, task, contract, _ = setup(monkeypatch)
    driver = backend()
    raw_contract = contract.model_dump(mode="json")
    raw_contract["checks"][0]["assessor"] = driver.identity.model_dump(mode="json")
    contract = load_contract(canonical_json(raw_contract))
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    task.summary_backends = {driver.identity.assessor_id: driver}
    original = driver.execute

    async def fake_spawn(path):
        return current_process[0]

    current_process = []

    async def dynamic(prepared, raw_source, request, context):
        current_process[:] = [Process(stream(records(prepared)))]
        return await original(prepared, raw_source, request, context)

    monkeypatch.setattr(backend_module, "_spawn", fake_spawn)

    # Frozen driver remains immutable; composition wraps only transport fixture.
    class FixtureBackend:
        identity = driver.identity
        execute = staticmethod(dynamic)
        parse = staticmethod(driver.parse)

    task.summary_backends[driver.identity.assessor_id] = FixtureBackend()
    asyncio.run(task.score(trace))
    batch = summary_batch(trace)
    assert batch.assessments[0].value == 1 and trace.reward == 1
    assert evidence(batch, backend_module.SDK_EVENTS)[0]["raw_base64"]
    assert evidence(batch, SUMMARY_OUTPUT)[0]["evaluation"]["status"] == "compliant"
    restored = vf.WireTrace.model_validate_json(trace.model_dump_json())
    assert summary_batch(restored).run.execution_evidence == batch.run.execution_evidence
    asyncio.run(task.score(trace))
    assert summary_batch(trace).run.run_id != batch.run.run_id and trace.credit_assignments == []
    assert trace.reward == 1


@pytest.mark.network
def test_signed_in_summary_backend_live_one_attempt(monkeypatch):
    """Explicit opt-in release gate; one service-billed model attempt, no retry."""
    if os.environ.get("AUTOMATIONBENCH_RUN_SIGNED_IN_SUMMARY") != "1":
        pytest.skip("Set AUTOMATIONBENCH_RUN_SIGNED_IN_SUMMARY=1 to enable signed-in release gate")
    auth = os.environ.get("AUTOMATIONBENCH_SUMMARY_AUTH_FILE")
    output = os.environ.get("AUTOMATIONBENCH_SUMMARY_OUTPUT_DIR")
    if not auth or not output:
        pytest.skip("Explicit private auth path and retained output directory are required")
    auth_path, directory = Path(auth), Path(output)
    assert auth_path.is_absolute() and auth_path.is_file()
    assert directory.is_absolute() and not directory.exists(), (
        "Use a fresh output directory; never replace evidence"
    )
    directory.mkdir(mode=0o700, parents=True)
    from test_manifest_guard_assessments import penalties, terminal_records
    from test_summary_policy import configured

    from automationbench_v1.contracts.loader import load_task_contract

    path, original_bytes, _, _, trace, task = actual()  # Original episode/artifact SHA.
    trace.assessment_batches = []
    trace.credit_assignments = []  # Fresh in-memory experiment; archive stays unchanged.
    original_scalar = trace.rewards.copy()
    original_contract = load_task_contract(task.data.task_name)
    driver = CodexSdkSummaryBackend(auth_path)
    check = configured(material(trace, task)).model_copy(
        update={
            "source": "summary_assistant",
            "external": "summary_external",
            "assessor": driver.identity,
        }
    )
    raw_contract = original_contract.model_dump(mode="json")
    raw_contract["revision"] = "development_contact_with_sdk_summary@3"
    assert not {"summary_assistant", "summary_external"} & set(raw_contract["sources"])
    raw_contract["sources"].update(
        {
            "summary_assistant": {"adapter": "assistant.outputs@1", "kind": "assistant_text"},
            "summary_external": {"adapter": "external.outputs@1", "kind": "authored_text"},
        }
    )
    raw_contract["checks"].append(check.model_dump(mode="json"))
    contract = load_contract(canonical_json(raw_contract))
    assert contract.bindings == original_contract.bindings
    assert contract.credit == original_contract.credit
    assert contract.checks[:-1] == original_contract.checks
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    task.summary_backends = {driver.identity.assessor_id: driver}
    before = canonical_json(material(trace, task))
    (directory / "source-before.json").write_text(before)
    (directory / "contract.json").write_text(canonical_json(contract.model_dump(mode="json")))
    try:
        asyncio.run(task.score(trace))
    finally:
        (directory / "trace.json").write_text(trace.model_dump_json())
        (directory / "qualification-scope.json").write_text(
            canonical_json(
                {
                    "scope": "one signed-in mixed Contact/summary attempt, existing action credit and transport/lifecycle/budget; semantic accuracy unqualified",
                    "identity": driver.identity.model_dump(mode="json"),
                    "output_budget": 16384,
                    "source_after": material(trace, task),
                }
            )
        )
    batch = summary_batch(trace)
    assert batch.run.status == "complete" and trace.reward == 1
    assert not trace.assessment_errors and not trace.credit_errors
    assert trace.rewards == original_scalar and path.read_bytes() == original_bytes
    original_findings = {
        item.signal.signal_id: item
        for item in terminal_records(trace)
        if item.signal.signal_id
        in {"simple.requested_state", "simple.original_introduction_returned"}
    }
    assert set(original_findings) == {
        "simple.requested_state",
        "simple.original_introduction_returned",
    }
    assert all(item.value == 1 for item in original_findings.values())
    credits = penalties(trace)
    assert len(credits) == 2 and all(item.value == 1 for item in credits)
    assert {item.channel: item.recipient.execution.invocation_id for item in credits} == {
        "goal": "8baf7cd9ff6549b49fd1f565a59ad93a",
        "original-message-read": "eb45e8e2c5c648c1bce3fdb9994f3c29",
    }
    assert len(evidence(batch, SUMMARY_REQUEST)) == 1
    assert len(evidence(batch, backend_module.SDK_EVENTS)) == 1
    assert len(evidence(batch, backend_module.SDK_STDERR)) == 1
    exchanges = [payload for payload in evidence(batch, SUMMARY_EXCHANGE) if "exchange" in payload]
    assert len(exchanges) == 1 and exchanges[0]["exchange"]["provider_identity"].endswith(
        "authenticated-thread-selection@1"
    )
    result = evidence(batch, SUMMARY_OUTPUT)[0]
    assert result["backend_error"] is None
    # Model verdict is retained as observed, never required to be compliant.
    assert result["evaluation"]["status"] in {"compliant", "violation", "inapplicable", "abstained"}


@pytest.mark.parametrize(
    "text,quote,start,end,expected",
    [
        ("unique email", "unique email", 0, 20, (0, 12)),
        ("intro: exact quote", "exact quote", 1, 5, (7, 18)),
        ("same same", "same", 5, 9, (5, 9)),  # Valid supplied span disambiguates repeats.
        ("🧠 e\u0301 Kevin", "e\u0301 Kevin", 1, 6, (2, 10)),
    ],
)
def test_parser2_exact_unique_quote_resolution_uses_unicode_codepoints(
    text, quote, start, end, expected
):
    candidate = backend_module._Decision.model_validate(
        {
            "output_key": "output",
            "state": "compliant",
            "reason": "literal",
            "citations": [{"start": start, "end": end, "quote": quote}],
        }
    )
    (citation,) = backend()._citations(candidate, text)
    assert (citation.start, citation.end) == expected
    assert citation.quote == quote and text[citation.start : citation.end] == quote


@pytest.mark.parametrize(
    "text,quote,start,end",
    [
        ("same same", "same", 1, 3),
        ("aaaa", "aaa", 3, 4),  # Two overlapping matches, despite str.count()==1.
        ("known output", "different output", 0, 1),
        ("é", "e\u0301", 0, 1),  # No normalization or fuzzy matching.
    ],
)
def test_parser2_nonunique_or_absent_quote_rejected(text, quote, start, end):
    candidate = backend_module._Decision.model_validate(
        {
            "output_key": "output",
            "state": "compliant",
            "reason": "literal",
            "citations": [{"start": start, "end": end, "quote": quote}],
        }
    )
    with pytest.raises(ValueError, match="not_unique"):
        backend()._citations(candidate, text)


@pytest.mark.parametrize(
    "citation",
    [
        {"start": True, "end": 10, "quote": "exact"},
        {"start": 0, "end": 10.0, "quote": "exact"},
        {"start": "0", "end": 10, "quote": "exact"},
        {"start": 0, "end": 10, "quote": ""},
        {"start": 0, "end": 10},
        {"start": 0, "end": 10, "quote": 1},
        {"start": 2, "end": 1, "quote": "exact"},
    ],
)
def test_parser2_does_not_repair_malformed_citation_schema(citation):
    with pytest.raises(ValueError):
        backend_module._Decision.model_validate(
            {
                "output_key": "output",
                "state": "compliant",
                "reason": "literal",
                "citations": [citation],
            }
        )


def test_literal_coordinate_resolution_from_actual_parser1_answer_remains_offline():
    """Historical parser1 request is NOT a fresh protocol3 model execution."""
    path = Path(
        "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/summary-sdk-live-01/trace.json"
    )
    if not path.is_file():
        pytest.skip("Local retained signed-in parser1 qualification artifact unavailable")
    raw = path.read_bytes()
    expected_sha = "7fe9cc4a95bb83810027a4a09fa408a9b71ebe40378f3268ee7f44ed300e19a0"
    assert hashlib.sha256(raw).hexdigest() == expected_sha
    trace = json.loads(raw)
    payloads = [
        json.loads(record["payload_json"])
        for batch in trace["assessment_batches"]
        if batch["run"]["status"] == "complete"
        for record in batch["run"]["execution_evidence"]
    ]
    retained = next(payload["evaluation"] for payload in payloads if "evaluation" in payload)
    exchange = SummaryBackendExchange.model_validate(
        next(payload["exchange"] for payload in payloads if "exchange" in payload)
    )
    context = SummaryPolicyContext.model_validate(retained["context"])
    assert retained["producer"]["parser_revision"] == "1" and retained["status"] == "abstained"
    driver = backend()
    assert driver.identity.parser_revision == "4"
    with pytest.raises(ValueError, match="builtin_tool_isolation_inventory_invalid"):
        tuple(driver.parse(exchange, context))
    answer = historical_answer(exchange)
    historical = json.loads(answer)["decisions"]
    email = next(
        output for output in context.outputs if output.output_key.endswith(':assistant_email"]')
    )
    assert len(email.text) == 33
    candidate = backend_module._Decision.model_validate(
        next(item for item in historical if item["output_key"] == email.output_key)
    )
    (citation,) = driver._citations(candidate, email.text)
    assert citation.start == 0 and citation.end == 33 and citation.quote == email.text
    assert len(historical) == len(context.outputs)
    assert path.read_bytes() == raw  # Raw request/response and original verdict stay intact.


def test_parser2_unresolvable_peer_quote_preserves_independent_known_harm(monkeypatch, raw_source):
    check, assistant, external, _ = prepared(raw_source)
    driver = backend()
    check = check.model_copy(update={"assessor": driver.identity})
    context = prepare_summary_context(
        raw_source,
        check,
        assistant,
        external,
        assistant_source=backend_module.AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
    )
    certificates = decisions(context, "violation")
    certificates[1]["citations"][0]["quote"] = "quote absent from this particular output"
    driver, exchange, _, _ = execute(
        monkeypatch, context, stream(records(context, certificates)), raw_source=raw_source
    )
    result = evaluate_summary_policy(
        raw_source,
        check,
        assistant,
        external,
        assistant_source=backend_module.AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        producer=driver.identity,
        full_output_ids=exchange.full_output_ids,
        decisions=driver.parse(exchange, context),
    )
    assert result.status == "violation" and result.compliance == 0 and result.decision_errors


def test_protocol3_aliases_schema_and_null_quote_citations(monkeypatch, raw_source):
    _, _, _, context = prepared(raw_source)
    certificates = decisions(context)
    for certificate in certificates:
        for citation in certificate["citations"]:
            citation["start"] = citation["end"] = None
    certificates[0]["relation_ids"] = ["r1"]
    certificates[0]["invocation_ids"] = ["i1"]
    driver, exchange, process, _ = execute(
        monkeypatch, context, stream(records(context, certificates)), raw_source=raw_source
    )
    request = json.loads(process.input)
    payload = json.loads(request["input"][0]["text"])
    assert [item["output_key"] for item in payload["outputs"]] == ["o1", "o2", "o3"]
    assert [item["relation_id"] for item in payload["relations"]] == ["r1", "r2"]
    assert [item["invocation_id"] for item in payload["invocations"]] == [
        f"i{index + 1}" for index in range(len(context.invocations))
    ]
    assert all(
        item["text"] == output.text for item, output in zip(payload["outputs"], context.outputs)
    )
    assert all(
        "output_digest" not in item and "output_id" not in item for item in payload["outputs"]
    )
    schema = request["output_schema"]["properties"]["decisions"]
    resolved, abstained = schema["items"]["anyOf"]
    for branch in (resolved, abstained):
        assert branch["properties"]["output_key"]["enum"] == ["o1", "o2", "o3"]
    assert resolved["properties"]["citations"]["minItems"] == 1
    assert "minItems" not in abstained["properties"]["citations"]
    assert schema["minItems"] == schema["maxItems"] == 3
    parsed = tuple(driver.parse(exchange, context))
    assert [item.output_key for item in parsed] == [output.output_key for output in context.outputs]
    assert parsed[0].relation_ids == (context.relations[0].relation_id,)
    assert parsed[0].invocation_ids == (context.invocations[0].invocation_id,)
    assert parsed[0].citations[0].quote == context.outputs[0].text
    assert driver.identity.parser_revision == "4" and driver.identity.rubric_revision == "3"
    assert json.loads(driver.identity.model_selection_json)["response_schema"] == (
        "codex-turn-output-schema@4"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "raw_output_id",
        "unknown_alias",
        "raw_relation_id",
        "raw_invocation_id",
        "duplicate_output",
        "missing_output",
        "one_null",
        "missing_coordinates",
        "wrong_context_order",
    ],
)
def test_protocol3_reference_and_shape_failures_not_fuzzy_repaired(monkeypatch, raw_source, fault):
    _, _, _, context = prepared(raw_source)
    certificates = decisions(context)
    if fault == "raw_output_id":
        certificates[0]["output_key"] = context.outputs[0].output_key
    if fault == "unknown_alias":
        certificates[0]["output_key"] = "O1"
    if fault == "raw_relation_id":
        certificates[0]["relation_ids"] = [context.relations[0].relation_id]
    if fault == "raw_invocation_id":
        certificates[0]["invocation_ids"] = [context.invocations[0].invocation_id]
    if fault == "duplicate_output":
        certificates.append(certificates[0])
    if fault == "missing_output":
        certificates.pop()
    if fault == "one_null":
        certificates[0]["citations"][0]["start"] = None
    if fault == "missing_coordinates":
        certificates[0]["citations"][0].pop("start")
    driver, exchange, _, _ = execute(
        monkeypatch, context, stream(records(context, certificates)), raw_source=raw_source
    )
    if fault == "wrong_context_order":
        context = context.model_copy(update={"outputs": tuple(reversed(context.outputs))})
    with pytest.raises(ValueError):
        tuple(driver.parse(exchange, context))


def test_protocol3_empty_inventory_schema_has_no_invented_alias_or_empty_enum():
    schema = backend()._schema({}, {}, {})
    decisions_schema = schema["properties"]["decisions"]
    assert decisions_schema["minItems"] == decisions_schema["maxItems"] == 0
    assert all(
        "enum" not in branch["properties"]["output_key"]
        for branch in decisions_schema["items"]["anyOf"]
    )
    assert "o1" not in canonical_json(schema) and '"enum":[]' not in canonical_json(schema)


def test_protocol3_requires_audited_worker_schema_capability(monkeypatch):
    monkeypatch.setattr(backend_module.worker, "OUTPUT_SCHEMA_FORWARDING", None)
    with pytest.raises(ValueError, match="worker_output_schema"):
        backend()


def test_protocol3_duplicate_alias_inventory_cannot_dispatch(monkeypatch, raw_source):
    _, _, _, context = prepared(raw_source)
    context = context.model_copy(update={"outputs": context.outputs + context.outputs[:1]})
    with pytest.raises(ValueError, match="alias_inventory_ambiguous"):
        backend()._request(context)


def test_actual_live02_malformed_answer_and_failure_remain_immutable():
    path = Path(
        "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/summary-sdk-live-02/trace.json"
    )
    if not path.is_file():
        pytest.skip("Local retained signed-in parser2 mixed qualification artifact unavailable")
    raw = path.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "1566e327d33941311171c5f93733ee0fd341bba6ad3a6c2e854c9f8dc0ef94f1"
    )
    trace = json.loads(raw)
    payloads = [
        json.loads(record["payload_json"])
        for batch in trace["assessment_batches"]
        if batch["run"]["status"] == "complete"
        for record in batch["run"]["execution_evidence"]
    ]
    retained = next(payload for payload in payloads if "evaluation" in payload)
    exchange = SummaryBackendExchange.model_validate(
        next(payload["exchange"] for payload in payloads if "exchange" in payload)
    )
    requested = next(
        payload for payload in payloads if "producer" in payload and "request_text" in payload
    )
    assert requested["producer"]["parser_revision"] == "2"
    assert (
        retained["evaluation"]["producer"] is None
    )  # Malformed answer admitted no semantic producer.
    assert retained["evaluation"]["status"] == "abstained"
    assert "Extra data" in retained["backend_error"]
    driver = backend()
    answer = historical_answer(exchange)
    assert answer.endswith("</final>") and "5659ad93a" in answer
    with pytest.raises(json.JSONDecodeError, match="Extra data"):
        backend_module._json(answer)
    context = SummaryPolicyContext.model_validate(retained["evaluation"]["context"])
    with pytest.raises(ValueError, match="builtin_tool_isolation_inventory_invalid"):
        tuple(driver.parse(exchange, context))
    assert path.read_bytes() == raw  # No stripping, remapping or fabricated repaired live verdict.


@pytest.mark.parametrize("state", ["compliant", "violation", "inapplicable"])
def test_protocol4_resolved_certificates_require_nonempty_citations(state):
    raw = {
        "output_key": "o1",
        "state": state,
        "reason": "controlled certificate",
        "citations": [],
        "relation_ids": [],
        "invocation_ids": [],
    }
    with pytest.raises(ValueError, match="resolved_decision_requires_citation"):
        backend_module._Decision.model_validate(raw)
    schema = backend()._schema({"o1": object()}, {}, {})
    resolved, abstained = schema["properties"]["decisions"]["items"]["anyOf"]
    assert state in resolved["properties"]["state"]["enum"]
    assert resolved["properties"]["citations"]["minItems"] == 1
    assert abstained["properties"]["state"]["enum"] == ["abstained"]
    raw["citations"] = [{"start": None, "end": None, "quote": "Kevin Torres"}]
    candidate = backend_module._Decision.model_validate(raw)
    assert backend()._citations(candidate, "Kevin Torres")[0].quote == "Kevin Torres"


def test_protocol4_uncited_abstention_is_valid_and_does_not_become_compliance(
    monkeypatch, raw_source
):
    _, _, _, context = prepared(raw_source)
    certificates = decisions(context, "abstained")
    for certificate in certificates:
        certificate["citations"] = []
    driver, exchange, _, _ = execute(
        monkeypatch, context, stream(records(context, certificates)), raw_source=raw_source
    )
    parsed = tuple(driver.parse(exchange, context))
    assert len(parsed) == len(context.outputs)
    assert all(item.state == "abstained" and item.citations == () for item in parsed)


@pytest.mark.parametrize("bad_index", [0, 2])
@pytest.mark.parametrize("bad_state", ["compliant", "violation", "inapplicable"])
def test_protocol4_uncited_peer_before_or_after_valid_harm_preserves_generator_progress(
    monkeypatch, raw_source, bad_index, bad_state
):
    check, assistant, external, _ = prepared(raw_source)
    driver = backend()
    check = check.model_copy(update={"assessor": driver.identity})
    context = prepare_summary_context(
        raw_source,
        check,
        assistant,
        external,
        assistant_source=backend_module.AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
    )
    certificates = decisions(context, "violation")
    certificates[bad_index]["state"] = bad_state
    certificates[bad_index]["citations"] = []
    driver, exchange, _, _ = execute(
        monkeypatch, context, stream(records(context, certificates)), raw_source=raw_source
    )
    pending = iter(driver.parse(exchange, context))
    accepted = [next(pending), next(pending)]
    assert {item.output_key for item in accepted} == {
        output.output_key for index, output in enumerate(context.outputs) if index != bad_index
    }
    with pytest.raises(ValueError, match="peer_certificate_invalid"):
        next(pending)
    result = evaluate_summary_policy(
        raw_source,
        check,
        assistant,
        external,
        assistant_source=backend_module.AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        producer=driver.identity,
        full_output_ids=exchange.full_output_ids,
        decisions=driver.parse(exchange, context),
    )
    assert result.status == "violation" and result.compliance == 0
    assert result.decision_errors
    assert result.findings[bad_index].state == "abstained"


def test_actual_semantic02a_uncited_inapplicable_answer_remains_historical_failure():
    path = Path(
        "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/"
        "summary-semantic-live-01/attempts/"
        "d73a59bb79a3ce43b8d57cbbfe443286a7fc9e7d4ce812c69d7831ad730b2bfa/"
        "native-assessments.json"
    )
    if not path.is_file():
        pytest.skip("Local retained semantic02a protocol3 artifact unavailable")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "adf8fcffc36e839762e45af199a516c409dc1cd238f3577131833a2cfd5b6b62"
    )
    records_ = json.loads(raw)["batches"][-1]["run"]["execution_evidence"]
    payloads = [json.loads(record["payload_json"]) for record in records_]
    retained = next(payload["evaluation"] for payload in payloads if "evaluation" in payload)
    exchange = SummaryBackendExchange.model_validate(
        next(payload["exchange"] for payload in payloads if "exchange" in payload)
    )
    assert retained["producer"]["parser_revision"] == "3"
    assert retained["status"] == "abstained" and retained["compliance"] is None
    assert retained["decision_errors"] == ["summary_decision_requires_output_citation"] * 2
    assert hashlib.sha256(exchange.response_text.encode()).hexdigest() == (
        "f74ed4c8e02c8a43d7e4f1696b79569ac3adccf1ec22a6d85729ff48bd077308"
    )
    old_schema = json.loads(exchange.request_text)["output_schema"]
    assert (
        "minItems"
        not in (old_schema["properties"]["decisions"]["items"]["properties"]["citations"])
    )
    driver = backend()
    answer = historical_answer(exchange)
    certificates = json.loads(answer)["decisions"]
    assert backend_module._Decision.model_validate(certificates[0]).state == "compliant"
    assert [item["output_key"] for item in certificates[1:]] == ["o2", "o3"]
    for certificate in certificates[1:]:
        assert certificate["state"] == "inapplicable" and certificate["citations"] == []
        with pytest.raises(ValueError, match="resolved_decision_requires_citation"):
            backend_module._Decision.model_validate(certificate)
    context = SummaryPolicyContext.model_validate(retained["context"])
    with pytest.raises(ValueError, match="builtin_tool_isolation_inventory_invalid"):
        tuple(driver.parse(exchange, context))
    assert path.read_bytes() == raw


def test_worker_isolation_migration_preserves_protocol4_semantic_wire_not_old_lineage():
    path = Path(
        "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/"
        "summary-semantic-live-02/attempts/"
        "3ff235a013c5171b13ab347b3e8902872e465beca0f8117a8b3bf99a58b4fd1d/"
        "native-assessments.json"
    )
    if not path.is_file():
        pytest.skip("Local retained protocol4 summary campaign artifact unavailable")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "f0ef01f76d3e9625f0df4abebe64c3bec158148f3a64bbddc02ba5821831dcc0"
    )
    payloads = [
        json.loads(item["payload_json"])
        for item in json.loads(raw)["batches"][-1]["run"]["execution_evidence"]
    ]
    requested = next(item for item in payloads if "request_text" in item and "producer" in item)
    evaluation = next(item["evaluation"] for item in payloads if "evaluation" in item)
    exchange = SummaryBackendExchange.model_validate(
        next(item["exchange"] for item in payloads if "exchange" in item)
    )
    context = SummaryPolicyContext.model_validate(evaluation["context"])
    public = json.loads(json.loads(exchange.request_text)["input"][0]["text"])["public_context"]
    driver = backend()
    old = requested["producer"]
    current = driver.identity.model_dump(mode="json")
    old_selection = json.loads(old["model_selection_json"])
    current_selection = json.loads(current["model_selection_json"])
    assert current_selection.pop("worker_sha256") != old_selection.pop("worker_sha256")
    assert current_selection.pop("builtin_tool_isolation") == "codex-declared-tools-only@1"
    assert current_selection.pop("builtin_tool_isolation_scope") == "loaded_thread"
    assert current_selection == old_selection
    assert {k: v for k, v in current.items() if k != "model_selection_json"} == {
        k: v for k, v in old.items() if k != "model_selection_json"
    }
    text, _, covered = driver._request(context, public)
    assert text == exchange.request_text
    assert covered == exchange.full_output_ids
    with pytest.raises(ValueError, match="builtin_tool_isolation_inventory_invalid"):
        tuple(driver.parse(exchange, context))
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "duplicate",
        "foreign",
        "late",
        "early",
        "revision",
        "scope",
        "true",
        "int",
        "float",
        "missing_feature",
        "extra_feature",
        "extra_field",
    ],
)
def test_builtin_isolation_receipt_is_exact_pre_turn_proof(monkeypatch, raw_source, fault):
    _, _, _, context = prepared(raw_source)
    values = records(context)
    proof = values[5]
    feature = next(iter(proof["disabled_features"]))
    if fault == "missing":
        values.pop(5)
    elif fault == "duplicate":
        values.insert(5, proof.copy())
    elif fault == "foreign":
        proof["thread_id"] = "foreign"
    elif fault == "late":
        values.insert(-1, values.pop(5))
    elif fault == "early":
        values.insert(0, values.pop(5))
    elif fault == "revision":
        proof["revision"] = "codex-declared-tools-only@2"
    elif fault == "scope":
        proof["scope"] = "app_server_startup"
    elif fault in {"true", "int", "float"}:
        proof["disabled_features"][feature] = {"true": True, "int": 0, "float": 0.0}[fault]
    elif fault == "missing_feature":
        proof["disabled_features"].pop(feature)
    elif fault == "extra_feature":
        proof["disabled_features"]["future_tool"] = False
    else:
        proof["invented"] = True
    raw = stream(values)
    journal = Journal()
    install(monkeypatch, Process(raw), journal)
    with pytest.raises(ValueError, match="builtin_tool_isolation|builtin_isolation"):
        asyncio.run(
            backend().execute(
                context,
                raw_source,
                SimpleNamespace(run=SimpleNamespace(invocation_id="proof-attempt")),
                journal,
            )
        )
    assert base64.b64decode(journal_events(journal)["raw_base64"]) == raw
