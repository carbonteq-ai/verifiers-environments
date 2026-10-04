"""Source-bound summary guard outcomes; semantic backends remain caller-owned."""

import json
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

import verifiers.v1 as vf
from pydantic import StrictStr

from .capture import canonical_json
from .contracts.authored_outputs import AuthoredOutputSource, capture_authored_outputs
from .contracts.base import FrozenModel, Identifier
from .contracts.engine import binding_reason
from .contracts.external_outputs import ExternalOutputSource, capture_external_outputs
from .contracts.loader import canonical_contract_digest, load_contract
from .contracts.no_clarification import NoClarificationCheck
from .contracts.summary_policy import (
    SummaryAssessor,
    SummaryDecision,
    SummaryExclusionCheck,
    SummaryPolicyContext,
    evaluate_summary_policy,
    prepare_summary_context,
)
from .contracts.tables import Digest
from .manifest_source import admit_manifest_source
from .manifest_summary_actions import plan_summary_actions, reduce_summary_actions

SUMMARY_PRODUCER = "automationbench.manifest_summary_exclusions"
SUMMARY_OUTPUT = "automationbench.manifest_summary_result@1"
SUMMARY_EXCHANGE = "automationbench.summary_semantic_exchange@1"
SUMMARY_REQUEST = "automationbench.summary_semantic_request@1"
SUMMARY_ACTION_OUTPUT = "automationbench.summary_action_harm_result@1"


class SummaryRunConfig(FrozenModel):
    contract_digest: Digest
    check_id: Identifier


class SummaryBackendExchange(FrozenModel):
    """Original backend exchange, supplied by the trusted execution adapter.

    The adapter declares whole-output coverage independently of model output.
    Request and response strings preserve its actual wire representation.
    """

    request_text: StrictStr
    response_text: StrictStr
    provider_identity: StrictStr
    usage_json: StrictStr
    full_output_ids: tuple[StrictStr, ...]


class SummaryBackend(Protocol):
    @property
    def identity(self) -> SummaryAssessor: ...

    async def execute(
        self,
        prepared: SummaryPolicyContext,
        raw_source: Mapping,
        request: vf.AssessmentRequest,
        context: vf.AssessmentContext,
    ) -> SummaryBackendExchange: ...

    def parse(
        self,
        exchange: SummaryBackendExchange,
        prepared: SummaryPolicyContext,
    ) -> Iterable[SummaryDecision]: ...


@dataclass(frozen=True)
class _OutputPolicyProfile:
    """Fixed environment wiring; a manifest cannot supply these callbacks."""

    check_type: type[SummaryExclusionCheck] | type[NoClarificationCheck]
    producer: str
    output_kind: str
    exchange_kind: str
    request_kind: str
    backend_registry: str
    signal: Callable
    targets: Callable
    prepare: Callable
    evaluate: Callable
    action_credit: bool = False


def _summary_profile():
    return _OutputPolicyProfile(
        SummaryExclusionCheck,
        SUMMARY_PRODUCER,
        SUMMARY_OUTPUT,
        SUMMARY_EXCHANGE,
        SUMMARY_REQUEST,
        "summary_backends",
        summary_signal,
        summary_targets,
        prepare_summary_context,
        evaluate_summary_policy,
        action_credit=True,
    )


def summary_signal(check):
    return vf.SignalDefinition(
        signal_id=check.signal_id,
        revision="1",
        semantics="outcome",
        description="Public summary-exclusion guard compliance",
        units="binary",
        minimum=0,
        maximum=1,
        direction="higher",
    )


def summary_action_signal(check, *, penalty=False):
    return vf.SignalDefinition(
        signal_id=check.signal_id + (".action_penalty" if penalty else ".action_harm"),
        revision="1",
        semantics="other",
        units="binary",
        description="Manifest summary harmful-action penalty"
        if penalty
        else "Manifest summary action harm",
        minimum=-1 if penalty else 0,
        maximum=0 if penalty else 1,
        direction="higher" if penalty else "lower",
    )


def summary_action_plan(source, raw, contract, check):
    if not any(
        rule.check == check.check_id and rule.policy == "summary_action_negative_once@1"
        for rule in contract.credit
    ):
        return None
    return plan_summary_actions(
        source,
        raw,
        check,
        assistant_source=contract.sources[check.source],
        external_source=contract.sources[check.external],
    )


def summary_targets(source, raw, contract, check):
    subject = vf.SubjectRef(
        kind="trace",
        snapshot_id=source.snapshot_id,
        episode_id=source.episode_id,
        trace_id=json.loads(source.source_json)["trace_id"],
    )
    plan = summary_action_plan(source, raw, contract, check)
    targets = (vf.AssessmentTarget(subject=subject, signal=summary_signal(check)),)
    if plan is None:
        return targets
    return (
        *targets,
        *(
            vf.AssessmentTarget(subject=group.recipient, signal=summary_action_signal(check))
            for group in plan.groups
        ),
    )


def summary_requests(source, contract, view):
    return _output_policy_requests(source, contract, view, _summary_profile())


def _output_policy_requests(source, contract, view, profile):
    requests = []
    for check in contract.checks:
        if not isinstance(check, profile.check_type):
            continue
        run = vf.AssessmentRun(
            run_id=uuid.uuid4().hex,
            producer_id=profile.producer,
            producer_revision="1",
            rubric_revision=contract.revision,
            snapshot_id=source.snapshot_id,
            invocation_id=uuid.uuid4().hex,
            attempt_id=uuid.uuid4().hex,
            configuration_json=canonical_json(
                {
                    "contract_digest": canonical_contract_digest(contract),
                    "check_id": check.check_id,
                }
            ),
            expected=profile.targets(
                source, json.loads(view.input_json)["source"], contract, check
            ),
        )
        requests.append(
            (
                "manifest_check",
                vf.AssessmentRequest(
                    source=source.identity,
                    run=run,
                    views=(view,),
                ),
            )
        )
    return requests


def _abstain_summary(request, context, check, reason, *, output_kind=SUMMARY_OUTPUT):
    context.record_evidence(
        output_kind,
        {"check_id": check.check_id, "status": "abstained", "reason": reason},
        invocation_id=request.run.invocation_id,
    )
    return tuple(
        vf.Assessment(
            assessment_id=uuid.uuid4().hex,
            run_id=request.run.run_id,
            subject=item.subject,
            view_id=request.views[0].view_id,
            signal=item.signal,
            status="abstained",
            value=None,
            reason=reason,
            invocation_ids=(request.run.invocation_id,),
        )
        for item in request.run.expected
    )


async def assess_summary(task, request, context):
    return await _assess_output_policy(task, request, context, _summary_profile())


async def _assess_output_policy(task, request, context, profile):
    """Retain raw exchange before custom parsing; unavailable meaning stays unknown."""
    material = admit_manifest_source(task, request, context).decode()
    contract = load_contract(canonical_json(material["contract"]))
    config = SummaryRunConfig.model_validate_json(request.run.configuration_json)
    if canonical_json(config.model_dump(mode="json")) != request.run.configuration_json:
        raise ValueError("summary_requested_configuration_not_canonical")
    if config.contract_digest != canonical_contract_digest(contract):
        raise ValueError("summary_requested_contract_mismatch")
    checks = [
        check
        for check in contract.checks
        if isinstance(check, (SummaryExclusionCheck, NoClarificationCheck))
        and isinstance(check, profile.check_type)
        and check.check_id == config.check_id
    ]
    if len(checks) != 1 or not request.run.expected:
        raise ValueError("summary_requested_check_or_target_mismatch")
    check = checks[0]
    target = request.run.expected[0]
    expected_subject = vf.SubjectRef(
        kind="trace",
        snapshot_id=request.source.snapshot_id,
        episode_id=request.source.episode_id,
        trace_id=json.loads(context.retrospective_source().source_json)["trace_id"],
    )
    native_source = context.retrospective_source()
    if (
        target.signal != profile.signal(check)
        or target.subject != expected_subject
        or request.run.expected
        != profile.targets(native_source, material["source"], contract, check)
    ):
        raise ValueError("summary_requested_subject_or_signal_mismatch")
    if (
        request.run.producer_id != profile.producer
        or request.run.producer_revision != "1"
        or request.run.rubric_revision != contract.revision
    ):
        raise ValueError("summary_requested_producer_mismatch")
    reason = binding_reason(material["source"], contract)
    if reason is not None:
        return _abstain_summary(request, context, check, reason, output_kind=profile.output_kind)
    action_plan = (
        summary_action_plan(native_source, material["source"], contract, check)
        if profile.action_credit and isinstance(check, SummaryExclusionCheck)
        else None
    )
    if action_plan is not None and action_plan.context_digest is None:
        return _abstain_summary(
            request,
            context,
            check,
            "summary_action_public_policy_unavailable",
            output_kind=profile.output_kind,
        )
    assistant_source = contract.sources[check.source]
    external_source = contract.sources[check.external]
    if not isinstance(assistant_source, AuthoredOutputSource) or not isinstance(
        external_source, ExternalOutputSource
    ):
        raise TypeError("summary_requested_sources_invalid")
    raw = material["source"]
    assistant = capture_authored_outputs(raw, assistant_source)
    external = capture_external_outputs(raw, external_source, native_source=native_source)
    prepared = profile.prepare(
        raw,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=native_source,
    )
    decisions, producer, covered = (), None, ()
    backend_error = None
    # Composition binds this registry. Manifests cannot import or create backends.
    registry = getattr(task, profile.backend_registry, {})
    backend = registry.get(check.assessor.assessor_id) if check.assessor is not None else None
    # Exact empty texts need no semantic execution. The reducer still checks
    # independent inventory closure, so missing capture cannot become silence.
    # Whitespace is authored text and must not be stripped into an empty value.
    if backend is not None and any(output.text != "" for output in prepared.outputs):
        try:
            identity = SummaryAssessor.model_validate(backend.identity.model_dump(mode="python"))
            if identity != check.assessor:
                raise ValueError("summary_backend_configuration_changed")
            journal_start = len(context.execution_evidence)
            exchange = await backend.execute(prepared, raw, request, context)
            exchange = SummaryBackendExchange.model_validate(exchange.model_dump(mode="python"))
            # Retain the original exchange even if parsing subsequently fails.
            context.record_evidence(
                profile.exchange_kind,
                {
                    "context_digest": prepared.context_digest,
                    "producer": identity.model_dump(mode="json"),
                    "exchange": exchange.model_dump(mode="json"),
                },
                invocation_id=request.run.invocation_id,
            )
            if (
                not exchange.provider_identity.strip()
                or not exchange.request_text.strip()
                or not exchange.response_text.strip()
            ):
                raise ValueError("summary_backend_exchange_identity_or_body_unavailable")
            if not isinstance(json.loads(exchange.usage_json), dict):
                raise TypeError("summary_backend_usage_requires_object")
            known = {output.output_key for output in prepared.outputs}
            if (
                len(set(exchange.full_output_ids)) != len(exchange.full_output_ids)
                or not set(exchange.full_output_ids) <= known
            ):
                raise ValueError("summary_backend_coverage_unknown_or_duplicate")
            expected_request = {
                "context_digest": prepared.context_digest,
                "producer": identity.model_dump(mode="json"),
                "request_text": exchange.request_text,
                "full_output_ids": list(exchange.full_output_ids),
            }
            journal = context.execution_evidence[journal_start:]
            if not any(
                record.kind == profile.request_kind
                and json.loads(record.payload_json) == expected_request
                for record in journal
            ):
                raise ValueError("summary_backend_request_journal_unavailable_or_changed")
            parsed = backend.parse(exchange, prepared)
            if isinstance(parsed, (str, bytes, Mapping)):
                raise TypeError("summary_backend_decision_collection_invalid")
            # The reducer admits bounded partial iterators and preserves an
            # independently valid violation if later parsing fails.
            decisions = parsed
            producer, covered = identity, exchange.full_output_ids
        except Exception as error:  # noqa: BLE001 - optional caller-owned backend failures abstain
            # Cancellation propagates; no prior semantic result is substituted.
            backend_error = type(error).__name__ + ":" + str(error)
            context.record_evidence(
                profile.exchange_kind,
                {
                    "context_digest": prepared.context_digest,
                    "error": backend_error,
                },
                invocation_id=request.run.invocation_id,
            )
    evaluation = profile.evaluate(
        raw,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=native_source,
        decisions=decisions,
        producer=producer,
        full_output_ids=covered,
    )
    context.record_evidence(
        profile.output_kind,
        {
            "contract_digest": canonical_contract_digest(contract),
            "evaluation": evaluation.model_dump(mode="json"),
            "backend_error": backend_error,
        },
        invocation_id=request.run.invocation_id,
    )
    valid = evaluation.compliance is not None
    assessments = [
        vf.Assessment(
            assessment_id=uuid.uuid4().hex,
            run_id=request.run.run_id,
            subject=target.subject,
            view_id=request.views[0].view_id,
            signal=target.signal,
            status="valid" if valid else "abstained",
            value=evaluation.compliance,
            reason=evaluation.reason,
            invocation_ids=(request.run.invocation_id,),
        ),
    ]
    plan = action_plan
    if plan is not None:
        if not isinstance(check, SummaryExclusionCheck):
            raise TypeError("clarification_action_credit_is_not_implemented")
        actions = reduce_summary_actions(
            native_source,
            raw,
            check,
            evaluation,
            assistant_source=assistant_source,
            external_source=external_source,
            plan=plan,
        )
        context.record_evidence(
            SUMMARY_ACTION_OUTPUT,
            {
                "contract_digest": config.contract_digest,
                "source_digest": actions.plan.source_digest,
                "context_digest": actions.plan.context_digest,
                "check_id": check.check_id,
                "findings": [
                    {
                        "group": finding.group.model_dump(mode="json"),
                        "harm": finding.harm,
                        "reason": finding.reason,
                    }
                    for finding in actions.findings
                ],
            },
            invocation_id=request.run.invocation_id,
        )
        assessments.extend(
            vf.Assessment(
                assessment_id=uuid.uuid4().hex,
                run_id=request.run.run_id,
                subject=finding.group.recipient,
                view_id=request.views[0].view_id,
                signal=summary_action_signal(check),
                status="valid" if finding.harm is not None else "abstained",
                value=finding.harm,
                reason=finding.reason,
                invocation_ids=(request.run.invocation_id,),
            )
            for finding in actions.findings
        )
    return tuple(assessments)
