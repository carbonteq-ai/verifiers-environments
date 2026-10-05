"""Current semantic receipts projected once onto original physical actions.

The native executor authenticates accepted parents and sealed source membership.
This module replays the retained parser, never the semantic provider, and keeps
consumption independent of assessment attempts and individual authored fields.
"""

import json
import uuid
from collections.abc import Mapping
from typing import Literal

import verifiers.v1 as vf

from .capture import canonical_json
from .contracts.authored_outputs import AuthoredOutputSource, capture_authored_outputs
from .contracts.base import FrozenModel, Identifier
from .contracts.engine import binding_reason
from .contracts.external_outputs import ExternalOutputSource, capture_external_outputs
from .contracts.loader import canonical_contract_digest, load_contract, load_task_contract
from .contracts.summary_policy import (
    SummaryAssessor,
    SummaryEvaluation,
    SummaryExclusionCheck,
    evaluate_summary_policy,
    prepare_summary_context,
)
from .contracts.tables import Digest
from .manifest_guard_assessments import digest
from .manifest_source import manifest_source_material
from .manifest_summary_actions import plan_summary_actions, reduce_summary_actions
from .manifest_summary_assessments import (
    SUMMARY_ACTION_OUTPUT,
    SUMMARY_EXCHANGE,
    SUMMARY_OUTPUT,
    SUMMARY_PRODUCER,
    SUMMARY_REQUEST,
    SummaryBackendExchange,
    SummaryRunConfig,
    summary_action_signal,
    summary_targets,
)

RULE_ID = "automationbench.manifest_summary_action_negative_once"


class Consumption(FrozenModel):
    episode_id: Identifier
    contract_digest: Digest
    check_id: Identifier
    action_key: Digest
    channel: Identifier
    signal: vf.SignalDefinition


class PenaltyConfig(FrozenModel):
    consumption: Consumption
    policy: Literal["summary_action_negative_once@1"]
    source_digest: Digest
    group_digest: Digest
    parent_assessment_id: Identifier


def _safe(source):
    raw = json.loads(source.source_json)
    return manifest_source_material(raw)


def _record(run, kind):
    records = [item for item in run.execution_evidence if item.kind == kind]
    if len(records) != 1 or records[0].invocation_id != run.invocation_id:
        raise ValueError("summary_credit_receipt_unresolved:" + kind)
    return json.loads(records[0].payload_json)


def _replay(task, source, raw, check, run):
    """Parse the original exchange once, preserving bounded parser failures."""
    assistant_source, external_source = task[check.source], task[check.external]
    if not isinstance(assistant_source, AuthoredOutputSource) or not isinstance(
        external_source, ExternalOutputSource
    ):
        raise TypeError("summary_credit_source_kind_invalid")
    assistant = capture_authored_outputs(raw, assistant_source)
    external = capture_external_outputs(raw, external_source, native_source=source)
    prepared = prepare_summary_context(
        raw,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=source,
    )
    return assistant_source, external_source, assistant, external, prepared


def _semantic(task, source, raw, contract, check, run):
    assistant_source, external_source, assistant, external, prepared = _replay(
        contract.sources, source, raw, check, run
    )
    output = _record(run, SUMMARY_OUTPUT)
    if output.get("contract_digest") != canonical_contract_digest(contract):
        raise ValueError("summary_credit_evaluation_contract_mismatch")
    retained = SummaryEvaluation.model_validate_json(canonical_json(output["evaluation"]))
    decisions, producer, covered, backend_error = (), None, (), None
    exchanges = [
        json.loads(item.payload_json)
        for item in run.execution_evidence
        if item.kind == SUMMARY_EXCHANGE and "exchange" in json.loads(item.payload_json)
    ]
    if exchanges:
        if len(exchanges) != 1:
            raise ValueError("summary_credit_exchange_unresolved")
        payload = exchanges[0]
        backend = (
            getattr(task, "summary_backends", {}).get(check.assessor.assessor_id)
            if check.assessor
            else None
        )
        if backend is None:
            raise ValueError("summary_credit_parser_unavailable")
        identity = SummaryAssessor.model_validate(
            backend.identity.model_dump(mode="python"), strict=True
        )
        exchange = SummaryBackendExchange.model_validate_json(canonical_json(payload["exchange"]))
        if (
            identity != check.assessor
            or payload.get("producer") != identity.model_dump(mode="json")
            or payload.get("context_digest") != prepared.context_digest
        ):
            raise ValueError("summary_credit_exchange_producer_mismatch")
        if any(
            item.invocation_id != run.invocation_id
            for item in run.execution_evidence
            if item.kind in {SUMMARY_EXCHANGE, SUMMARY_REQUEST}
        ):
            raise ValueError("summary_credit_exchange_invocation_mismatch")
        journal = {
            "context_digest": prepared.context_digest,
            "producer": identity.model_dump(mode="json"),
            "request_text": exchange.request_text,
            "full_output_ids": list(exchange.full_output_ids),
        }
        records = [
            json.loads(item.payload_json)
            for item in run.execution_evidence
            if item.kind == SUMMARY_REQUEST
        ]
        if (
            records != [journal]
            or not exchange.provider_identity.strip()
            or not exchange.request_text.strip()
            or not exchange.response_text.strip()
            or not isinstance(json.loads(exchange.usage_json), dict)
        ):
            raise ValueError("summary_credit_exchange_journal_mismatch")
        try:
            parsed = backend.parse(exchange, prepared)
            if isinstance(parsed, (str, bytes, Mapping)):
                raise TypeError("summary_backend_decision_collection_invalid")
            decisions, producer, covered = parsed, identity, exchange.full_output_ids
        except Exception as error:  # noqa: BLE001 - replay optional parser's original failure
            backend_error = type(error).__name__ + ":" + str(error)
    elif retained.producer is not None:
        raise ValueError("summary_credit_exchange_missing")
    evaluation = evaluate_summary_policy(
        raw,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=source,
        decisions=decisions,
        producer=producer,
        full_output_ids=covered,
    )
    if canonical_json(evaluation.model_dump(mode="json")) != canonical_json(
        retained.model_dump(mode="json")
    ):
        raise ValueError("summary_credit_semantic_receipt_mismatch")
    # Execution failures can have no exchange and are never useful parents.
    if exchanges and output.get("backend_error") != backend_error:
        raise ValueError("summary_credit_parser_failure_mismatch")
    return reduce_summary_actions(
        source,
        raw,
        check,
        evaluation,
        assistant_source=assistant_source,
        external_source=external_source,
    )


def plan_summary_credit(task, source, batches, context, contract):
    """Plan only current authenticated action harms, with stable once semantics."""
    source = vf.SourceSnapshot.model_validate(source.model_dump(mode="python"), strict=True)
    if context.source != source.identity:
        raise ValueError("summary_credit_source_mismatch")
    raw, contract_digest = _safe(source), canonical_contract_digest(contract)
    current = {
        (run.run_id, run.invocation_id, run.attempt_id): run
        for run in context.current_assessment_runs
    }
    rules = [rule for rule in contract.credit if rule.policy == "summary_action_negative_once@1"]
    requests, channels, instances = [], set(), set()
    for batch in batches:
        run = batch.run
        identity = run.run_id, run.invocation_id, run.attempt_id
        if identity not in current or run.status not in {"complete", "partial"}:
            continue
        if run.producer_id != SUMMARY_PRODUCER or run.producer_revision != "1":
            raise ValueError("summary_credit_producer_mismatch")
        if (
            len(batch.views) != 1
            or (
                batch.source.identity
                if isinstance(batch.source, vf.SourceSnapshot)
                else batch.source
            )
            != source.identity
        ):
            raise ValueError("summary_credit_snapshot_or_view_mismatch")
        config = SummaryRunConfig.model_validate_json(run.configuration_json)
        if (
            canonical_json(config.model_dump(mode="json")) != run.configuration_json
            or config.contract_digest != contract_digest
        ):
            raise ValueError("summary_credit_configuration_mismatch")
        check = next((item for item in contract.checks if item.check_id == config.check_id), None)
        if not isinstance(check, SummaryExclusionCheck):
            raise TypeError("summary_credit_check_unknown")
        if not any(rule.check == check.check_id for rule in rules):
            continue
        if check.check_id in instances:
            raise ValueError("summary_credit_duplicate_current_check")
        instances.add(check.check_id)
        view = batch.views[0]
        view.verify()
        if view.snapshot_id != source.snapshot_id or view.scope != "retrospective":
            raise ValueError("summary_credit_view_scope_mismatch")
        material = json.loads(view.input_json)
        if (
            canonical_json(material["source"]) != canonical_json(raw)
            or canonical_contract_digest(load_contract(canonical_json(material["contract"])))
            != contract_digest
        ):
            raise ValueError("summary_credit_input_binding_mismatch")
        if (
            run.rubric_revision != contract.revision
            or run.snapshot_id != source.snapshot_id
            or run.expected != summary_targets(source, raw, contract, check)
            or any(
                getattr(current[identity], field) != getattr(run, field)
                for field in (
                    "configuration_json",
                    "expected",
                    "producer_id",
                    "producer_revision",
                    "rubric_revision",
                    "snapshot_id",
                )
            )
        ):
            raise ValueError("summary_credit_current_targets_mismatch")
        authority = binding_reason(raw, contract)
        output = _record(run, SUMMARY_OUTPUT)
        if "evaluation" not in output:
            # Public authority/preparation unavailability is a current result,
            # not permission to replay an older semantic attempt.
            unavailable_reason = authority
            if unavailable_reason is None:
                assistant_source, external_source = (
                    contract.sources[check.source],
                    contract.sources[check.external],
                )
                if not isinstance(assistant_source, AuthoredOutputSource) or not isinstance(
                    external_source, ExternalOutputSource
                ):
                    raise TypeError("summary_credit_source_kind_invalid")
                factual_plan = plan_summary_actions(
                    source,
                    raw,
                    check,
                    assistant_source=assistant_source,
                    external_source=external_source,
                )
                if factual_plan.context_digest is None:
                    unavailable_reason = "summary_action_public_policy_unavailable"
            if (
                unavailable_reason is None
                or output.get("reason") != unavailable_reason
                or output.get("status") != "abstained"
                or output.get("check_id") != check.check_id
                or (authority is not None and output.get("reason") != authority)
                or len(batch.assessments) != len(run.expected)
            ):
                raise ValueError("summary_credit_unavailable_receipt_mismatch")
            for target in run.expected:
                parents = [
                    parent
                    for parent in batch.assessments
                    if parent.subject == target.subject and parent.signal == target.signal
                ]
                if (
                    len(parents) != 1
                    or parents[0].status != "abstained"
                    or parents[0].value is not None
                    or parents[0].reason != output.get("reason")
                    or parents[0].view_id != view.view_id
                    or parents[0].run_id != run.run_id
                    or parents[0].invocation_ids != (run.invocation_id,)
                ):
                    raise ValueError("summary_credit_unavailable_parent_mismatch")
            continue
        if authority is not None:
            raise ValueError("summary_credit_authority_mismatch")
        actions = _semantic(task, source, raw, contract, check, run)
        original = _record(run, SUMMARY_ACTION_OUTPUT)
        expected = {
            "contract_digest": contract_digest,
            "source_digest": actions.plan.source_digest,
            "context_digest": actions.plan.context_digest,
            "check_id": check.check_id,
            "findings": [
                {
                    "group": item.group.model_dump(mode="json"),
                    "harm": item.harm,
                    "reason": item.reason,
                }
                for item in actions.findings
            ],
        }
        if canonical_json(original) != canonical_json(expected):
            raise ValueError("summary_credit_action_receipt_mismatch")
        aggregate = _record(run, SUMMARY_OUTPUT)["evaluation"]
        parents = list(batch.assessments)
        expected_parents = [
            (run.expected[0], aggregate["compliance"], aggregate["reason"]),
            *(
                (
                    vf.AssessmentTarget(
                        subject=item.group.recipient, signal=summary_action_signal(check)
                    ),
                    item.harm,
                    item.reason,
                )
                for item in actions.findings
            ),
        ]
        if len(parents) != len(expected_parents):
            raise ValueError("summary_credit_parent_inventory_mismatch")
        for target, value, reason in expected_parents:
            matching = [
                parent
                for parent in parents
                if parent.subject == target.subject and parent.signal == target.signal
            ]
            if len(matching) != 1:
                raise ValueError("summary_credit_parent_unresolved")
            parent = matching[0]
            if (
                parent.run_id != run.run_id
                or (parent.value is not None and type(parent.value) not in (int, float))
                or parent.view_id != view.view_id
                or parent.invocation_ids != (run.invocation_id,)
                or (parent.status, parent.value, parent.reason)
                != ("valid" if value is not None else "abstained", value, reason)
            ):
                raise ValueError("summary_credit_parent_mismatch")
        for finding in actions.findings:
            if finding.harm != 1:
                continue
            parent = next(
                parent
                for parent in parents
                if parent.subject == finding.group.recipient
                and parent.signal == summary_action_signal(check)
            )
            for rule in rules:
                if rule.check != check.check_id:
                    continue
                signal = summary_action_signal(check, penalty=True)
                consumption = Consumption(
                    episode_id=source.episode_id,
                    contract_digest=contract_digest,
                    check_id=check.check_id,
                    action_key=finding.group.action_key,
                    channel=rule.channel,
                    signal=signal,
                )
                consumed = False
                for previous in context.prior_assignments:
                    if (
                        previous.request.source.episode_id != source.episode_id
                        or previous.request.rule.rule_id != RULE_ID
                    ):
                        continue
                    old = PenaltyConfig.model_validate_json(
                        previous.request.rule.configuration_json
                    )
                    if old.consumption.model_dump(exclude={"signal"}) != consumption.model_dump(
                        exclude={"signal"}
                    ):
                        continue
                    for part in previous.contributions:
                        if part.status == "valid":
                            if (
                                old.consumption.signal != signal
                                or part.signal != signal
                                or part.value != -1
                                or part.channel != rule.channel
                                or part.recipient.execution is None
                                or part.recipient.execution.occurrence_id
                                != finding.group.action_key
                            ):
                                raise ValueError("summary_credit_prior_conflict")
                            consumed = True
                if consumed:
                    continue
                key = finding.group.action_key, rule.channel
                if key in channels:
                    raise ValueError("summary_credit_aggregation_required")
                channels.add(key)
                config = PenaltyConfig(
                    consumption=consumption,
                    policy=rule.policy,
                    source_digest=actions.plan.source_digest,
                    group_digest=digest(finding.group.model_dump(mode="json")),
                    parent_assessment_id=parent.assessment_id,
                )
                requests.append(
                    (
                        "manifest_summary_penalty",
                        vf.CreditRequest(
                            source=source,
                            invocation_id=uuid.uuid4().hex,
                            attempt_id=uuid.uuid4().hex,
                            rule=vf.CreditRule(
                                rule_id=RULE_ID,
                                revision="1",
                                configuration_json=canonical_json(config.model_dump(mode="json")),
                            ),
                            accepted=(parent,),
                            targets=(
                                vf.CreditTarget(
                                    recipient=finding.group.recipient, channel=rule.channel
                                ),
                            ),
                            allocation="turn_boundary",
                            # Distinct physical retries can share one sampled
                            # call's tokens. Preserve each action's penalty;
                            # identical execution/channel claims were rejected
                            # above, before this explicit token overlap policy.
                            overlap_policy="sum",
                        ),
                    )
                )
    return requests


async def manifest_summary_penalty(task, request):
    """Project an accepted action parent; native runtime admits its provenance."""
    if (
        not isinstance(request.source, vf.SourceSnapshot)
        or len(request.accepted) != 1
        or len(request.targets) != 1
    ):
        raise ValueError("summary_penalty_one_sealed_parent_target_required")
    config = PenaltyConfig.model_validate_json(request.rule.configuration_json)
    parent, target = request.accepted[0], request.targets[0]
    contract = load_task_contract(task.data.task_name)
    check = next(
        (item for item in contract.checks if item.check_id == config.consumption.check_id), None
    )
    if not isinstance(check, SummaryExclusionCheck):
        raise TypeError("summary_penalty_check_unknown")
    if (
        request.rule.rule_id != RULE_ID
        or request.rule.revision != "1"
        or canonical_json(config.model_dump(mode="json")) != request.rule.configuration_json
        or config.consumption.contract_digest != canonical_contract_digest(contract)
        or config.consumption.episode_id != request.source.episode_id
        or config.source_digest != digest(_safe(request.source))
    ):
        raise ValueError("summary_penalty_source_or_rule_mismatch")
    if not any(
        rule.policy == config.policy
        and rule.check == check.check_id
        and rule.channel == target.channel
        for rule in contract.credit
    ):
        raise ValueError("summary_penalty_rule_undeclared")
    assistant_source, external_source = (
        contract.sources[check.source],
        contract.sources[check.external],
    )
    if not isinstance(assistant_source, AuthoredOutputSource) or not isinstance(
        external_source, ExternalOutputSource
    ):
        raise TypeError("summary_penalty_sources_invalid")
    plan = plan_summary_actions(
        request.source,
        _safe(request.source),
        check,
        assistant_source=assistant_source,
        external_source=external_source,
    )
    group = next(
        (item for item in plan.groups if item.action_key == config.consumption.action_key), None
    )
    if (
        group is None
        or digest(group.model_dump(mode="json")) != config.group_digest
        or group.recipient != target.recipient
        or parent.subject != target.recipient
        or parent.assessment_id != config.parent_assessment_id
        or parent.status != "valid"
        or parent.value != 1
        or type(parent.value) not in (int, float)
        or parent.signal != summary_action_signal(check)
        or config.consumption.signal != summary_action_signal(check, penalty=True)
        or config.consumption.channel != target.channel
        or request.allocation != "turn_boundary"
        or request.overlap_policy != "sum"
    ):
        raise ValueError("summary_penalty_action_parent_or_target_mismatch")
    return (
        vf.CreditContribution(
            contribution_id=uuid.uuid4().hex,
            parent_assessment_ids=(parent.assessment_id,),
            recipient=target.recipient,
            channel=target.channel,
            signal=config.consumption.signal,
            transformation="summary_action_harm_penalty@1",
            status="valid",
            value=-1,
            allocation=request.allocation,
            attribution="coarse",
            reason=parent.reason,
        ),
    )
