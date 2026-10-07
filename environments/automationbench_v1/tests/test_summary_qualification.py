"""Frozen semantic scheduling through real native execution, without inference."""

import asyncio
import base64
import hashlib
import json
import zipfile
from pathlib import Path

import pytest
import verifiers.v1 as vf
from test_manifest_summary_assessments import ControlledBackend

from automationbench_v1.calibration import summary_qualification as runner
from automationbench_v1.calibration.summary_cases import (
    SummaryCaseSpec,
    load_summary_replay,
    prepare_summary_case,
)
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.summary_policy import SummaryAssessor
from automationbench_v1.manifest_no_clarification_assessments import (
    NO_CLARIFICATION_EXCHANGE,
    NO_CLARIFICATION_OUTPUT,
    NO_CLARIFICATION_PRODUCER,
    NO_CLARIFICATION_REQUEST,
)
from automationbench_v1.summary_backends.codex_sdk import SDK_EVENTS, CodexSdkSummaryBackend
from automationbench_v1.summary_backends.codex_sdk_no_clarification import CLARIFICATION_SDK_EVENTS

DOCUMENT = Path(
    "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/"
    "reward-candidate/summary-semantic-case-preparation.json"
)


def selection():
    raw = DOCUMENT.read_bytes()
    document = json.loads(raw)
    corpus = Path(document["corpus"]["path"]).read_bytes()
    return runner.SummaryQualificationSelection(
        raw, hashlib.sha256(raw).hexdigest(), corpus, document["corpus"]["sha256"]
    )


@pytest.fixture(scope="module")
def cases():
    document = json.loads(DOCUMENT.read_bytes())
    baseline = load_summary_replay(document)
    identity = CodexSdkSummaryBackend(Path("/not-read/auth.json")).identity
    return tuple(
        prepare_summary_case(baseline, SummaryCaseSpec.model_validate(spec), assessor=identity)
        for spec in document["cases"][:3]
    )


class ObservedBackend(ControlledBackend):
    def __init__(self, identity, directory, *, fail=False, block=False):
        super().__init__(identity, fail_execute=fail)
        self.directory = directory
        self.block = block
        self.active = self.peak = 0
        self.inputs = []
        self.entered = asyncio.Event()

    async def execute(self, prepared, raw_source, request, context):
        starts = [
            json.loads(line)
            for line in (self.directory / "attempts.jsonl").read_text().splitlines()
        ]
        assert any(item["status"] == "started" for item in starts)
        self.inputs.append(canonical_json(raw_source))
        assert "target_state" not in self.inputs[-1]
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.entered.set()
        try:
            result = await super().execute(prepared, raw_source, request, context)
            if self.block:
                await asyncio.Event().wait()
            await asyncio.sleep(0.01)
            return result
        finally:
            self.active -= 1


def run(cases, backend, directory, **kwargs):
    return asyncio.run(
        runner.run_summary_qualification(
            cases, backend=backend, directory=directory, selection=selection(), **kwargs
        )
    )


def test_native_retention_labels_outside_backend_and_resume_no_retry(cases, tmp_path):
    backend = ObservedBackend(cases[0].contract.checks[0].assessor, tmp_path)
    report = run(
        cases[:2],
        backend,
        tmp_path,
    )
    assert report["status"] == "retained" and report["source_unchanged"]
    assert backend.calls == 2 and backend.peak == 2
    assert report["results"][1]["target_agreement"] is False
    assert all(item["backend_executions"] == 1 for item in report["results"])
    replay = run(
        cases[:2],
        backend,
        tmp_path,
        resume=True,
    )
    assert replay["results"] == report["results"] and backend.calls == 2
    with pytest.raises(FileExistsError):
        run(cases[:2], backend, tmp_path)


def test_failure_consumes_attempt_retains_native_request(cases, tmp_path):
    backend = ObservedBackend(cases[0].contract.checks[0].assessor, tmp_path, fail=True)
    report = run(cases[:1], backend, tmp_path)
    assert report["results"][0]["transport_status"] == "failed"
    native = json.loads(next(tmp_path.glob("attempts/*/native-assessments.json")).read_bytes())
    assert any(batch["run"]["execution_evidence"] for batch in native["batches"])
    run(cases[:1], backend, tmp_path, resume=True)
    assert backend.calls == 1


def test_transport_failure_stops_new_slots_but_semantic_failure_does_not(cases, tmp_path):
    backend = ObservedBackend(cases[0].contract.checks[0].assessor, tmp_path, fail=True)
    report = run(cases, backend, tmp_path, max_concurrent=1)
    assert report["stop_reason"] == "assessment_transport_failed"
    assert report["not_started_cases"] == [case.case_id for case in cases[1:]]
    assert backend.calls == 1


def test_rolling_refill_and_independent_campaigns(cases, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    left = ObservedBackend(cases[0].contract.checks[0].assessor, first)
    right = ObservedBackend(cases[0].contract.checks[0].assessor, second)
    left.fail_parse = True

    async def both():
        return await asyncio.gather(
            runner.run_summary_qualification(
                cases, backend=left, directory=first, max_concurrent=2, selection=selection()
            ),
            runner.run_summary_qualification(
                cases[:1], backend=right, directory=second, max_concurrent=10, selection=selection()
            ),
        )

    reports = asyncio.run(both())
    assert left.calls == 3 and left.peak == 2 and right.calls == 1
    assert all(report["status"] == "retained" for report in reports)
    assert all(item["parser_status"] == "failed" for item in reports[0]["results"])


def test_cancellation_retains_started_case_and_never_redispatches(cases, tmp_path):
    backend = ObservedBackend(cases[0].contract.checks[0].assessor, tmp_path, block=True)

    async def cancel():
        owned = asyncio.create_task(
            runner.run_summary_qualification(
                cases[:1], backend=backend, directory=tmp_path, selection=selection()
            )
        )
        await asyncio.wait_for(backend.entered.wait(), timeout=15)
        owned.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owned

    asyncio.run(cancel())
    assert backend.active == 0
    events = [json.loads(line) for line in (tmp_path / "attempts.jsonl").read_text().splitlines()]
    assert events[0]["status"] == "started" and events[-1]["status"] == "interrupted"
    report = run(cases[:1], backend, tmp_path, resume=True)
    assert report["started_cases"] == 1 and len(backend.inputs) == 1


@pytest.mark.parametrize(
    "field,value",
    [("case_id", "other"), ("capture_mode", "retained_actual"), ("target_output_key", "other")],
)
def test_prepared_forgery_rejected_before_reservation(cases, tmp_path, field, value):
    backend = ObservedBackend(cases[0].contract.checks[0].assessor, tmp_path)
    forged = cases[1].model_copy(update={field: value})
    with pytest.raises(ValueError):
        run((forged,), backend, tmp_path)
    assert not (tmp_path / "attempts.jsonl").exists() and not backend.inputs


def test_resume_changes_and_retained_artifact_tamper_rejected(cases, tmp_path):
    backend = ObservedBackend(cases[0].contract.checks[0].assessor, tmp_path)
    run(cases[:1], backend, tmp_path)
    with pytest.raises(ValueError, match="manifest_changed"):
        run(cases[:1], backend, tmp_path, resume=True, max_concurrent=2)
    result = next(tmp_path.glob("attempts/*/result.json"))
    result.write_text("{}")
    with pytest.raises(ValueError, match="artifact_changed"):
        run(cases[:1], backend, tmp_path, resume=True)
    assert backend.calls == 1


@pytest.mark.parametrize("concurrency", [True, 0, 33, 1.0])
def test_strict_scheduler_settings(cases, tmp_path, concurrency):
    backend = ObservedBackend(cases[0].contract.checks[0].assessor, tmp_path)
    with pytest.raises(ValueError):
        run(cases[:1], backend, tmp_path, max_concurrent=concurrency)
    assert not backend.inputs


def test_reviewed_selection_and_label_mutation_rejected(cases, tmp_path):
    selected = selection()
    backend = ObservedBackend(cases[0].contract.checks[0].assessor, tmp_path)
    forged = runner.SummaryQualificationSelection(
        selected.preparation_bytes + b" ",
        selected.preparation_sha256,
        selected.corpus_bytes,
        selected.corpus_sha256,
    )
    with pytest.raises(ValueError, match="selection_changed"):
        asyncio.run(
            runner.run_summary_qualification(
                cases[:1], backend=backend, directory=tmp_path, selection=forged
            )
        )
    with pytest.raises(ValueError, match="labels_not_selected"):
        run(cases[:1], backend, tmp_path, expected_labels={})
    assert not backend.inputs and not (tmp_path / "attempts.jsonl").exists()


def test_clarification_unsupported_population_is_explicit(clarification_campaign):
    cases, approved = clarification_campaign
    preparation, corpus = approved.documents()
    preparation["cases"] = preparation["cases"][:2]
    excluded = corpus["cases"][2]
    preparation["unsupported_cases"] = [
        {
            "case_id": excluded["case_id"],
            "evaluation_case_sha256": runner._digest(excluded),
            "reason": "Required visibility is not captured in this fixture.",
        }
    ]
    unsupported, uncovered = runner._clarification_accounting(preparation, corpus, cases[:1])
    assert [case.case_id for case in unsupported] == [excluded["case_id"]]
    assert uncovered == [cases[1].case_id]


@pytest.mark.parametrize(
    "mutation", ["missing", "overlap", "unknown", "hash", "duplicate", "blank", "bool"]
)
def test_clarification_unsupported_inventory_cannot_hide_cases(clarification_campaign, mutation):
    cases, approved = clarification_campaign
    preparation, corpus = approved.documents()
    excluded = corpus["cases"][2]
    preparation["cases"] = preparation["cases"][:2]
    item = {
        "case_id": excluded["case_id"],
        "evaluation_case_sha256": runner._digest(excluded),
        "reason": "Not reproducible from captured public evidence.",
    }
    preparation["unsupported_cases"] = [item]
    if mutation == "missing":
        preparation["unsupported_cases"] = []
    elif mutation == "overlap":
        item["case_id"] = cases[0].case_id
    elif mutation == "unknown":
        item["case_id"] = "unknown-case"
    elif mutation == "hash":
        item["evaluation_case_sha256"] = "0" * 64
    elif mutation == "duplicate":
        preparation["unsupported_cases"].append(dict(item))
    elif mutation == "blank":
        item["reason"] = " "
    else:
        item["case_id"] = True
    with pytest.raises(ValueError):
        runner._clarification_accounting(preparation, corpus, cases[:1])


def test_clarification_old_success_cannot_mask_current_failure(clarification_campaign, tmp_path):
    cases, approved = clarification_campaign
    selected = (cases[:1], approved)
    histories = []
    for name, fail in (("old", False), ("current", True)):
        directory = tmp_path / name
        backend = ClarificationObservedBackend(
            cases[0].contract.checks[0].assessor, directory, fail=fail
        )
        run_clarification(selected, backend, directory)
        artifact = next(directory.glob("attempts/*/native-assessments.json"))
        histories.extend(
            vf.AssessmentBatch.model_validate_json(canonical_json(batch))
            for batch in json.loads(artifact.read_bytes())["batches"]
        )
    assert {batch.run.status for batch in runner._terminal(histories)} >= {"complete"}
    with pytest.raises(ValueError, match="multiple_assessment_attempts"):
        runner._observation(cases[0], histories, None)


def test_archived_source_tamper_rejected_before_resume(cases, tmp_path):
    backend = ObservedBackend(cases[0].contract.checks[0].assessor, tmp_path)
    run(cases[:1], backend, tmp_path)
    (tmp_path / "source-snapshot.zip").write_bytes(b"not-archive")
    with pytest.raises(zipfile.BadZipFile):
        run(cases[:1], backend, tmp_path, resume=True)
    assert backend.calls == 1


def test_resume_only_never_started_cases_after_unknown_start(cases, tmp_path):
    backend = ObservedBackend(cases[0].contract.checks[0].assessor, tmp_path, fail=True)
    run(cases, backend, tmp_path, max_concurrent=1)
    journal = tmp_path / "attempts.jsonl"
    # Explicit crash fixture: only the original durable start was observed.
    journal.write_bytes(journal.read_bytes().splitlines(keepends=True)[0])
    backend.fail_execute = False
    report = run(cases, backend, tmp_path, max_concurrent=1, resume=True)
    assert backend.calls == 3
    assert report["results"][0]["status"] == "interrupted_unreconciled"
    assert report["started_cases"] == 3 and report["status"] == "incomplete"


def test_frozen_prepared_bytes_rejected_and_campaign_lock_exclusive(cases, tmp_path):
    import fcntl

    backend = ObservedBackend(cases[0].contract.checks[0].assessor, tmp_path)
    run(cases[:1], backend, tmp_path)
    with (tmp_path / ".campaign.lock").open("ab") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            run(cases[:1], backend, tmp_path, resume=True)
    input_path = next(tmp_path.glob("inputs/*.json"))
    raw = json.loads(input_path.read_bytes())
    raw["case_id"] = "other"
    input_path.write_text(canonical_json(raw))
    with pytest.raises(ValueError, match="frozen_case_changed"):
        run(cases[:1], backend, tmp_path, resume=True)
    assert backend.calls == 1


@pytest.fixture(scope="module")
def retained_batch(cases, tmp_path_factory):
    directory = tmp_path_factory.mktemp("runner-history")
    backend = ObservedBackend(cases[0].contract.checks[0].assessor, directory)
    run(cases[:1], backend, directory)
    payload = json.loads(next(directory.glob("attempts/*/native-assessments.json")).read_bytes())
    return vf.AssessmentBatch.model_validate_json(canonical_json(payload["batches"][-1]))


@pytest.mark.parametrize(
    "mutation",
    [
        "rubric",
        "finding",
        "drop_finding",
        "receipt",
        "receipt_reorder",
        "terminal_reason",
        "undeclared_target",
    ],
)
def test_lifecycle_history_rejects_changed_previous_records(retained_batch, mutation):
    baseline = retained_batch.model_copy(
        update={"run": retained_batch.run.model_copy(update={"status": "partial"})}
    )
    changed = retained_batch
    if mutation == "rubric":
        changed = changed.model_copy(
            update={"run": changed.run.model_copy(update={"rubric_revision": "other"})}
        )
    elif mutation == "finding":
        changed = changed.model_copy(
            update={"assessments": (changed.assessments[0].model_copy(update={"reason": "other"}),)}
        )
    elif mutation == "drop_finding":
        changed = changed.model_copy(
            update={"run": changed.run.model_copy(update={"status": "partial"}), "assessments": ()}
        )
    elif mutation == "receipt":
        changed = changed.model_copy(
            update={
                "run": changed.run.model_copy(
                    update={"execution_evidence": changed.run.execution_evidence[1:]}
                )
            }
        )
    elif mutation == "receipt_reorder":
        assert len(changed.run.execution_evidence) >= 2
        changed = changed.model_copy(
            update={
                "run": changed.run.model_copy(
                    update={"execution_evidence": tuple(reversed(changed.run.execution_evidence))}
                )
            }
        )
    elif mutation == "undeclared_target":
        foreign = changed.assessments[0].model_copy(
            update={
                "subject": changed.assessments[0].subject.model_copy(
                    update={"trace_id": "unrequested"}
                )
            }
        )
        changed = changed.model_copy(update={"assessments": (*changed.assessments, foreign)})
    else:
        baseline = retained_batch
        changed = changed.model_copy(
            update={"run": changed.run.model_copy(update={"reason": "other"})}
        )
    with pytest.raises(ValueError):
        runner._terminal((baseline, changed))


def test_append_only_partial_to_terminal_valid(retained_batch):
    partial = retained_batch.model_copy(
        update={
            "run": retained_batch.run.model_copy(
                update={"status": "partial", "execution_evidence": ()}
            ),
            "assessments": (),
        }
    )
    assert runner._terminal((partial, retained_batch, retained_batch)) == (retained_batch,)


@pytest.fixture(scope="module")
def clarification_campaign(tmp_path_factory):
    from automationbench_v1.calibration.no_clarification_cases import (
        prepare_no_clarification_cases,
    )

    directory = tmp_path_factory.mktemp("clarification-review-fixture")
    document = json.loads(DOCUMENT.read_bytes())
    original = json.loads(Path(document["corpus"]["path"]).read_bytes())
    # Explicitly reviewed test recipes; labels are not production model gold.
    original["cases"] = original["cases"][:3]
    document["cases"] = document["cases"][:3]
    for case in original["cases"]:
        case["expected"].update(
            target_state="inapplicable",
            aggregate_status="inapplicable",
            compliance=1,
            reason="Controlled test-driver certificate; no semantic qualification.",
        )
    corpus_bytes = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    corpus_path = directory / "reviewed-corpus.json"
    corpus_path.write_bytes(corpus_bytes)
    document["policy_profile"] = "no_clarification@1"
    document["corpus"] = {
        "path": str(corpus_path),
        "sha256": hashlib.sha256(corpus_bytes).hexdigest(),
        "case_count": 3,
    }
    for spec, case in zip(document["cases"], original["cases"], strict=True):
        spec["evaluation_case_sha256"] = hashlib.sha256(canonical_json(case).encode()).hexdigest()
    preparation_bytes = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()
    approved = runner.SummaryQualificationSelection(
        preparation_bytes,
        hashlib.sha256(preparation_bytes).hexdigest(),
        corpus_bytes,
        hashlib.sha256(corpus_bytes).hexdigest(),
    )
    identity = SummaryAssessor(
        assessor_id="controlled-no-clarification-driver",
        revision="1",
        parser_revision="1",
        rubric_revision="clarification-fixture",
        model_selection_json='{"backend":"controlled_fixture_no_inference"}',
    )
    return prepare_no_clarification_cases(document, assessor=identity), approved


class ClarificationObservedBackend(ObservedBackend):
    def __init__(self, identity, directory, **kwargs):
        super().__init__(identity, directory, **kwargs)
        self.producer = NO_CLARIFICATION_PRODUCER
        self.request_kind = NO_CLARIFICATION_REQUEST

    def parse(self, exchange, prepared):
        if self.fail_parse:
            raise ValueError("controlled clarification parser failure")
        return tuple(
            item.model_copy(
                update={
                    "assessor_id": self.identity.assessor_id,
                    "assessor_revision": self.identity.revision,
                    "state": "inapplicable",
                }
            )
            for item in super().parse(exchange, prepared)
        )


def run_clarification(campaign, backend, directory, **kwargs):
    cases, approved = campaign
    return asyncio.run(
        runner.run_no_clarification_qualification(
            cases, backend=backend, directory=directory, selection=approved, **kwargs
        )
    )


def test_clarification_v2_native_route_and_cross_revision_resume_rejection(
    clarification_campaign, tmp_path
):
    from automationbench_v1.calibration.no_clarification_cases import prepare_no_clarification_cases

    legacy_cases, legacy_selection = clarification_campaign
    legacy_check = legacy_cases[0].contract.checks[0]
    assert isinstance(legacy_check, runner.NoClarificationCheck)
    document, _ = legacy_selection.documents()
    document["policy_profile"] = "no_clarification@2"
    raw = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()
    selected = runner.SummaryQualificationSelection(
        raw,
        hashlib.sha256(raw).hexdigest(),
        legacy_selection.corpus_bytes,
        legacy_selection.corpus_sha256,
    )
    cases = prepare_no_clarification_cases(
        document,
        assessor=legacy_check.assessor,
        policy_profile="no_clarification@2",
    )
    backend = ClarificationObservedBackend(legacy_check.assessor, tmp_path)
    report = run_clarification(
        (cases, selected),
        backend,
        tmp_path,
        policy_profile="no_clarification@2",
        max_concurrent=2,
    )
    manifest_bytes = (tmp_path / "manifest.json").read_bytes()
    assert json.loads(manifest_bytes)["policy_profile"] == "no_clarification@2"
    assert report["planned_runnable_cases"] == 3 and report["unsupported_case_count"] == 0
    assert report["source_unchanged"] and report["status"] == "retained"
    assert backend.calls == 3 and all(row["compliance"] == 1 for row in report["results"])
    resumed = run_clarification(
        (cases, selected),
        backend,
        tmp_path,
        policy_profile="no_clarification@2",
        max_concurrent=2,
        resume=True,
    )
    assert resumed["results"] == report["results"] and backend.calls == 3
    with pytest.raises(ValueError, match="summary_qualification_selected_policy_profile_mismatch"):
        run_clarification((cases, selected), backend, tmp_path, resume=True)
    assert backend.calls == 3 and (tmp_path / "manifest.json").read_bytes() == manifest_bytes


def test_clarification_native_route_retention_and_resume(clarification_campaign, tmp_path):
    cases, _ = clarification_campaign
    backend = ClarificationObservedBackend(cases[0].contract.checks[0].assessor, tmp_path)
    report = run_clarification(clarification_campaign, backend, tmp_path, max_concurrent=2)
    assert backend.calls == 3 and backend.peak == 2
    assert report["status"] == "retained" and report["source_unchanged"]
    assert report["planned_runnable_cases"] == 3
    assert report["unsupported_case_count"] == 0 and report["uncovered_case_ids"] == []
    assert all(result["output_inventory_closed"] is True for result in report["results"])
    assert all(result["aggregate_status"] == "inapplicable" for result in report["results"])
    assert all(
        result["compliance"] == 1 and result["parser_status"] == "retained"
        for result in report["results"]
    )
    assert all(result["target_agreement"] is True for result in report["results"])
    assert (
        json.loads((tmp_path / "manifest.json").read_bytes())["policy_profile"]
        == "no_clarification@1"
    )
    for path in tmp_path.glob("attempts/*/native-assessments.json"):
        retained = tuple(
            vf.AssessmentBatch.model_validate_json(canonical_json(batch))
            for batch in json.loads(path.read_bytes())["batches"]
        )
        current = runner._terminal(retained)
        assert all(batch.run.producer_id == NO_CLARIFICATION_PRODUCER for batch in current)
        assert any(
            record.kind == NO_CLARIFICATION_EXCHANGE
            for batch in current
            for record in batch.run.execution_evidence
        )
        assert any(
            record.kind == NO_CLARIFICATION_OUTPUT
            for batch in current
            for record in batch.run.execution_evidence
        )
    replay = run_clarification(
        clarification_campaign, backend, tmp_path, max_concurrent=2, resume=True
    )
    assert replay["results"] == report["results"] and backend.calls == 3


def test_clarification_failure_stops_queue_and_consumes_attempt(clarification_campaign, tmp_path):
    cases, _ = clarification_campaign
    backend = ClarificationObservedBackend(
        cases[0].contract.checks[0].assessor, tmp_path, fail=True
    )
    report = run_clarification(clarification_campaign, backend, tmp_path, max_concurrent=1)
    assert backend.calls == 1 and report["stop_reason"] == "assessment_transport_failed"
    assert report["not_started_cases"] == [case.case_id for case in cases[1:]]
    retained = json.loads(next(tmp_path.glob("attempts/*/native-assessments.json")).read_bytes())
    assert any(
        record["kind"] == NO_CLARIFICATION_REQUEST
        for batch in retained["batches"]
        for record in batch["run"]["execution_evidence"]
    )
    backend.fail_execute = False
    run_clarification(clarification_campaign, backend, tmp_path, max_concurrent=1, resume=True)
    assert backend.calls == 3  # Failed first case is never retried.


def test_clarification_cancellation_retains_native_partial_history(
    clarification_campaign, tmp_path
):
    cases, approved = clarification_campaign
    backend = ClarificationObservedBackend(
        cases[0].contract.checks[0].assessor, tmp_path, block=True
    )

    async def cancel():
        pending = asyncio.create_task(
            runner.run_no_clarification_qualification(
                cases[:1],
                backend=backend,
                directory=tmp_path,
                selection=approved,
            )
        )
        await asyncio.wait_for(backend.entered.wait(), timeout=15)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

    asyncio.run(cancel())
    events = [json.loads(line) for line in (tmp_path / "attempts.jsonl").read_bytes().splitlines()]
    assert events[0]["status"] == "started" and events[-1]["status"] == "interrupted"
    single = (cases[:1], approved)
    run_clarification(single, backend, tmp_path, resume=True)
    assert backend.calls == 1 and backend.active == 0


def test_summary_and_clarification_routes_cannot_reuse_each_other(
    cases, clarification_campaign, tmp_path
):
    clarification, approved = clarification_campaign
    backend = ClarificationObservedBackend(clarification[0].contract.checks[0].assessor, tmp_path)
    with pytest.raises(ValueError, match="selected_policy_profile_mismatch"):
        asyncio.run(
            runner.run_summary_qualification(
                clarification[:1],
                backend=backend,
                directory=tmp_path,
                selection=approved,
            )
        )
    with pytest.raises(ValueError, match="selected_policy_profile_mismatch"):
        asyncio.run(
            runner.run_no_clarification_qualification(
                cases[:1],
                backend=backend,
                directory=tmp_path,
                selection=selection(),
            )
        )
    assert not backend.inputs and not (tmp_path / "attempts.jsonl").exists()


@pytest.mark.parametrize("policy", ["summary", "clarification"])
@pytest.mark.parametrize("fault", [None, "digest", "base64", "foreign_kind"])
def test_failed_worker_retains_profile_usage_without_success_or_retry(
    cases, clarification_campaign, tmp_path, policy, fault
):
    """Real native evidence retention; controlled worker failure, no inference."""
    selected = cases[:1] if policy == "summary" else clarification_campaign[0][:1]
    own_kind = SDK_EVENTS if policy == "summary" else CLARIFICATION_SDK_EVENTS
    other_kind = CLARIFICATION_SDK_EVENTS if policy == "summary" else SDK_EVENTS
    counts = {
        "inputTokens": 123,
        "cachedInputTokens": 10,
        "cacheWriteInputTokens": 0,
        "outputTokens": 37,
        "reasoningOutputTokens": 11,
        "totalTokens": 160,
    }
    observed = {
        "kind": "event",
        "event": {
            "method": "thread/tokenUsage/updated",
            "params": {"threadId": "failed-fixture-thread", "tokenUsage": {"total": counts}},
        },
    }
    records = [
        {"kind": "thread_started", "response": {"thread": {"id": "failed-fixture-thread"}}},
        observed,
        {"kind": "finished", "ok": False, "status": "failed"},
    ]
    # A complete-looking JSON fragment without its journal newline is not admitted.
    incomplete = {
        **observed,
        "event": {
            **observed["event"],
            "params": {
                "threadId": "failed-fixture-thread",
                "tokenUsage": {"total": {**counts, "outputTokens": 999}},
            },
        },
    }
    raw = (
        "".join(canonical_json(item) + "\n" for item in records) + canonical_json(incomplete)
    ).encode()
    payload = {
        "raw_base64": base64.b64encode(raw).decode(),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    if fault == "digest":
        payload["sha256"] = "0" * 64
    elif fault == "base64":
        payload["raw_base64"] = "%%%not-base64%%%"

    class FailedWorker(ObservedBackend):
        async def execute(self, prepared, raw_source, request, context):
            await super().execute(prepared, raw_source, request, context)
            context.record_evidence(
                other_kind if fault == "foreign_kind" else own_kind,
                payload,
                invocation_id=request.run.invocation_id,
            )
            raise RuntimeError("controlled worker rejected before semantic exchange")

    backend = FailedWorker(selected[0].contract.checks[0].assessor, tmp_path)
    if policy == "clarification":
        backend.producer = NO_CLARIFICATION_PRODUCER
        backend.request_kind = NO_CLARIFICATION_REQUEST

    def execute(*, resume=False):
        if policy == "summary":
            return run(selected, backend, tmp_path, resume=resume)
        return run_clarification(
            (selected, clarification_campaign[1]), backend, tmp_path, resume=resume
        )

    report = execute()
    result = report["results"][0]
    assert result["transport_status"] == "failed"
    assert result["backend_executions"] == 0 and result["usage"] == []
    assert result["compliance"] is None and result["target_state"] == "abstained"
    assert result["parser_status"] == "failed" and result["backend_errors"]
    partial = result["partial_sdk_usage"]
    if fault == "foreign_kind":
        assert partial == []
    elif fault is not None:
        assert partial == [
            {"status": "unavailable", "reason": "ValueError" if fault == "digest" else "Error"}
        ]
    else:
        assert len(partial) == 1 and partial[0]["status"] == "observed"
        assert partial[0]["reported_counts"] == counts
        assert partial[0]["observed_updates"] == 1
        assert partial[0]["observed_output_lower_bound"] == 37
        assert partial[0]["response_accounting"]["status"] == "unavailable"

    retained_path = next(tmp_path.glob("attempts/*/native-assessments.json"))
    retained_bytes = retained_path.read_bytes()
    retained = json.loads(retained_bytes)
    batches = tuple(vf.AssessmentBatch.model_validate(batch) for batch in retained["batches"])
    assert any(
        json.loads(record.payload_json) == payload
        for batch in runner._terminal(batches)
        for record in batch.run.execution_evidence
        if record.kind == (other_kind if fault == "foreign_kind" else own_kind)
    )
    # Reload uses the same observation path and consumes the failed attempt.
    replay = execute(resume=True)
    assert replay["results"] == report["results"] and backend.calls == 1
    assert retained_path.read_bytes() == retained_bytes
