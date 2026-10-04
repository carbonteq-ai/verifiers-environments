"""Earliest observed qualified completion of an original typed-record goal."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, cast

from pydantic import TypeAdapter

from ..capture import canonical_json
from .effects import EffectEvidence, EffectFact
from .obligations import _context, _fields
from .populations import InitialCollectionSource, PopulationEvidence, _model, _resolve_field
from .predicates import evaluate_predicate
from .retained_credit import CompletionEvaluation, CompletionFinding, CompletionSelection
from .retained_records import (
    RecordRetentionEvidence,
    RetainedRecordCheck,
    RetainedRecordSource,
    _digest,
    _finite,
    _leaf,
    _literal_types,
    _typed_context_populations,
    evaluate_retained_records,
)
from .zendesk_effects import ZendeskTicketEffectSource, validate_zendesk_ticket_effects

if TYPE_CHECKING:
    from .models import CreditSpec


def _status_update(fact: EffectFact):
    if fact.status != "qualified":
        return None
    if (fact.origin != "tool_server" or fact.kind != "status_update" or not fact.effect_id
            or not fact.invocation_id or fact.params_json is None
            or type(fact.expected_revision) is not int or fact.expected_revision < 0
            or type(fact.applied_revision) is not int
            or fact.applied_revision != fact.expected_revision + 1):
        raise ValueError("record_completion_qualified_update_metadata_invalid")
    params = json.loads(fact.params_json)
    if (not isinstance(params, dict) or canonical_json(params) != fact.params_json
            or type(params.get("native_record_id")) is not str or not params["native_record_id"]
            or not isinstance(params.get("before_fields"), dict)
            or not isinstance(params.get("after_fields"), dict)):
        raise ValueError("record_completion_update_projection_invalid")
    for name in ("requested_fields", "changed_fields"):
        fields = params.get(name)
        if (not isinstance(fields, list) or any(type(field) is not str or not field for field in fields)
                or len(set(fields)) != len(fields)):
            raise ValueError("record_completion_update_field_inventory_invalid")
    return params


def _baseline(row, retention_source, used):
    """Validate only read leaves without relabeling initial evidence as final."""
    cells = json.loads(row.cells_json)
    model = _model(cast(str, retention_source.path[2]), cast(str, retention_source.path[3]))
    for alias in used:
        if alias not in cells:
            continue
        annotation = _leaf(model, retention_source.fields[alias])
        try:
            if not _literal_types(cells[alias], annotation):
                raise ValueError("record_completion_initial_literal_type_invalid")
            normalized = TypeAdapter(annotation).validate_json(canonical_json(cells[alias]), strict=True)
            if not _finite(normalized):
                raise ValueError("record_completion_initial_numeric_domain_invalid")
        except ValueError:
            del cells[alias]
    return cells


def _project_fields(fields, retention_source):
    projected = {}
    model = _model(cast(str, retention_source.path[2]), cast(str, retention_source.path[3]))
    for alias, path in retention_source.fields.items():
        known, value = _resolve_field(fields, model, path) if isinstance(fields, Mapping) else (False, None)
        if known:
            projected[alias] = value
    return projected


def evaluate_record_retained_completion(
    source: Mapping, check: RetainedRecordCheck, rule: CreditSpec,
    populations: Mapping[str, PopulationEvidence], retention: RecordRetentionEvidence,
    effects: EffectEvidence, *, population_sources: Mapping[str, InitialCollectionSource],
    retention_source: RetainedRecordSource, effect_source: ZendeskTicketEffectSource,
) -> CompletionEvaluation:
    from .models import CreditSpec

    check = RetainedRecordCheck.model_validate(check.model_dump(mode="python", warnings=False))
    rule = CreditSpec.model_validate(rule.model_dump(mode="python", warnings=False))
    retention_source = RetainedRecordSource.model_validate(retention_source.model_dump(mode="python", warnings=False))
    effect_source = ZendeskTicketEffectSource.model_validate(effect_source.model_dump(mode="python", warnings=False))
    if (rule.policy != "records_retained_completion_once@1" or rule.check != check.check_id
            or rule.completion_selection != "earliest" or rule.effects is None):
        raise ValueError("record_completion_rule_check_mismatch")
    if retention_source.path[2:] != ("zendesk", "tickets"):
        raise ValueError("record_completion_effect_scope_mismatch")
    read = {path[1] for path in _fields(check.retained_when.model_dump(mode="python")) if path[0] == "retained"}
    if not set(rule.goal_fields) <= read:
        raise ValueError("record_completion_goal_field_not_read")
    initial = population_sources[check.population]
    if any(alias not in retention_source.fields or initial.fields.get(alias) != retention_source.fields[alias] for alias in read):
        raise ValueError("record_completion_initial_goal_projection_mismatch")
    outcome = evaluate_retained_records(source, check, populations, retention,
        population_sources=population_sources, retention_source=retention_source)
    validate_zendesk_ticket_effects(effects, source, effect_source)
    updates = defaultdict(list)
    for fact in effects.effects:
        params = _status_update(fact)
        if params is not None:
            updates[params["native_record_id"]].append((fact, params))
    working = _typed_context_populations(check, populations, population_sources)
    rows = {row.identity: row for row in working[check.population].rows}
    goal_native_fields = {retention_source.fields[alias][0] for alias in rule.goal_fields}
    findings = []
    for goal in outcome.findings:
        status: Literal["eligible", "unavailable", "ineligible"] = "ineligible"
        reason, baseline, selected = "record_completion_terminal_goal_not_met", None, None
        if goal.status == "abstained":
            status, reason = "unavailable", "record_completion_terminal_goal_unavailable"
        elif goal.status == "inapplicable" or goal.required is not True:
            reason = "record_completion_not_required"
        elif goal.value == 1 and goal.native_record_id is not None:
            row = rows[goal.candidate_identity]
            context = _context(check, row, working)
            context["candidate"]["native_record_id"] = goal.native_record_id
            context["retained"] = _baseline(row, retention_source, read)
            baseline = evaluate_predicate(check.retained_when, context).value
            if baseline is True:
                reason = "record_completion_initially_satisfied"
            elif baseline is None:
                status, reason = "unavailable", "record_completion_initial_goal_unavailable"
            else:
                witnesses = []
                for fact, params in updates[goal.native_record_id]:
                    if not goal_native_fields & set(params["requested_fields"]) & set(params["changed_fields"]):
                        continue
                    context["retained"] = _project_fields(params["before_fields"], retention_source)
                    before = evaluate_predicate(check.retained_when, context).value
                    context["retained"] = _project_fields(params["after_fields"], retention_source)
                    after = evaluate_predicate(check.retained_when, context).value
                    if before is False and after is True:
                        witnesses.append(fact)
                if witnesses:
                    earliest = min(cast(int, fact.applied_revision) for fact in witnesses)
                    first = [fact for fact in witnesses if fact.applied_revision == earliest]
                    if len(first) != 1:
                        status, reason = "unavailable", "record_completion_revision_order_ambiguous"
                    else:
                        fact = first[0]
                        selected = CompletionSelection(check.check_id, goal.instance_key, goal.native_record_id,
                            fact.invocation_id, cast(str, fact.effect_id), cast(int, fact.expected_revision),
                            cast(int, fact.applied_revision))
                        status, reason = "eligible", "record_completion_observed_qualified_transition"
                elif effects.complete:
                    reason = "record_completion_no_qualified_transition"
                else:
                    status, reason = "unavailable", "record_completion_action_evidence_unavailable"
        findings.append(CompletionFinding(goal.instance_key, goal.candidate_identity,
            goal.native_record_id, status, reason, baseline, selected))
    return CompletionEvaluation(outcome.source_digest, outcome.check_digest, _digest(rule.model_dump(mode="json")),
        outcome, tuple(findings), effects.complete, "record_completion_evaluated_observed_transitions")
