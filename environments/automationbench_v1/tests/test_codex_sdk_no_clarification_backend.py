"""Fixed policy profile qualification with fake processes; no model accuracy claim."""

import asyncio
import base64
import hashlib
import json
import os
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_codex_sdk_summary_backend import Journal, Process, decisions, records, stream
from test_external_output_source import actual, material
from test_summary_policy import prepared

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.authored_outputs import AuthoredOutputSource
from automationbench_v1.contracts.external_outputs import ExternalOutputSource
from automationbench_v1.contracts.no_clarification import (
    NoClarificationCheck,
    evaluate_no_clarification_policy,
    prepare_no_clarification_context,
)
from automationbench_v1.summary_backends import (
    CodexSdkNoClarificationBackend,
    CodexSdkSummaryBackend,
    codex_sdk,
)
from automationbench_v1.summary_backends import codex_sdk_no_clarification as policy


def backend(**limits):
    return CodexSdkNoClarificationBackend(Path("/private/test-auth.json"), **limits)


@pytest.fixture(scope="module")
def contrast_inputs():
    from automationbench_v1.calibration.no_clarification_cases import (
        load_no_clarification_replay,
        prepare_no_clarification_case,
    )
    from automationbench_v1.calibration.summary_cases import SummaryCaseSpec
    from automationbench_v1.contracts.authored_outputs import capture_authored_outputs
    from automationbench_v1.contracts.external_outputs import capture_external_outputs

    path = Path(
        "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate/no-clarification-case-preparation-v1.json"
    )
    document = json.loads(path.read_bytes())
    baseline = load_no_clarification_replay(document)
    result = {}
    for spec in document["cases"]:
        if spec["case_id"] not in {"NC16", "NC18"}:
            continue
        case = prepare_no_clarification_case(
            baseline, SummaryCaseSpec.model_validate(spec), assessor=backend().identity
        )
        sealed = json.loads(case.source.source_json)
        raw = {
            key: sealed[key]
            for key in ("task_evidence", "tool_execution_events", "state_write_receipts")
        }
        result[case.case_id] = (
            raw,
            case.contract.checks[0],
            capture_authored_outputs(raw, AuthoredOutputSource()),
            capture_external_outputs(raw, ExternalOutputSource()),
            case.context,
        )
    return result


def semantic_decisions(context, state="inapplicable"):
    return decisions(
        context.model_copy(
            update={"outputs": tuple(output for output in context.outputs if output.text != "")}
        ),
        state,
    )


def reduce(inputs, driver, exchange):
    raw, check, assistant, external, context = inputs
    return evaluate_no_clarification_policy(
        raw,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        producer=driver.identity,
        full_output_ids=exchange.full_output_ids,
        decisions=driver.parse(exchange, context),
    )


def test_exact_empty_is_deterministic_not_a_judge_certificate(monkeypatch, contrast_inputs):
    values = contrast_inputs["NC16"]
    context = values[-1]
    driver, exchange, _, _ = execute(monkeypatch, values, semantic_decisions(context))
    request = json.loads(exchange.request_text)
    payload = json.loads(request["input"][0]["text"])
    assert len(payload["outputs"]) == 2 and all(
        output["text"] != "" for output in payload["outputs"]
    )
    assert [output["text"] for output in payload["deterministic_empty_outputs"]] == [""]
    assert exchange.full_output_ids == tuple(output.output_key for output in context.outputs)
    assert request["output_schema"]["properties"]["decisions"]["minItems"] == 2
    result = reduce(values, driver, exchange)
    empty_key = next(output.output_key for output in context.outputs if output.text == "")
    finding = next(finding for finding in result.findings if finding.output_key == empty_key)
    assert finding.state == "inapplicable" and finding.basis == "empty_text"
    assert result.compliance == 1 and not result.decision_errors


def test_whitespace_remains_in_semantic_inventory(inputs):
    context = inputs[-1]
    changed = context.model_copy(
        update={
            "outputs": (context.outputs[0].model_copy(update={"text": " "}), *context.outputs[1:])
        }
    )
    _, request, covered = backend()._request(changed)
    payload = json.loads(request["input"][0]["text"])
    assert payload["outputs"][0]["text"] == " "
    assert payload["deterministic_empty_outputs"] == []
    assert len(covered) == len(context.outputs)


@pytest.mark.parametrize("retain_empty", [False, True])
def test_no_semantic_outputs_have_exact_zero_decision_schema(contrast_inputs, retain_empty):
    context = contrast_inputs["NC16"][-1]
    empty = tuple(output for output in context.outputs if output.text == "")
    selected = empty if retain_empty else ()
    changed = context.model_copy(update={"outputs": selected, "relations": (), "invocations": ()})
    _, request, covered = backend()._request(changed)
    payload = json.loads(request["input"][0]["text"])
    assert payload["outputs"] == []
    assert len(payload["deterministic_empty_outputs"]) == len(selected)
    assert covered == tuple(output.output_key for output in selected)
    schema = request["output_schema"]["properties"]["decisions"]
    assert schema["minItems"] == schema["maxItems"] == 0


def test_known_harm_through_gap_uses_only_qualified_references(monkeypatch, contrast_inputs):
    values = contrast_inputs["NC18"]
    context = values[-1]
    certificates = semantic_decisions(context, "violation")
    _, request, _ = backend()._request(context)
    payload = json.loads(request["input"][0]["text"])
    assert payload["unqualified_invocation_context"]
    assert all(item["status"] == "qualified" for item in payload["invocations"])
    assert all(
        "invocation_id" not in item and item["reference_status"] == "not_citable"
        for item in payload["unqualified_invocation_context"]
    )
    aliases = [item["invocation_id"] for item in payload["invocations"]]
    certificates[0]["invocation_ids"] = aliases
    driver, exchange, _, _ = execute(monkeypatch, values, certificates)
    result = reduce(values, driver, exchange)
    assert result.compliance == 0 and result.status == "violation"
    assert result.context is not None and not result.context.invocation_closed


@pytest.mark.parametrize("bad_index", [0, 1])
def test_unqualified_reference_is_not_ignored_and_independent_harm_survives(
    monkeypatch, contrast_inputs, bad_index
):
    values = contrast_inputs["NC18"]
    certificates = semantic_decisions(values[-1], "violation")
    certificates[bad_index]["invocation_ids"] = ["i7"]
    driver, exchange, _, _ = execute(monkeypatch, values, certificates)
    result = reduce(values, driver, exchange)
    assert result.compliance == 0 and result.decision_errors
    assert result.findings[bad_index].state == "abstained"


@pytest.mark.parametrize("case_id", ["NC16", "NC18"])
def test_frozen_failed_campaign_is_not_reinterpreted_by_parser5(case_id):
    from automationbench_v1.calibration.summary_cases import PreparedSummaryCase
    from automationbench_v1.manifest_summary_assessments import SummaryBackendExchange

    directory = Path(
        "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/no-clarification-semantic-live-01"
    )
    manifest = json.loads((directory / "manifest.json").read_bytes())
    item = next(item for item in manifest["cases"] if item["case_id"] == case_id)
    prepared = PreparedSummaryCase.model_validate_json(
        (directory / "inputs" / (item["case_digest"] + ".json")).read_bytes()
    )
    artifact = directory / "attempts" / item["case_digest"] / "native-assessments.json"
    raw = artifact.read_bytes()
    before = hashlib.sha256(raw).hexdigest()
    exchanges = [
        json.loads(record["payload_json"])["exchange"]
        for batch in json.loads(raw)["batches"]
        for record in batch["run"]["execution_evidence"]
        if record["kind"] == "automationbench.no_clarification_semantic_exchange@1"
        and "exchange" in json.loads(record["payload_json"])
    ]
    exchange = SummaryBackendExchange.model_validate(exchanges[-1])
    # Inspect the historical raw answer without assigning current transport authority.
    answer = next(
        item["event"]["params"]["item"]["text"]
        for item in map(json.loads, exchange.response_text.splitlines())
        if item.get("kind") == "event"
        and item["event"].get("method") == "item/completed"
        and item["event"].get("params", {}).get("item", {}).get("type") == "agentMessage"
    )
    parsed = json.loads(answer)
    if case_id == "NC16":
        assert any(
            item["state"] == "abstained" and item["citations"] == [] for item in parsed["decisions"]
        )
    else:
        assert any(
            item["state"] == "violation" and "i7" in item["invocation_ids"]
            for item in parsed["decisions"]
        )
    with pytest.raises(ValueError, match="builtin_tool_isolation_inventory_invalid"):
        tuple(backend().parse(exchange, prepared.context))
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == before


@pytest.fixture(scope="module")
def inputs():
    _, _, _, _, trace, task = actual()
    raw = material(trace, task)
    previous, assistant, external, summary_context = prepared(raw)
    declaration = previous.model_dump(mode="json")
    declaration.update(operator="no_clarification@1", assessor=backend().identity.model_dump())
    check = NoClarificationCheck.model_validate(declaration)
    context = prepare_no_clarification_context(
        raw,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
    )
    assert (
        context.check_digest
        == hashlib.sha256(canonical_json(check.model_dump(mode="json")).encode()).hexdigest()
    )
    assert context.check_digest != summary_context.check_digest
    return raw, check, assistant, external, context


def execute(monkeypatch, inputs, certificates):
    raw, _, _, _, context = inputs
    observed = stream(records(context, certificates))
    process, journal = Process(observed), Journal()

    async def spawn(path):
        assert journal.records[0][0] == policy.CLARIFICATION_REQUEST
        return process

    monkeypatch.setattr(codex_sdk, "_spawn", spawn)
    driver = backend()
    exchange = asyncio.run(
        driver.execute(
            context,
            raw,
            SimpleNamespace(run=SimpleNamespace(invocation_id="test-attempt")),
            journal,
        )
    )
    return driver, exchange, process, journal


def test_fixed_profile_has_distinct_identity_rubric_and_exact_raw_journal(monkeypatch, inputs):
    *_, context = inputs
    driver, exchange, process, journal = execute(monkeypatch, inputs, decisions(context))
    summary = CodexSdkSummaryBackend(Path("/private/test-auth.json"))
    assert driver.identity.assessor_id == "codex-sdk-no-clarification"
    assert driver.identity.parser_revision == "5"
    assert driver.identity.rubric_revision == "2"
    selection = json.loads(driver.identity.model_selection_json)
    assert selection["rubric_sha256"] == hashlib.sha256(policy.RUBRIC.encode()).hexdigest()
    assert selection["deterministic_empty_outputs"] is True
    assert selection["qualified_invocation_references"] is True
    assert driver.identity != summary.identity
    dispatched = json.loads(process.input)
    assert dispatched["system_prompt"] == policy.RUBRIC
    assert dispatched["mcp_urls"] == {} and dispatched["approved_mcp_tools"] == {}
    assert [kind for kind, _, _ in journal.records] == [
        policy.CLARIFICATION_REQUEST,
        policy.CLARIFICATION_SDK_EVENTS,
        policy.CLARIFICATION_SDK_STDERR,
    ]
    assert journal.records[0][1]["request_text"] == exchange.request_text
    assert base64.b64decode(journal.records[1][1]["raw_base64"]) == exchange.response_text.encode()
    assert "/private/test-auth" not in str(journal.records)
    assert all(
        item.assessor_id == driver.identity.assessor_id for item in driver.parse(exchange, context)
    )
    with pytest.raises(ValueError, match="binding_invalid"):
        tuple(summary.parse(exchange, context))
    with pytest.raises(TypeError):
        CodexSdkNoClarificationBackend(Path("/private/test-auth.json"), rubric="custom")  # type: ignore[call-arg]
    with pytest.raises(FrozenInstanceError):
        setattr(driver, "_profile", summary._profile)  # noqa: B010 - exercise frozen instance admission.


@pytest.mark.parametrize("bad_index", [0, 2])
@pytest.mark.parametrize("fault", ["uncited", "unknown_reference", "wrong_quote"])
def test_independent_harm_survives_bad_peer_without_semantic_repair(
    monkeypatch, inputs, bad_index, fault
):
    raw, check, assistant, external, context = inputs
    certificates = decisions(context, "violation")
    if fault == "uncited":
        certificates[bad_index]["citations"] = []
    elif fault == "unknown_reference":
        certificates[bad_index]["invocation_ids"] = ["not-a-source-reference"]
    else:
        certificates[bad_index]["citations"][0]["quote"] = "not present in this output"
    driver, exchange, _, _ = execute(monkeypatch, inputs, certificates)
    result = evaluate_no_clarification_policy(
        raw,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        producer=driver.identity,
        full_output_ids=exchange.full_output_ids,
        decisions=driver.parse(exchange, context),
    )
    assert result.compliance == 0 and result.status == "violation"
    assert result.findings[bad_index].state == "abstained" and result.decision_errors


def test_uncited_abstention_and_source_or_rubric_retarget_are_not_compliance(monkeypatch, inputs):
    raw, check, assistant, external, context = inputs
    certificates = decisions(context, "abstained")
    for certificate in certificates:
        certificate["citations"] = []
    driver, exchange, _, _ = execute(monkeypatch, inputs, certificates)
    result = evaluate_no_clarification_policy(
        raw,
        check,
        assistant,
        external,
        assistant_source=AuthoredOutputSource(),
        external_source=ExternalOutputSource(),
        producer=driver.identity,
        full_output_ids=exchange.full_output_ids,
        decisions=driver.parse(exchange, context),
    )
    assert result.compliance is None and result.status == "abstained"
    with pytest.raises(ValueError, match="binding_invalid"):
        tuple(driver.parse(exchange, context.model_copy(update={"check_digest": "0" * 64})))
    changed = json.loads(exchange.request_text)
    changed["system_prompt"] = codex_sdk.RUBRIC
    with pytest.raises(ValueError, match="binding_invalid"):
        tuple(
            driver.parse(
                exchange.model_copy(update={"request_text": canonical_json(changed)}), context
            )
        )


def test_cancellation_retains_available_raw_prefix_and_stops_only_attempt(monkeypatch, inputs):
    raw, _, _, _, context = inputs
    prefix = b'{"kind":"incomplete-worker-prefix"}\n'
    process, journal = Process(prefix, block=True), Journal()

    async def spawn(path):
        assert journal.records[0][0] == policy.CLARIFICATION_REQUEST
        return process

    monkeypatch.setattr(codex_sdk, "_spawn", spawn)

    async def run():
        pending = asyncio.create_task(
            backend().execute(
                context,
                raw,
                SimpleNamespace(run=SimpleNamespace(invocation_id="test-attempt")),
                journal,
            )
        )
        await process.started.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

    asyncio.run(run())
    assert process.terminated
    assert base64.b64decode(journal.records[1][1]["raw_base64"]) == prefix
    assert journal.records[1][0] == policy.CLARIFICATION_SDK_EVENTS
    assert journal.records[-1][0] == policy.CLARIFICATION_SDK_STDERR


def _mixed_contact_attempt(monkeypatch, driver, directory):
    """One scoring wave; preserve failed-attempt evidence without an implicit retry."""
    from test_manifest_guard_assessments import penalties, terminal_records
    from test_manifest_summary_assessments import evidence
    from test_summary_policy import configured

    from automationbench_v1 import manifest_assessments
    from automationbench_v1.contracts.engine import compile_contract
    from automationbench_v1.contracts.loader import load_contract, load_task_contract
    from automationbench_v1.manifest_no_clarification_assessments import (
        NO_CLARIFICATION_EXCHANGE,
        NO_CLARIFICATION_OUTPUT,
        NO_CLARIFICATION_PRODUCER,
        NO_CLARIFICATION_REQUEST,
    )

    assert directory.is_absolute() and not directory.exists(), "Use a fresh evidence directory"
    directory.mkdir(mode=0o700, parents=True)
    path, original_bytes, envelope, _, trace, task = actual()
    # Fresh immutable archive is the starting ledger; never erase prior contributions.
    assert trace.assessment_batches == [] and trace.credit_assignments == []
    original_scalar = trace.rewards.copy()
    original_contract = load_task_contract(task.data.task_name)
    original_source = material(trace, task)
    declaration = configured(original_source).model_dump(mode="json")
    declaration.update(
        operator="no_clarification@1",
        check_id="no-clarification",
        signal_id="no-clarification-compliance",
        source="clarification_assistant",
        external="clarification_external",
        assessor=driver.identity.model_dump(mode="json"),
    )
    check = NoClarificationCheck.model_validate(declaration)
    raw_contract = original_contract.model_dump(mode="json")
    raw_contract["revision"] = "development_contact_sdk_no_clarification@1"
    assert not {"clarification_assistant", "clarification_external"} & set(raw_contract["sources"])
    raw_contract["sources"].update(
        {
            "clarification_assistant": {"adapter": "assistant.outputs@1", "kind": "assistant_text"},
            "clarification_external": {"adapter": "external.outputs@1", "kind": "authored_text"},
        }
    )
    raw_contract["checks"].append(check.model_dump(mode="json"))
    contract = load_contract(canonical_json(raw_contract))
    compile_contract(contract)
    assert contract.bindings == original_contract.bindings
    assert contract.credit == original_contract.credit and len(contract.credit) == 2
    assert contract.checks[:-1] == original_contract.checks
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    task.no_clarification_backends = {driver.identity.assessor_id: driver}
    before = canonical_json(original_source)
    (directory / "source-before.json").write_text(before)
    (directory / "contract.json").write_text(canonical_json(contract.model_dump(mode="json")))
    provenance = {
        "scope": "one mixed Contact/no-clarification backend attempt; semantic accuracy unqualified",
        "identity": driver.identity.model_dump(mode="json"),
        "original_episode_path": str(path),
        "original_episode_sha256": hashlib.sha256(original_bytes).hexdigest(),
        "original_artifact_envelope_sha256": hashlib.sha256(envelope).hexdigest(),
        "source_before_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "output_budget": {"threshold": 16384, "enforcement": "reported_observed_threshold"},
        "provider_response_model": None,
        "model_provenance": "authenticated_thread_selection_only",
        "automatic_retries": 0,
        "scoring_waves": 1,
        "semantic_penalty": False,
    }
    (directory / "qualification-scope.json").write_text(canonical_json(provenance))
    try:
        asyncio.run(task.score(trace))
    finally:
        (directory / "trace.json").write_text(trace.model_dump_json())
        (directory / "source-after.json").write_text(canonical_json(material(trace, task)))

    batches = [
        batch
        for batch in trace.assessment_batches
        if batch.run.producer_id == NO_CLARIFICATION_PRODUCER
    ]
    assert len({batch.run.run_id for batch in batches}) == 1
    complete = [batch for batch in batches if batch.run.status == "complete"]
    assert len(complete) == 1
    batch = complete[0]
    requests = evidence(batch, NO_CLARIFICATION_REQUEST)
    exchanges = evidence(batch, NO_CLARIFICATION_EXCHANGE)
    outputs = evidence(batch, NO_CLARIFICATION_OUTPUT)
    assert len(requests) == len(exchanges) == len(outputs) == 1
    exchange = exchanges[0]["exchange"]
    (directory / "request.json").write_text(requests[0]["request_text"])
    (directory / "exchange.json").write_text(canonical_json(exchange))
    (directory / "usage.json").write_text(exchange["usage_json"])
    (directory / "evaluation.json").write_text(canonical_json(outputs[0]))
    events = evidence(batch, policy.CLARIFICATION_SDK_EVENTS)
    diagnostics = evidence(batch, policy.CLARIFICATION_SDK_STDERR)
    assert len(events) == len(diagnostics) == 1
    (directory / "sdk-events.jsonl").write_bytes(base64.b64decode(events[0]["raw_base64"]))
    (directory / "sdk-stderr.bin").write_bytes(base64.b64decode(diagnostics[0]["raw_base64"]))
    assert not trace.assessment_errors and not trace.credit_errors
    assert path.read_bytes() == original_bytes
    assert (path.parent / "trace-0-artifacts.json").read_bytes() == envelope
    assert trace.rewards == original_scalar and trace.reward == 1
    after = material(trace, task)
    for key in ("tool_execution_events", "state_write_receipts"):
        assert after.get(key) == original_source.get(key)
    for key in ("prompt", "initial", "authored_outputs"):
        assert after["task_evidence"][key] == original_source["task_evidence"][key]
    original_findings = {
        item.signal.signal_id: item
        for item in terminal_records(trace)
        if item.signal.signal_id
        in {"simple.requested_state", "simple.original_introduction_returned"}
    }
    assert len(original_findings) == 2 and all(
        item.value == 1 for item in original_findings.values()
    )
    credits = penalties(trace)
    assert len(credits) == 2 and all(item.value == 1 for item in credits)
    assert {item.channel: item.recipient.execution.invocation_id for item in credits} == {
        "goal": "8baf7cd9ff6549b49fd1f565a59ad93a",
        "original-message-read": "eb45e8e2c5c648c1bce3fdb9994f3c29",
    }
    assert requests[0]["producer"] == driver.identity.model_dump(mode="json")
    assert exchange["provider_identity"].endswith("authenticated-thread-selection@1")
    result = outputs[0]
    assert result["backend_error"] is None
    evaluation = result["evaluation"]
    assert evaluation["producer"] == driver.identity.model_dump(mode="json")
    assert evaluation["decision_errors"] == []
    assert evaluation["context"]["assistant_closed"] and evaluation["context"]["external_closed"]
    assert evaluation["context"]["invocation_closed"]
    assert len(evaluation["findings"]) == len(exchange["full_output_ids"]) == 3
    assert all(finding["decision"] is not None for finding in evaluation["findings"])
    # Admission/coverage gate only: retain semantic verdict, including legitimate abstention.
    assert evaluation["status"] in {"compliant", "violation", "inapplicable", "abstained"}
    (directory / "result.json").write_text(
        canonical_json(
            {
                "status": "qualified_transport_and_mixed_credit",
                "semantic_accuracy": "unqualified",
                "observed_status": evaluation["status"],
                "observed_compliance": evaluation["compliance"],
                "backend_executions": 1,
                "original_contribution_count": len(credits),
            }
        )
    )
    return trace


def test_mixed_contact_live_gate_fixture_executes_once_and_retains_native_evidence(
    monkeypatch, tmp_path
):
    driver = backend()
    current, calls = [], []

    async def spawn(path):
        return current[0]

    async def execute_once(prepared_context, raw_source, request, context):
        calls.append(request.run.run_id)
        assert len(calls) == 1
        current[:] = [Process(stream(records(prepared_context)))]
        return await driver.execute(prepared_context, raw_source, request, context)

    class FixtureBackend:
        identity = driver.identity
        execute = staticmethod(execute_once)
        parse = staticmethod(driver.parse)

    monkeypatch.setattr(codex_sdk, "_spawn", spawn)
    directory = tmp_path / "attempt"
    _mixed_contact_attempt(monkeypatch, FixtureBackend(), directory)
    assert len(calls) == 1
    assert json.loads((directory / "result.json").read_text())["original_contribution_count"] == 2
    assert (directory / "trace.json").is_file() and (directory / "sdk-events.jsonl").is_file()


@pytest.mark.network
def test_signed_in_no_clarification_backend_live_one_attempt(monkeypatch):
    """Explicit one-attempt schema/provenance gate; no semantic accuracy claim."""
    if os.environ.get("AUTOMATIONBENCH_RUN_SIGNED_IN_NO_CLARIFICATION") != "1":
        pytest.skip("Set AUTOMATIONBENCH_RUN_SIGNED_IN_NO_CLARIFICATION=1 for signed-in gate")
    auth = os.environ.get("AUTOMATIONBENCH_SUMMARY_AUTH_FILE")
    output = os.environ.get("AUTOMATIONBENCH_NO_CLARIFICATION_OUTPUT_DIR")
    if not auth or not output:
        pytest.skip("Explicit private auth path and fresh retained output directory are required")
    auth_path = Path(auth)
    assert auth_path.is_absolute() and auth_path.is_file()
    _mixed_contact_attempt(monkeypatch, CodexSdkNoClarificationBackend(auth_path), Path(output))


@pytest.mark.parametrize("fault", ["missing_proof", "unexpected_image"])
def test_no_clarification_isolation_failure_retains_original_stream(monkeypatch, inputs, fault):
    raw, _, _, _, context = inputs
    values = records(context, semantic_decisions(context))
    if fault == "missing_proof":
        values.pop(5)
    else:
        values.insert(
            -1,
            {
                "kind": "event",
                "event": {
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "item": {
                            "type": "imageGeneration",
                            "id": "image-1",
                            "status": "failed",
                            "result": "",
                            "savedPath": None,
                        },
                    },
                },
            },
        )
    observed = stream(values)
    process, journal = Process(observed), Journal()

    async def spawn(path):
        return process

    monkeypatch.setattr(codex_sdk, "_spawn", spawn)
    driver = backend()
    with pytest.raises(ValueError, match="builtin_tool_isolation|unexpected_tool_or_item"):
        asyncio.run(
            driver.execute(
                context,
                raw,
                SimpleNamespace(run=SimpleNamespace(invocation_id="isolation-attempt")),
                journal,
            )
        )
    retained = next(
        payload for kind, payload, _ in journal.records if kind == policy.CLARIFICATION_SDK_EVENTS
    )
    assert base64.b64decode(retained["raw_base64"]) == observed


def test_actual_failed_image_attempt_remains_unqualified_under_new_transport():
    path = Path(
        "/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/"
        "no-clarification-sdk-live-02/trace.json"
    )
    raw = path.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "7fc55778cd066a0d4d1ea9d85e3d0f4483b0c2a90de93fc3da18997a58b29a10"
    )
    payload = next(
        json.loads(record["payload_json"])
        for batch in json.loads(raw)["assessment_batches"]
        for record in batch["run"]["execution_evidence"]
        if record["kind"] == policy.CLARIFICATION_SDK_EVENTS
    )
    stream_bytes = base64.b64decode(payload["raw_base64"])
    assert (
        hashlib.sha256(stream_bytes).hexdigest()
        == "cf169750cf7d15939a15d9a9d2af8b76df4ea4317e12e9a25b836d2effd0fd76"
    )
    images = [
        record["event"]["params"]["item"]
        for record in map(json.loads, stream_bytes.splitlines())
        if record.get("kind") == "event"
        and record["event"].get("params", {}).get("item", {}).get("type") == "imageGeneration"
    ]
    assert [item["status"] for item in images] == ["in_progress", "failed"]
    assert all(item["result"] == "" and item["savedPath"] is None for item in images)
    with pytest.raises(ValueError, match="builtin_tool_isolation_inventory_invalid"):
        backend()._admit(stream_bytes.decode())
    assert path.read_bytes() == raw
