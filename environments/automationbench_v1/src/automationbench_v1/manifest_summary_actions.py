"""Original external action membership, separate from semantic judgment/credit.

The caller must authenticate the retained evaluation against its current native
assessment parent and producer journal. An evaluation is not an authentication
certificate. This helper rechecks source membership and decision conformance;
it neither runs a judge nor establishes semantic accuracy or token attribution.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Mapping

import verifiers.v1 as vf
from pydantic import StrictBool, StrictInt, model_validator

from .capture import canonical_json
from .contracts.authored_outputs import AuthoredOutputSource, capture_authored_outputs
from .contracts.base import FrozenModel, Identifier
from .contracts.external_outputs import ExternalOutputSource, capture_external_outputs
from .contracts.invocation_inventory import capture_invocation_inventory
from .contracts.summary_policy import (
    SummaryEvaluation,
    SummaryExclusionCheck,
    SummaryFinding,
    evaluate_summary_policy,
    prepare_summary_context,
)
from .contracts.tables import Digest


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _same(left, right):
    return canonical_json(left.model_dump(mode="json")) == canonical_json(
        right.model_dump(mode="json")
    )


class SummaryActionGroup(FrozenModel):
    action_key: Digest
    recipient: vf.SubjectRef
    output_keys: tuple[Identifier, ...]
    local_closed: StrictBool
    reason: Identifier

    @model_validator(mode="after")
    def original_execution(self):
        execution = self.recipient.execution
        if (
            self.recipient.kind != "execution"
            or execution is None
            or execution.origin != "tool_server"
            or self.action_key != execution.occurrence_id
            or not self.output_keys
            or len(set(self.output_keys)) != len(self.output_keys)
        ):
            raise ValueError("summary_action_original_execution_group_invalid")
        return self


class SummaryUnassignedOutput(FrozenModel):
    output_key: Identifier
    reason: Identifier


class SummaryActionPlan(FrozenModel):
    source_identity: vf.SourceIdentity
    source_digest: Digest
    check_id: Identifier
    check_digest: Digest
    context_digest: Digest | None
    groups: tuple[SummaryActionGroup, ...]
    unassigned: tuple[SummaryUnassignedOutput, ...]


class SummaryActionFinding(FrozenModel):
    group: SummaryActionGroup
    harm: StrictInt | None
    reason: Identifier
    members: tuple[SummaryFinding, ...]

    @model_validator(mode="after")
    def bounded_harm(self):
        if self.harm not in (None, 0, 1):
            raise ValueError("summary_action_harm_out_of_bounds")
        return self


class SummaryActionEvaluation(FrozenModel):
    plan: SummaryActionPlan
    findings: tuple[SummaryActionFinding, ...]
    unassigned_violations: tuple[SummaryFinding, ...]
    validation_errors: tuple[Identifier, ...] = ()


def _capture(native_source, raw_source, check, assistant_source, external_source):
    # Python-mode strict admission preserves copied bool/bytes types. The
    # executor, not a prepared view or semantic producer, supplies this source.
    sealed = vf.SourceSnapshot.model_validate(
        native_source.model_dump(mode="python", warnings=False), strict=True
    )
    payload = json.loads(sealed.source_json)
    safe = {
        "task_evidence": payload["task_evidence"],
        "tool_execution_events": payload.get("tool_execution_events", []),
        "state_write_receipts": payload.get("state_write_receipts", []),
    }
    if canonical_json(raw_source) != canonical_json(safe):
        raise ValueError("summary_action_executor_source_mismatch")
    check = SummaryExclusionCheck.model_validate(
        check.model_dump(mode="python", warnings=False), strict=True
    )
    assistant = capture_authored_outputs(safe, assistant_source)
    external = capture_external_outputs(safe, external_source, native_source=sealed)
    inventory = capture_invocation_inventory(safe, native_source=sealed)
    return sealed, safe, check, assistant, external, inventory


def _context(sealed, safe, check, assistant, external, assistant_source, external_source):
    return prepare_summary_context(
        safe,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=sealed,
    )


def _plan(sealed, safe, check, assistant, external, inventory, context_digest):
    output_keys = [
        canonical_json([namespace, fact.output_id])
        for namespace, facts in (
            ("assistant", assistant.records),
            ("external", external.text_records),
        )
        for fact in facts
    ]
    if len(set(output_keys)) != len(output_keys):
        raise ValueError("summary_action_output_identity_ambiguous")
    coverage = {item.invocation_id: item for item in external.invocation_coverage}
    counts = Counter(item.invocation_id for item in external.invocation_coverage)
    invocations = {
        item.invocation_id: item for item in inventory.entries if item.status == "qualified"
    }
    members, recipients, unassigned = {}, {}, []
    for fact in assistant.records:
        unassigned.append(
            SummaryUnassignedOutput(
                output_key=canonical_json(["assistant", fact.output_id]),
                reason="summary_assistant_original_action_mapping_unavailable",
            )
        )
    # Use the recaptured native facts, never decision invocation/relation cites
    # or an output ID's string formatting to select an action.
    for fact in external.text_records:
        key = canonical_json(["external", fact.output_id])
        matches = [
            ref
            for ref in sealed.executions
            if ref.origin == "tool_server" and ref.invocation_id == fact.invocation_id
        ]
        if (
            len(matches) != 1
            or matches[0].phase != "returned"
            or fact.invocation_id not in invocations
            or counts[fact.invocation_id] != 1
        ):
            unassigned.append(
                SummaryUnassignedOutput(
                    output_key=key, reason="summary_external_original_execution_unavailable"
                )
            )
            continue
        execution = matches[0]
        action_key = execution.occurrence_id
        recipients[action_key] = vf.SubjectRef(
            kind="execution",
            snapshot_id=sealed.snapshot_id,
            episode_id=sealed.episode_id,
            trace_id=execution.trace_id,
            execution=execution,
        )
        members.setdefault(action_key, []).append(key)
    groups = []
    for action_key, keys in members.items():
        recipient = recipients[action_key]
        invocation = recipient.execution.invocation_id
        local = coverage[invocation]
        closed = local.disposition == "authored_fields"
        groups.append(
            SummaryActionGroup(
                action_key=action_key,
                recipient=recipient,
                output_keys=tuple(keys),
                local_closed=closed,
                reason=local.reason,
            )
        )
    return SummaryActionPlan(
        source_identity=sealed.identity,
        source_digest=_digest(safe),
        check_id=check.check_id,
        check_digest=_digest(check.model_dump(mode="json")),
        context_digest=context_digest,
        groups=tuple(groups),
        unassigned=tuple(unassigned),
    )


def plan_summary_actions(
    native_source: vf.SourceSnapshot,
    raw_source: Mapping,
    check: SummaryExclusionCheck,
    *,
    assistant_source: AuthoredOutputSource,
    external_source: ExternalOutputSource,
) -> SummaryActionPlan:
    """Derive action membership even when the declared policy is unavailable.

    Only exact policy-path/text/digest failures suppress the optional context
    digest. Source or capture integrity errors must never masquerade as missing
    policy. A plan with no context cannot authorize semantic reduction/credit.
    """
    sealed, safe, check, assistant, external, inventory = _capture(
        native_source, raw_source, check, assistant_source, external_source
    )
    context_digest = None
    try:
        context_digest = _context(
            sealed, safe, check, assistant, external, assistant_source, external_source
        ).context_digest
    except (ValueError, TypeError) as error:
        if str(error) not in {
            "summary_policy_source_unavailable",
            "summary_policy_source_requires_text",
            "summary_policy_source_digest_changed",
        }:
            raise
    return _plan(sealed, safe, check, assistant, external, inventory, context_digest)


def reduce_summary_actions(
    native_source: vf.SourceSnapshot,
    raw_source: Mapping,
    check: SummaryExclusionCheck,
    evaluation: SummaryEvaluation,
    *,
    assistant_source: AuthoredOutputSource,
    external_source: ExternalOutputSource,
    plan: SummaryActionPlan | None = None,
) -> SummaryActionEvaluation:
    """One harm value per physical invocation, retaining every field finding.

    Invalid/omitted/conflicting members stay unknown. Retained admitted decisions
    cannot reconstruct discarded malformed producer responses, so no compliance
    is inferred by discarding an original unknown finding or its failure state.
    Parent/exchange authenticity is the native publisher's separate obligation.
    """
    sealed, safe, check, assistant, external, inventory = _capture(
        native_source, raw_source, check, assistant_source, external_source
    )
    context = _context(sealed, safe, check, assistant, external, assistant_source, external_source)
    current = _plan(sealed, safe, check, assistant, external, inventory, context.context_digest)
    if plan is not None:
        supplied = SummaryActionPlan.model_validate(
            plan.model_dump(mode="python", warnings=False), strict=True
        )
        if not _same(supplied, current):
            raise ValueError("summary_action_plan_source_or_membership_changed")
    evaluation = SummaryEvaluation.model_validate(
        evaluation.model_dump(mode="python", warnings=False), strict=True
    )
    if (
        evaluation.source_digest != current.source_digest
        or evaluation.check_id != check.check_id
        or evaluation.signal_id != check.signal_id
        or evaluation.context is None
        or not _same(evaluation.context, context)
    ):
        raise ValueError("summary_action_evaluation_context_changed")
    known = {output.output_key: output for output in context.outputs}
    counts = Counter(finding.output_key for finding in evaluation.findings)
    for finding in evaluation.findings:
        output = known.get(finding.output_key)
        if (
            output is None
            or finding.output_id != output.output_id
            or finding.output_digest != output.output_digest
        ):
            raise ValueError("summary_action_finding_output_changed")
    # Re-run the existing semantic admission/reducer over surviving certificates.
    # Compare individual findings, not the global verdict: unrelated original
    # parser errors need not destroy this action's independently qualified harm.
    replay = evaluate_summary_policy(
        safe,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=sealed,
        decisions=tuple(
            finding.decision for finding in evaluation.findings if finding.decision is not None
        ),
        producer=evaluation.producer,
        full_output_ids=evaluation.full_output_ids,
    )
    rederived = {finding.output_key: finding for finding in replay.findings}
    originals = {finding.output_key: finding for finding in evaluation.findings}
    admitted, errors = {}, []
    for key, output in known.items():
        original, recaptured = originals.get(key), rederived.get(key)
        if (
            counts[key] == 1
            and original is not None
            and recaptured is not None
            and _same(original, recaptured)
        ):
            admitted[key] = original
        elif counts[key] == 1 and original is not None and original.state == "abstained":
            # Keep the original unknown member. Never revive its rejected
            # decision, even if a surviving certificate now looks valid alone.
            admitted[key] = original
        else:
            errors.append("summary_action_member_missing_conflicting_or_invalid:" + key)
            admitted[key] = SummaryFinding(
                output_key=key,
                output_id=output.output_id,
                output_digest=output.output_digest,
                state="abstained",
                reason="summary_action_member_unavailable",
            )
    findings = []
    for group in current.groups:
        group_members = tuple(admitted[key] for key in group.output_keys)
        if any(member.state == "violation" for member in group_members):
            harm, reason = 1, "summary_action_violation_cited"
        elif group.local_closed and all(
            member.state in {"compliant", "inapplicable"} for member in group_members
        ):
            harm, reason = 0, "summary_action_all_outputs_decided_no_violation"
        else:
            harm, reason = None, "summary_action_capture_or_semantics_unresolved"
        findings.append(
            SummaryActionFinding(group=group, harm=harm, reason=reason, members=group_members)
        )
    return SummaryActionEvaluation(
        plan=current,
        findings=tuple(findings),
        unassigned_violations=tuple(
            admitted[item.output_key]
            for item in current.unassigned
            if admitted[item.output_key].state == "violation"
        ),
        validation_errors=tuple(errors),
    )
