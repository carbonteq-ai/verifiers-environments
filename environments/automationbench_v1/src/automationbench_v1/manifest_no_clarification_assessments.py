"""Public no-clarification guard, initially outcome-only."""

import json

import verifiers.v1 as vf

from .contracts.no_clarification import (
    NoClarificationCheck,
    evaluate_no_clarification_policy,
    prepare_no_clarification_context,
)
from .manifest_summary_assessments import (
    _assess_output_policy,
    _output_policy_requests,
    _OutputPolicyProfile,
)

NO_CLARIFICATION_PRODUCER = "automationbench.manifest_no_clarification"
NO_CLARIFICATION_OUTPUT = "automationbench.manifest_no_clarification_result@1"
NO_CLARIFICATION_EXCHANGE = "automationbench.no_clarification_semantic_exchange@1"
NO_CLARIFICATION_REQUEST = "automationbench.no_clarification_semantic_request@1"


def no_clarification_signal(check):
    return vf.SignalDefinition(
        signal_id=check.signal_id,
        revision="1",
        semantics="outcome",
        description="Public no-clarification guard compliance",
        units="binary",
        minimum=0,
        maximum=1,
        direction="higher",
    )


def no_clarification_targets(source, raw, contract, check):
    subject = vf.SubjectRef(
        kind="trace",
        snapshot_id=source.snapshot_id,
        episode_id=source.episode_id,
        trace_id=json.loads(source.source_json)["trace_id"],
    )
    return (vf.AssessmentTarget(subject=subject, signal=no_clarification_signal(check)),)


def _profile():
    return _OutputPolicyProfile(
        NoClarificationCheck,
        NO_CLARIFICATION_PRODUCER,
        NO_CLARIFICATION_OUTPUT,
        NO_CLARIFICATION_EXCHANGE,
        NO_CLARIFICATION_REQUEST,
        "no_clarification_backends",
        no_clarification_signal,
        no_clarification_targets,
        prepare_no_clarification_context,
        evaluate_no_clarification_policy,
    )


def no_clarification_requests(source, contract, view):
    return _output_policy_requests(source, contract, view, _profile())


async def assess_no_clarification(task, request, context):
    return await _assess_output_policy(task, request, context, _profile())
