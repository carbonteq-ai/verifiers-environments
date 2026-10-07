"""Authenticated native guard boundaries reject malformed inputs and subjects.

The deliberately altered request identities are validated transport fixtures;
they are not claims that the native source capturer emitted those identities.
"""

import asyncio
import json

import pytest
import verifiers.v1 as vf
from test_manifest_guard_assessments import guard_contract, native_fixture
from test_manifest_guards import create, initial
from test_notification_evidence import run_operations
from verifiers.v1.assessment_runtime import execute_assessment
from verifiers.v1.assessment_source import capture_trace_source

from automationbench_v1 import manifest_assessments
from automationbench_v1.capture import canonical_json
from automationbench_v1.manifest_guard_assessments import assess_guard, parse_guard_config


def requests(monkeypatch):
    contract = guard_contract()
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: contract)
    task, _, trace = native_fixture(run_operations(initial(), [create()]))
    source = capture_trace_source(trace, task_evidence=task.assessment_source(trace))
    planned = [request for _, request in task.assessment_requests(source)]
    return task, source, planned


def assess(task, request, source):
    errors = []

    def produce(request, context):
        try:
            return assess_guard(task, request, context)
        except Exception as error:
            errors.append(error)
            raise

    batch = asyncio.run(execute_assessment(produce, request, source, []))
    if errors:
        assert batch.run.status == "failed" and not batch.assessments
        raise errors[0]
    if batch.run.status != "complete":
        raise ValueError(batch.run.reason)
    return batch.assessments


def replace_target(request, subject, source=None):
    target = request.run.expected[0].model_copy(update={"subject": subject})
    changed = request.model_dump(mode="json")
    changed["run"]["expected"] = [target.model_dump(mode="json")]
    if source is not None:
        changed["source"] = source.model_dump(mode="json")
    return vf.AssessmentRequest.model_validate(changed)


def test_same_invocation_other_origin_cannot_receive_cached_harm(monkeypatch):
    task, source, planned = requests(monkeypatch)
    request = next(item for item in planned if json.loads(item.run.configuration_json)["case"])
    assert assess(task, request, source)[0].value == 1
    original = request.run.expected[0].subject
    assert original.execution is not None
    foreign = original.execution.model_copy(update={"origin": "interceptor"})
    identity = request.source.model_copy(update={"executions": (*request.source.executions, foreign)})
    subject = original.model_copy(update={"execution": foreign})
    changed = replace_target(request, subject, identity)
    with pytest.raises(ValueError, match="does not belong to the supplied source"):
        assess(task, changed, source)


def test_scope_must_use_exact_declared_trace_subject(monkeypatch):
    task, source, planned = requests(monkeypatch)
    request = next(item for item in planned if json.loads(item.run.configuration_json)["case"] is None)
    identity = request.source.model_copy(update={"trace_ids": (*request.source.trace_ids, "other-trace")})
    subject = request.run.expected[0].subject.model_copy(update={"trace_id": "other-trace"})
    changed = replace_target(request, subject, identity)
    with pytest.raises(ValueError, match="does not belong to the supplied source"):
        assess(task, changed, source)


def test_trace_fallback_requires_absent_execution_membership(monkeypatch):
    task, source, planned = requests(monkeypatch)
    request = next(item for item in planned if json.loads(item.run.configuration_json)["case"])
    trace_subject = next(subject for subject in request.views[0].subjects if subject.kind == "trace")
    changed = replace_target(request, trace_subject)
    with pytest.raises(ValueError, match="guard_requested_execution_mismatch"):
        assess(task, changed, source)
    # Capture a distinct, explicitly incomplete provenance selection, then let
    # the real planner construct its trace fallback. Do not forge a context.
    incomplete = vf.SourceSnapshot.capture(
        json.loads(source.source_json), episode_id=source.episode_id,
        nodes=source.nodes, trace_ids=source.trace_ids,
    )
    unavailable = next(request for _, request in task.assessment_requests(incomplete)
                       if json.loads(request.run.configuration_json)["case"])
    record = assess(task, unavailable, incomplete)[0]
    assert record.status == "abstained" and record.value is None
    assert record.reason == "guard_execution_membership_unavailable"


@pytest.mark.parametrize("mutation", ["boolean-count", "negative-count", "extra", "boolean-row", "case-digest"])
def test_strict_config_rejects_malformed_retained_metadata(monkeypatch, mutation):
    task, source, planned = requests(monkeypatch)
    request = next(item for item in planned if json.loads(item.run.configuration_json)["case"])
    config = json.loads(request.run.configuration_json)
    if mutation == "boolean-count":
        config["potential_instances"] = True
    elif mutation == "negative-count":
        config["potential_instances"] = -1
    elif mutation == "extra":
        config["unsupported"] = "value"
    elif mutation == "boolean-row":
        config["case"]["candidate_identity"][-1] = True
    else:
        config["case"]["instance_key"] = "0" * 64
    with pytest.raises(ValueError):
        parse_guard_config(canonical_json(config))
    malformed = request.model_copy(update={"run": request.run.model_copy(update={"configuration_json": canonical_json(config)})})
    with pytest.raises(ValueError):
        assess(task, malformed, source)
