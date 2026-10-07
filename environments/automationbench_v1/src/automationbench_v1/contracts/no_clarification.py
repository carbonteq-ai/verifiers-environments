"""A finite prohibition on requests to resolve task-execution uncertainty.

This module admits factual inventories and cited producer decisions. It does
not classify question marks, names, field types or communicative purpose. The
separately pinned producer assesses whole outputs in their public task context.
Incoming content, discovery arguments and private reasoning are not promoted
into authored outputs. Unknown visibility or purpose remains unknown.
"""

import json
from collections.abc import Iterable, Mapping
from functools import partial
from typing import Literal

from pydantic import model_validator
from verifiers.v1.assessments import SourceSnapshot

from .authored_outputs import AuthoredOutputEvidence, AuthoredOutputFact, AuthoredOutputSource
from .base import FrozenModel, Identifier
from .external_outputs import ExternalOutputEvidence, ExternalOutputFact, ExternalOutputSource
from .populations import Path
from .summary_policy import (
    SummaryAssessor,
    SummaryDecision,
    SummaryEvaluation,
    SummaryPolicyContext,
    _admit_decision,
    _evaluate_output_policy,
    _prepare_output_policy_context,
)
from .tables import Digest


class NoClarificationCheck(FrozenModel):
    check_id: Identifier
    signal_id: Identifier
    role: Literal["harm"] = "harm"
    operator: Literal["no_clarification@1", "no_clarification@2"] = "no_clarification@1"
    source: Identifier
    external: Identifier
    policy_path: Path
    policy_digest: Digest
    assessor: SummaryAssessor | None = None

    @model_validator(mode="after")
    def public_policy(self):
        if (
            len(self.policy_path) < 2
            or self.policy_path[0] != "task_evidence"
            or self.policy_path[1] not in {"prompt", "initial"}
            or any(type(part) is int and part < 0 for part in self.policy_path)
        ):
            raise ValueError("no_clarification_policy_requires_public_source_path")
        if self.source == self.external:
            raise ValueError("no_clarification_output_source_aliases_must_differ")
        return self


def _communication_basis(source, output, context):
    """Require a recaptured outward act, independently of the semantic verdict.

    These are bounded installed transport capabilities, not a field-name test
    for question meaning. The enclosing context has already re-captured the
    entire fact and exact action relations from source. A judge cannot nominate
    a different send as this output's delivery witness. Unknown presentation of
    other written fields remains unsupported, without exempting their prose.
    """
    if output.inventory == "assistant":
        fact = AuthoredOutputFact.model_validate_json(output.fact_json, strict=True)
        if fact.channel not in {None, "final", "commentary"}:
            return False
        if fact.origin == "sdk_item":
            # Only completed agentMessage items enter this recaptured inventory;
            # incoming userMessage, reasoning and MCP argument text never do.
            return True
        projection = source["task_evidence"]["authored_outputs"]
        index = fact.source_path[-2]
        if type(index) is not int:
            return False
        nodes = projection.get("native_nodes", ())
        calls = projection.get("native_calls", ())
        if not 0 <= index < len(nodes):
            return False
        node = nodes[index]
        matched = [
            call for call in calls if type(call.get("node")) is int and call["node"] == index
        ]
        return (
            type(node.get("node")) is int
            and node["node"] == index
            and node.get("sampled") is True
            and node.get("role") == "assistant"
            and len(matched) == 1
            and matched[0].get("failed") is False
            and matched[0].get("finish_reason") in {"stop", "tool_calls"}
        )

    fact = ExternalOutputFact.model_validate_json(output.fact_json, strict=True)
    entries = [entry for entry in context.invocations if entry.invocation_id == fact.invocation_id]
    if len(entries) != 1 or entries[0].status != "qualified":
        return False
    values = {}
    for item in context.relations:
        relation = item.relation
        if (
            relation.invocation_id == fact.invocation_id
            and relation.service == fact.service
            and relation.collection == fact.collection
            and relation.record_id == fact.record_id
        ):
            if relation.field in values:
                return False
            values[relation.field] = json.loads(relation.value_json)
    if values.get(fact.field) != fact.text:
        return False
    operation = entries[0].operation
    if (
        operation == "gmail_send_email"
        and fact.service == "gmail"
        and fact.collection == "messages"
        and fact.surface == "message_field"
        and fact.field in {"subject", "body_plain", "body_html"}
    ):
        recipients = [values.get(key) for key in ("to", "cc", "bcc")]
        return any(
            type(group) is list
            and bool(group)
            and all(type(value) is str and bool(value.strip()) for value in group)
            for group in recipients
        )
    if (
        operation == "slack_send_direct_message"
        and fact.service == "slack"
        and fact.collection == "messages"
        and fact.surface == "message_field"
        and fact.field == "text"
    ):
        return all(
            type(values.get(key)) is str and bool(values[key])
            for key in ("recipient_user_id", "channel_id")
        )
    if (
        operation == "zendesk_update_ticket"
        and fact.service == "zendesk"
        and fact.collection == "comments"
        and fact.field == "body"
    ):
        return (
            values.get("public") is True
            and type(values.get("ticket_id")) is str
            and bool(values["ticket_id"])
        )
    return False


def _admit_communicated_decision(
    decision, output, context, declared, producer, full_output_ids, *, communicated_outputs
):
    _admit_decision(decision, output, context, declared, producer, full_output_ids)
    if decision.state == "violation" and output.output_key not in communicated_outputs:
        raise ValueError("no_clarification_communication_basis_unavailable")


def _prepare_communication_admission(context, *, source):
    """Seal per-output facts before consuming untrusted optional iterables.

    The callback retains only immutable output identities from the freshly
    re-captured context. It never reads caller-owned source after this point.
    An unavailable peer cannot discard a separately qualified outward act.
    """
    communicated = set()
    for output in context.outputs:
        try:
            if _communication_basis(source, output, context):
                communicated.add(output.output_key)
        except (ValueError, TypeError, AttributeError, KeyError, IndexError):
            continue
    return partial(_admit_communicated_decision, communicated_outputs=frozenset(communicated))


def prepare_no_clarification_context(
    source: Mapping,
    check: NoClarificationCheck,
    assistant: AuthoredOutputEvidence,
    external: ExternalOutputEvidence,
    *,
    assistant_source: AuthoredOutputSource,
    external_source: ExternalOutputSource,
    native_source: SourceSnapshot | None = None,
) -> SummaryPolicyContext:
    check = NoClarificationCheck.model_validate(check.model_dump(mode="python", warnings=False))
    return _prepare_output_policy_context(
        source,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=native_source,
    )


def evaluate_no_clarification_policy(
    source: Mapping,
    check: NoClarificationCheck,
    assistant: AuthoredOutputEvidence,
    external: ExternalOutputEvidence,
    *,
    assistant_source: AuthoredOutputSource,
    external_source: ExternalOutputSource,
    native_source: SourceSnapshot | None = None,
    decisions: Iterable[SummaryDecision] = (),
    producer: SummaryAssessor | None = None,
    full_output_ids: Iterable[str] = (),
) -> SummaryEvaluation:
    """Outcome only: known requests survive gaps; no action credit is inferred.

    A decision's inapplicable state means a resolved non-clarification output,
    rather than non-summary content. Closed zero outputs comply without a judge;
    missing capture or unresolved nonempty text cannot establish compliance.
    The @1 operator preserves historical admission. Explicit @2 additionally
    requires source-backed outward communication before admitting a violation;
    it does not rewrite the producer's retained raw decision or infer credit.
    """
    return _evaluate_output_policy(
        source,
        check,
        assistant,
        external,
        assistant_source=assistant_source,
        external_source=external_source,
        native_source=native_source,
        decisions=decisions,
        producer=producer,
        full_output_ids=full_output_ids,
        prepare_context=prepare_no_clarification_context,
        reason_prefix="no_clarification",
        violation_reason="no_clarification_request_violation_cited",
        inapplicable_reason="no_clarification_no_output_requests_clarification",
        prepare_admission=(
            partial(_prepare_communication_admission, source=source)
            if check.operator == "no_clarification@2"
            else None
        ),
    )
