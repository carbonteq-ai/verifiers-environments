"""Bounded, artifact-first semantic assessment of frozen prepared cases.

Run this module directly; it does not collect solver rollouts or alter catalogs.
Expected labels are reporting inputs, never assessment or backend inputs.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import math
import os
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import verifiers.v1 as vf
from pydantic import StrictStr
from verifiers.v1.assessment_runtime import execute_assessment_plan

from ..capture import canonical_json
from ..contracts.base import FrozenModel, Identifier
from ..contracts.no_clarification import NoClarificationCheck
from ..contracts.summary_policy import SummaryAssessor, SummaryEvaluation, SummaryExclusionCheck
from ..contracts.tables import Digest
from ..manifest_assessments import ManifestAssessmentTask
from ..manifest_no_clarification_assessments import (
    NO_CLARIFICATION_EXCHANGE,
    NO_CLARIFICATION_OUTPUT,
    NO_CLARIFICATION_PRODUCER,
    assess_no_clarification,
    no_clarification_requests,
)
from ..manifest_summary_assessments import (
    SUMMARY_EXCHANGE,
    SUMMARY_OUTPUT,
    SUMMARY_PRODUCER,
    SummaryBackend,
    assess_summary,
    summary_requests,
)
from ..summary_backends.codex_sdk import BUDGET, SDK_EVENTS
from ..summary_backends.codex_sdk_no_clarification import CLARIFICATION_SDK_EVENTS
from ..taskset import AutomationBenchData, AutomationBenchTaskConfig
from .budgets import retain_sdk_budget
from .collector import _write_native
from .source import source_identity

if TYPE_CHECKING:
    from .summary_cases import PreparedSummaryCase


@dataclass(frozen=True)
class _QualificationProfile:
    """Two environment-owned routes; declarations cannot register callbacks."""

    name: Literal["summary_exclusions@1", "no_clarification@1", "no_clarification@2"]
    check_type: type[SummaryExclusionCheck | NoClarificationCheck]
    producer: str
    output_kind: str
    exchange_kind: str
    sdk_events_kind: str
    backend_registry: str
    requests: Callable[..., Any]
    assess: Callable[..., Any]


def _profile(name="summary_exclusions@1"):
    if name == "summary_exclusions@1":
        return _QualificationProfile(
            "summary_exclusions@1",
            SummaryExclusionCheck,
            SUMMARY_PRODUCER,
            SUMMARY_OUTPUT,
            SUMMARY_EXCHANGE,
            SDK_EVENTS,
            "summary_backends",
            summary_requests,
            assess_summary,
        )
    if name in {"no_clarification@1", "no_clarification@2"}:
        return _QualificationProfile(
            cast(Literal["no_clarification@1", "no_clarification@2"], name),
            NoClarificationCheck,
            NO_CLARIFICATION_PRODUCER,
            NO_CLARIFICATION_OUTPUT,
            NO_CLARIFICATION_EXCHANGE,
            CLARIFICATION_SDK_EVENTS,
            "no_clarification_backends",
            no_clarification_requests,
            assess_no_clarification,
        )
    raise ValueError("summary_qualification_policy_profile_unknown")


def _case_profile(case):
    document = json.loads(case.preparation_document_json)
    profile = _profile(document.get("policy_profile", "summary_exclusions@1"))
    if (
        len(case.contract.checks) != 1
        or type(case.contract.checks[0]) is not profile.check_type
        or case.contract.checks[0].operator != profile.name
    ):
        raise ValueError("summary_qualification_case_policy_profile_mismatch")
    return profile


def _validate_case(case, profile):
    if profile.name == "summary_exclusions@1":
        from .summary_cases import validate_prepared_summary_case

        return validate_prepared_summary_case(case)
    from .no_clarification_cases import validate_prepared_no_clarification_case

    return validate_prepared_no_clarification_case(case, policy_profile=profile.name)


class _UnsupportedCase(FrozenModel):
    case_id: Identifier
    evaluation_case_sha256: Digest
    reason: StrictStr


def _clarification_accounting(preparation, corpus, cases):
    raw = preparation.get("unsupported_cases", [])
    if type(raw) is not list or any(type(item) is not dict for item in raw):
        raise ValueError("summary_qualification_unsupported_inventory_invalid")
    unsupported = tuple(_UnsupportedCase.model_validate(item) for item in raw)
    expected = {case["case_id"]: case for case in corpus["cases"]}
    runnable = {case["case_id"] for case in preparation["cases"]}
    unavailable = {case.case_id for case in unsupported}
    selected = {case.case_id for case in cases}
    if (
        len(unavailable) != len(unsupported)
        or runnable & unavailable
        or runnable | unavailable != set(expected)
        or not selected <= runnable
        or any(
            not case.reason.strip()
            or case.evaluation_case_sha256 != _digest(expected.get(case.case_id))
            for case in unsupported
        )
    ):
        raise ValueError("summary_qualification_corpus_population_unaccounted")
    return unsupported, sorted(runnable - selected)


@dataclass(frozen=True)
class SummaryQualificationSelection:
    """Caller-reviewed exact file selection, independent of prepared artifacts."""

    preparation_bytes: bytes
    preparation_sha256: str
    corpus_bytes: bytes
    corpus_sha256: str

    def documents(self):
        for raw, expected in (
            (self.preparation_bytes, self.preparation_sha256),
            (self.corpus_bytes, self.corpus_sha256),
        ):
            if (
                type(raw) is not bytes
                or type(expected) is not str
                or hashlib.sha256(raw).hexdigest() != expected
            ):
                raise ValueError("summary_qualification_reviewed_selection_changed")
        preparation, corpus = json.loads(self.preparation_bytes), json.loads(self.corpus_bytes)
        if (
            type(preparation) is not dict
            or type(corpus) is not dict
            or preparation["corpus"]["sha256"] != self.corpus_sha256
        ):
            raise ValueError("summary_qualification_reviewed_corpus_mismatch")
        for document in (preparation, corpus):
            ids = [case["case_id"] for case in document["cases"]]
            if len(ids) != len(set(ids)):
                raise ValueError("summary_qualification_reviewed_duplicate_case")
        return preparation, corpus


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _read(path, digest):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("summary_qualification_artifact_changed")
    return json.loads(raw)


def _verify_source_snapshot(path, source):
    expected = {
        f"{package}/{name}": digest
        for package, metadata in source["packages"].items()
        for name, digest in metadata["files"].items()
    }
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != len(expected) or set(archive.namelist()) != set(expected):
            raise ValueError("summary_qualification_source_archive_inventory_changed")
        if any(
            hashlib.sha256(archive.read(name)).hexdigest() != digest
            for name, digest in expected.items()
        ):
            raise ValueError("summary_qualification_source_archive_changed")


def _terminal(batches):
    terminal = {}
    for batch in batches:
        batch = vf.AssessmentBatch.model_validate(batch.model_dump(mode="python"))
        previous = terminal.get(batch.run.run_id)
        if (
            previous is not None
            and previous.run.status in {"complete", "failed", "interrupted"}
            and previous.model_dump_json() != batch.model_dump_json()
        ):
            raise ValueError("summary_qualification_terminal_history_conflict")
        if previous is not None:
            mutable = {"status", "reason", "execution_evidence", "output_evidence"}
            if (
                canonical_json(previous.run.model_dump(mode="json", exclude=mutable))
                != canonical_json(batch.run.model_dump(mode="json", exclude=mutable))
                or previous.source != batch.source
                or previous.views != batch.views
                or previous.dependencies != batch.dependencies
                or previous.assessments != batch.assessments[: len(previous.assessments)]
                or previous.run.execution_evidence
                != batch.run.execution_evidence[: len(previous.run.execution_evidence)]
                or previous.run.output_evidence
                != batch.run.output_evidence[: len(previous.run.output_evidence)]
                or previous.run.status == "partial"
                and batch.run.status in {"queued", "running"}
                or previous.run.status == "running"
                and batch.run.status == "queued"
            ):
                raise ValueError("summary_qualification_append_history_conflict")
        terminal[batch.run.run_id] = batch
    return tuple(terminal.values())


def _observation(case, batches, error):
    """Separate capture, semantic parsing, target, and aggregate observations."""
    terminal = _terminal(batches)
    profile = _case_profile(case)
    if len(terminal) > 1:
        raise ValueError("summary_qualification_multiple_assessment_attempts")
    if any(batch.run.producer_id != profile.producer for batch in terminal):
        raise ValueError("summary_qualification_native_policy_producer_changed")
    records = [record for batch in terminal for record in batch.run.execution_evidence]
    outputs = [
        json.loads(record.payload_json) for record in records if record.kind == profile.output_kind
    ]
    exchanges = [
        json.loads(record.payload_json)
        for record in records
        if record.kind == profile.exchange_kind
    ]
    actual = [item["exchange"] for item in exchanges if "exchange" in item]
    evaluations = [
        SummaryEvaluation.model_validate_json(canonical_json(item["evaluation"]))
        for item in outputs
        if "evaluation" in item
    ]
    evaluation = evaluations[0] if len(evaluations) == 1 else None
    target = (
        next(
            (item for item in evaluation.findings if item.output_key == case.target_output_key),
            None,
        )
        if evaluation
        else None
    )
    usages = [json.loads(item["usage_json"]) for item in actual]
    partial_usage = []
    if not actual:
        for record in records:
            if record.kind != profile.sdk_events_kind:
                continue
            payload = json.loads(record.payload_json)
            try:
                raw = base64.b64decode(payload["raw_base64"], validate=True)
                if hashlib.sha256(raw).hexdigest() != payload["sha256"]:
                    raise ValueError("raw_digest_changed")
                lines = raw.splitlines(keepends=True)
                observed = [json.loads(line) for line in lines if line.endswith(b"\n")]
                holder = {"codex_sdk": {"events": observed, "fresh_thread_requested": True}}
                retain_sdk_budget(holder, BUDGET)
                partial_usage.append(holder.get("automationbench_output_budget", {}))
            except (ValueError, KeyError, TypeError) as caught:
                partial_usage.append({"status": "unavailable", "reason": type(caught).__name__})
    failed = error is not None or any(
        batch.run.status in {"failed", "interrupted"} for batch in terminal
    )
    transport = "failed" if failed else ("retained" if actual else "not_dispatched_or_unavailable")
    # A retained exchange can still have an invalid answer. Do not turn this
    # into transport success plus an invented semantic certificate.
    backend_errors = [item.get("backend_error") for item in outputs if item.get("backend_error")]
    if any("error" in item for item in exchanges) and not actual:
        transport = "failed"
    result = {
        "transport_status": transport,
        "backend_executions": len(actual),
        "parser_status": "failed"
        if backend_errors
        else (
            "partial"
            if evaluation and evaluation.decision_errors
            else "retained"
            if evaluation and evaluation.producer
            else "not_dispatched_or_unavailable"
        ),
        "backend_errors": backend_errors,
        "target_present": target is not None,
        "target_output_key": case.target_output_key,
        "target_state": target.state if target else None,
        "aggregate_status": evaluation.status
        if evaluation
        else (outputs[0].get("status") if len(outputs) == 1 else None),
        "compliance": evaluation.compliance if evaluation else None,
        "abstained_outputs": sum(item.state == "abstained" for item in evaluation.findings)
        if evaluation
        else None,
        "decision_errors": list(evaluation.decision_errors) if evaluation else [],
        "usage": usages,
        "partial_sdk_usage": partial_usage,
        "usage_note": "Reasoning is reported separately; it is not added again to outputTokens.",
        "error_type": type(error).__name__ if error else None,
    }
    if profile.name in {"no_clarification@1", "no_clarification@2"}:
        context = evaluation.context if evaluation else None
        result["output_inventory_closed"] = (
            context.assistant_closed and context.external_closed and context.invocation_closed
            if context
            else None
        )
        result["coverage_reasons"] = list(context.coverage_reasons) if context else None
    return result


class _Journal:
    """One locked campaign owner; starts consume attempts even after a crash."""

    def __init__(self, directory, manifest_digest, cases):
        self.path = directory / "attempts.jsonl"
        self.manifest_digest = manifest_digest
        self.events = []
        self.latest = {}
        self.cases = {case["case_digest"]: case["case_id"] for case in cases}
        if self.path.exists():
            raw = self.path.read_bytes()
            if raw and not raw.endswith(b"\n"):
                raise ValueError("summary_qualification_incomplete_journal_tail")
            for line in raw.splitlines():
                self._accept(json.loads(line))

    def _accept(self, event, *, retain=True):
        if (
            type(event) is not dict
            or event.get("manifest_digest") != self.manifest_digest
            or type(event.get("sequence")) is not int
            or event["sequence"] != len(self.events)
            or type(event.get("status")) is not str
            or event.get("status") not in {"started", "retained", "failed", "interrupted"}
            or type(event.get("case_digest")) is not str
            or event.get("case_digest") not in self.cases
            or event.get("case_id") != self.cases.get(event.get("case_digest"))
            or type(event.get("recorded_at_unix")) not in (int, float)
            or not math.isfinite(event["recorded_at_unix"])
            or event.get("attempt_id")
            != _digest(
                {"manifest": self.manifest_digest, "case": event["case_digest"], "occurrence": 0}
            )
        ):
            raise ValueError("summary_qualification_journal_identity_invalid")
        if event["status"] != "started" and (
            event.get("result_path") != f"attempts/{event['case_digest']}/result.json"
            or type(event.get("result_digest")) is not str
            or len(event["result_digest"]) != 64
        ):
            raise ValueError("summary_qualification_journal_artifact_invalid")
        old = self.latest.get(event["case_digest"])
        if (
            old is None
            and event["status"] != "started"
            or old is not None
            and (old["status"] != "started" or event["status"] == "started")
        ):
            raise ValueError("summary_qualification_attempt_reuse")
        if retain:
            self.events.append(event)
            self.latest[event["case_digest"]] = event

    def append(self, case, status, **values):
        event = {
            "sequence": len(self.events),
            "manifest_digest": self.manifest_digest,
            "attempt_id": _digest(
                {"manifest": self.manifest_digest, "case": case.case_digest, "occurrence": 0}
            ),
            "case_id": case.case_id,
            "case_digest": case.case_digest,
            "status": status,
            "recorded_at_unix": time.time(),
            **values,
        }
        self._accept(event, retain=False)
        with self.path.open("ab") as stream:
            stream.write((canonical_json(event) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        self._accept(event)
        return event


def _report(manifest, journal, directory, expected_labels):
    results = []
    for event in journal.latest.values():
        if "result_digest" not in event:
            results.append(
                {
                    "case_id": event["case_id"],
                    "status": "interrupted_unreconciled",
                    "attempt_id": event["attempt_id"],
                }
            )
            continue
        result = _read(directory / event["result_path"], event["result_digest"])
        if (
            result.get("case_digest") != event["case_digest"]
            or result.get("case_id") != event["case_id"]
            or result.get("status") != event["status"]
            or result.get("native_path")
            != f"attempts/{event['case_digest']}/native-assessments.json"
        ):
            raise ValueError("summary_qualification_result_identity_invalid")
        native = _read(directory / result["native_path"], result["native_digest"])
        batches = tuple(
            vf.AssessmentBatch.model_validate_json(canonical_json(batch))
            for batch in native["batches"]
        )
        from .summary_cases import PreparedSummaryCase

        case = PreparedSummaryCase.model_validate_json(
            (directory / "inputs" / (event["case_digest"] + ".json")).read_bytes()
        )
        profile = _case_profile(case)
        case = _validate_case(case, profile)
        expected_request = profile.requests(case.source, case.contract, case.view)[0][1]
        if any(
            batch.source != case.source
            or batch.views != (case.view,)
            or batch.dependencies
            or any(
                getattr(batch.run, field) != getattr(expected_request.run, field)
                for field in (
                    "configuration_json",
                    "rubric_revision",
                    "producer_id",
                    "producer_revision",
                    "expected",
                )
            )
            for batch in batches
        ):
            raise ValueError("summary_qualification_native_artifact_case_mismatch")
        _terminal(batches)
        derived = _observation(case, batches, RuntimeError() if result["error_type"] else None)
        if any(
            canonical_json(result.get(key)) != canonical_json(value)
            for key, value in derived.items()
            if key != "error_type"
        ):
            raise ValueError("summary_qualification_result_native_observation_changed")
        expected = expected_labels.get(event["case_id"])
        result["expected"] = expected
        result["target_agreement"] = (
            (result["target_state"] == expected.get("target_state"))
            if expected and result["target_present"]
            else None
        )
        result["aggregate_agreement"] = (
            (result["aggregate_status"] == expected.get("aggregate_status")) if expected else None
        )
        results.append(result)
    report = {
        "schema_version": 1,
        "manifest_digest": _digest(manifest),
        "status": "retained"
        if len(journal.latest) == len(manifest["cases"])
        and all("result_digest" in event for event in journal.latest.values())
        else "incomplete",
        "planned_cases": len(manifest["cases"]),
        "started_cases": len(journal.latest),
        "labels_scope": "Reviewed proposal agreement; not human gold or general semantic accuracy.",
        "results": results,
    }
    if manifest.get("policy_profile") in {"no_clarification@1", "no_clarification@2"}:
        report["planned_runnable_cases"] = len(manifest["cases"])
        report["unsupported_cases"] = manifest["unsupported_cases"]
        report["unsupported_case_count"] = len(manifest["unsupported_cases"])
        report["unsupported_case_ids"] = [case["case_id"] for case in manifest["unsupported_cases"]]
        report["uncovered_case_ids"] = manifest["uncovered_case_ids"]
        report["uncovered_case_count"] = len(manifest["uncovered_case_ids"])
        report["corpus_cases"] = (
            report["planned_runnable_cases"]
            + report["unsupported_case_count"]
            + report["uncovered_case_count"]
        )
    return report


async def _run_output_policy_qualification(
    cases: tuple[PreparedSummaryCase, ...],
    *,
    backend: SummaryBackend,
    selection: SummaryQualificationSelection,
    directory: Path,
    max_concurrent: int = 10,
    max_elapsed_seconds: float = 900,
    expected_labels: dict | None = None,
    resume: bool = False,
    profile: _QualificationProfile,
) -> dict:
    """Run one attempt per case, resuming only never-started frozen cases."""
    import fcntl

    if type(max_concurrent) is not int or not 1 <= max_concurrent <= 32:
        raise ValueError("summary_qualification_concurrency_invalid")
    if (
        type(max_elapsed_seconds) not in (int, float)
        or not math.isfinite(max_elapsed_seconds)
        or max_elapsed_seconds <= 0
    ):
        raise ValueError("summary_qualification_deadline_invalid")
    if type(resume) is not bool or not cases:
        raise ValueError("summary_qualification_cases_or_resume_invalid")
    preparation, corpus = selection.documents()
    if preparation.get("policy_profile", "summary_exclusions@1") != profile.name:
        raise ValueError("summary_qualification_selected_policy_profile_mismatch")
    if any(case.preparation_document_json != canonical_json(preparation) for case in cases):
        raise ValueError("summary_qualification_preparation_not_selected")
    cases = tuple(_validate_case(case, profile) for case in cases)
    for case in cases:
        AutomationBenchData.model_validate_json(case.task_data_json)
        AutomationBenchTaskConfig.model_validate_json(case.task_config_json)
    if len({case.case_id for case in cases}) != len(cases) or len(
        {case.case_digest for case in cases}
    ) != len(cases):
        raise ValueError("summary_qualification_duplicate_case")
    identity = SummaryAssessor.model_validate(
        backend.identity.model_dump(mode="python"), strict=True
    )
    if any(
        len(case.contract.checks) != 1
        or not isinstance(case.contract.checks[0], (SummaryExclusionCheck, NoClarificationCheck))
        or type(case.contract.checks[0]) is not profile.check_type
        or _case_profile(case) != profile
        or case.contract.checks[0].assessor != identity
        for case in cases
    ):
        raise ValueError("summary_qualification_backend_selection_mismatch")
    corpus_labels = {case["case_id"]: case["expected"] for case in corpus["cases"]}
    labels = {case.case_id: corpus_labels[case.case_id] for case in cases}
    if expected_labels is not None and canonical_json(expected_labels) != canonical_json(labels):
        raise ValueError("summary_qualification_labels_not_selected")
    labels = json.loads(canonical_json(labels))
    if type(labels) is not dict or not set(labels) <= {case.case_id for case in cases}:
        raise ValueError("summary_qualification_labels_invalid")
    source = source_identity()
    frozen_cases = [
        {
            "case_id": case.case_id,
            "case_digest": case.case_digest,
            "prepared_digest": _digest(case.model_dump(mode="json")),
        }
        for case in cases
    ]
    manifest = {
        "schema_version": 1,
        "source_identity": source,
        "backend": identity.model_dump(mode="json"),
        "cases": frozen_cases,
        "max_concurrent": max_concurrent,
        "max_elapsed_seconds": max_elapsed_seconds,
        "attempts_per_case": 1,
        "preparation_sha256": selection.preparation_sha256,
        "corpus_sha256": selection.corpus_sha256,
        "expected_labels_digest": _digest(labels),
    }
    if profile.name != "summary_exclusions@1":
        manifest["policy_profile"] = profile.name
        unsupported, uncovered = _clarification_accounting(preparation, corpus, cases)
        manifest["unsupported_cases"] = [case.model_dump(mode="json") for case in unsupported]
        manifest["uncovered_case_ids"] = uncovered
    manifest_digest = _digest(manifest)
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".campaign.lock").open("ab") as ownership:
        fcntl.flock(ownership.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest_path = directory / "manifest.json"
        if manifest_path.exists():
            if not resume:
                raise FileExistsError("summary_qualification_campaign_exists")
            if json.loads(manifest_path.read_bytes()) != manifest:
                raise ValueError("summary_qualification_resume_manifest_changed")
        else:
            if resume or any(path.name != ".campaign.lock" for path in directory.iterdir()):
                raise ValueError("summary_qualification_unowned_or_missing_campaign")
            _write_native(manifest_path, manifest)
            _write_native(directory / "labels.json", labels)
            if source_identity(directory / "source-snapshot.zip") != source:
                raise ValueError("summary_qualification_source_changed_during_snapshot")
            for case in cases:
                _write_native(
                    directory / "inputs" / (case.case_digest + ".json"),
                    case.model_dump(mode="json"),
                )
        _verify_source_snapshot(directory / "source-snapshot.zip", source)
        journal = _Journal(directory, manifest_digest, frozen_cases)
        for case in cases:
            saved = json.loads((directory / "inputs" / (case.case_digest + ".json")).read_bytes())
            if _digest(saved) != next(
                item["prepared_digest"] for item in frozen_cases if item["case_id"] == case.case_id
            ):
                raise ValueError("summary_qualification_frozen_case_changed")
        _report(
            manifest, journal, directory, labels
        )  # Revalidate every retained artifact before resume.
        first = journal.events[0]["recorded_at_unix"] if journal.events else time.time()
        remaining = max(0, first + max_elapsed_seconds - time.time())
        deadline = time.monotonic() + remaining
        pending = [case for case in cases if case.case_digest not in journal.latest]
        active = set()
        source_changed = False
        stop_reason = None

        async def run(case):
            batches, error = [], None
            try:
                task = ManifestAssessmentTask(
                    AutomationBenchData.model_validate_json(case.task_data_json),
                    AutomationBenchTaskConfig.model_validate_json(case.task_config_json),
                )
                setattr(task, profile.backend_registry, {identity.assessor_id: backend})

                async def hook(request, context):
                    return await profile.assess(task, request, context)

                async with asyncio.timeout(max(0, deadline - time.monotonic())):
                    requests = profile.requests(case.source, case.contract, case.view)
                    await execute_assessment_plan(
                        {"manifest_check": hook},
                        requests,
                        case.source,
                        batches,
                        max_concurrent=1,
                    )
            except (Exception, asyncio.CancelledError) as caught:  # noqa: BLE001 - retain owned failed attempts
                error = caught
            result = _observation(case, batches, error)
            attempt_dir = Path("attempts") / case.case_digest
            native_path = attempt_dir / "native-assessments.json"
            native_digest = _write_native(
                directory / native_path,
                {"batches": [batch.model_dump(mode="json") for batch in batches]},
            )
            # Fresh public model validation, including every lifecycle snapshot.
            for batch in json.loads((directory / native_path).read_bytes())["batches"]:
                vf.AssessmentBatch.model_validate_json(canonical_json(batch))
            status = (
                "interrupted"
                if isinstance(error, asyncio.CancelledError)
                else "failed"
                if error or result["transport_status"] == "failed"
                else "retained"
            )
            result.update(
                case_id=case.case_id,
                case_digest=case.case_digest,
                status=status,
                native_path=str(native_path),
                native_digest=native_digest,
            )
            result_path = attempt_dir / "result.json"
            result_digest = _write_native(directory / result_path, result)
            journal.append(case, status, result_path=str(result_path), result_digest=result_digest)
            if isinstance(error, asyncio.CancelledError):
                raise error
            return result

        try:
            while pending or active:
                while pending and len(active) < min(max_concurrent, len(cases)):
                    if time.monotonic() >= deadline:
                        stop_reason = "campaign_deadline_reached"
                        pending.clear()
                        break
                    if source_identity() != source or backend.identity != identity:
                        source_changed = True
                        stop_reason = "source_or_backend_identity_changed"
                        pending.clear()
                        break
                    case = pending.pop(0)
                    journal.append(case, "started")  # Durable reservation before the first await.
                    active.add(asyncio.create_task(run(case)))
                if active:
                    completed, active = await asyncio.wait(
                        active, return_when=asyncio.FIRST_COMPLETED
                    )
                    for finished in completed:
                        if finished.result()["transport_status"] == "failed":
                            stop_reason = "assessment_transport_failed"
                            pending.clear()
        finally:
            for owned in active:
                owned.cancel()
            if active:
                await asyncio.gather(*active, return_exceptions=True)
            report = _report(manifest, journal, directory, labels)
            report["source_unchanged"] = source_identity() == source and not source_changed
            report["stop_reason"] = stop_reason
            report["not_started_cases"] = [
                case.case_id for case in cases if case.case_digest not in journal.latest
            ]
            report["retained_file_bytes"] = sum(
                path.stat().st_size for path in directory.rglob("*") if path.is_file()
            )
            # New immutable report per invocation; resumed runs never overwrite.
            _write_native(
                directory
                / ("report-" + str(len(tuple(directory.glob("report-*.json")))) + ".json"),
                report,
            )
        return report


async def run_summary_qualification(
    cases: tuple[PreparedSummaryCase, ...],
    *,
    backend: SummaryBackend,
    selection: SummaryQualificationSelection,
    directory: Path,
    max_concurrent: int = 10,
    max_elapsed_seconds: float = 900,
    expected_labels: dict | None = None,
    resume: bool = False,
) -> dict:
    return await _run_output_policy_qualification(
        cases,
        backend=backend,
        selection=selection,
        directory=directory,
        max_concurrent=max_concurrent,
        max_elapsed_seconds=max_elapsed_seconds,
        expected_labels=expected_labels,
        resume=resume,
        profile=_profile(),
    )


async def run_no_clarification_qualification(
    cases: tuple[PreparedSummaryCase, ...],
    *,
    backend: SummaryBackend,
    selection: SummaryQualificationSelection,
    directory: Path,
    max_concurrent: int = 10,
    max_elapsed_seconds: float = 900,
    expected_labels: dict | None = None,
    resume: bool = False,
    policy_profile: Literal["no_clarification@1", "no_clarification@2"] = "no_clarification@1",
) -> dict:
    return await _run_output_policy_qualification(
        cases,
        backend=backend,
        selection=selection,
        directory=directory,
        max_concurrent=max_concurrent,
        max_elapsed_seconds=max_elapsed_seconds,
        expected_labels=expected_labels,
        resume=resume,
        profile=_profile(policy_profile),
    )


def _main(profile):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument(
        "--preparation-sha256", required=True, help="Reviewed preparation file SHA256"
    )
    parser.add_argument("--corpus-sha256", required=True, help="Reviewed labels file SHA256")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--auth-file", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--total-timeout", type=float, default=900)
    parser.add_argument("--resume", action="store_true")
    if profile.name != "summary_exclusions@1":
        parser.add_argument(
            "--policy-profile",
            choices=("no_clarification@1", "no_clarification@2"),
            default=profile.name,
            help="Explicit admission revision; archived selections are not upgraded",
        )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Explicitly dispatch the signed-in assessment backend",
    )
    args = parser.parse_args()
    if profile.name != "summary_exclusions@1":
        profile = _profile(args.policy_profile)
    if not args.execute:
        parser.error("--execute is required; importing or inspecting this module never dispatches")
    from .summary_cases import PreparedSummaryCase

    if profile.name == "summary_exclusions@1":
        from ..summary_backends import CodexSdkSummaryBackend
        from .summary_cases import prepare_summary_cases

        backend = CodexSdkSummaryBackend(args.auth_file.expanduser().resolve())
        prepare_cases = prepare_summary_cases
        run = run_summary_qualification
    else:
        from ..summary_backends import CodexSdkNoClarificationBackend
        from .no_clarification_cases import prepare_no_clarification_cases

        backend = CodexSdkNoClarificationBackend(args.auth_file.expanduser().resolve())
        prepare_cases = partial(prepare_no_clarification_cases, policy_profile=profile.name)
        run = partial(run_no_clarification_qualification, policy_profile=profile.name)

    if not backend.auth_file.is_file():
        parser.error("protected authentication file is unavailable")
    document = _read(args.cases, args.preparation_sha256)
    selection = SummaryQualificationSelection(
        args.cases.read_bytes(),
        args.preparation_sha256,
        Path(document["corpus"]["path"]).read_bytes(),
        args.corpus_sha256,
    )
    selection.documents()
    if args.resume:
        manifest = json.loads((args.output_dir / "manifest.json").read_bytes())
        cases = tuple(
            PreparedSummaryCase.model_validate_json(
                (args.output_dir / "inputs" / (item["case_digest"] + ".json")).read_bytes()
            )
            for item in manifest["cases"]
        )
        if any(case.preparation_document_json != canonical_json(document) for case in cases):
            raise ValueError("summary_qualification_resume_preparation_changed")
    else:
        cases = prepare_cases(document, assessor=backend.identity)
    report = asyncio.run(
        run(
            cases,
            backend=backend,
            selection=selection,
            directory=args.output_dir,
            max_concurrent=args.concurrency,
            max_elapsed_seconds=args.total_timeout,
            resume=args.resume,
        )
    )
    print(
        canonical_json(
            {
                "status": report["status"],
                "planned_cases": report["planned_cases"],
                "started_cases": report["started_cases"],
                "source_unchanged": report["source_unchanged"],
            }
        )
    )


def main():
    _main(_profile())


if __name__ == "__main__":
    main()
