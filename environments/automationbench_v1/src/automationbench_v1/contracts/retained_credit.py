"""One observed completion recipient, distinct from retained outcome proof."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal, cast

from ..capture import canonical_json
from .effects import EffectEvidence, EffectFact
from .obligations import _context, _fields
from .predicates import evaluate_predicate
from .retained import RetainedEvaluation, RetainedRowCheck, _digest, evaluate_retained_rows
from .sheet_effects import SheetEffectSource, SheetRetentionEvidence, capture_sheet_effects
from .tables import TableEvidence, TableSource

if TYPE_CHECKING:
    from .models import CreditSpec


@dataclass(frozen=True)
class CompletionSelection:
    check_id: str
    instance_key: str
    native_record_id: str
    occurrence: str
    effect_id: str
    expected_revision: int
    applied_revision: int
    value: float = 1.0


@dataclass(frozen=True)
class CompletionFinding:
    instance_key: str
    candidate_identity: tuple
    native_record_id: str | None
    status: Literal["eligible", "unavailable", "ineligible"]
    reason: str
    initially_satisfied: bool | None
    selection: CompletionSelection | None = None


@dataclass(frozen=True)
class CompletionEvaluation:
    source_digest: str
    check_digest: str
    rule_digest: str
    outcome: RetainedEvaluation
    findings: tuple[CompletionFinding, ...]
    action_scope_complete: bool
    reason: str


def _update(fact: EffectFact):
    if fact.status != "qualified":
        return None
    if (fact.origin != "tool_server" or fact.kind != "update" or not fact.effect_id
            or not fact.invocation_id or fact.params_json is None
            or type(fact.expected_revision) is not int or fact.expected_revision < 0
            or type(fact.applied_revision) is not int
            or fact.applied_revision != fact.expected_revision + 1):
        raise ValueError("completion_qualified_update_metadata_invalid")
    params = json.loads(fact.params_json)
    if (not isinstance(params, dict) or canonical_json(params) != fact.params_json
            or not isinstance(params.get("before_cells"), dict)
            or not isinstance(params.get("after_cells"), dict)
            or type(params.get("native_record_id")) is not str
            or not params["native_record_id"]):
        raise ValueError("completion_qualified_update_projection_invalid")
    for name in ("requested_fields", "changed_fields"):
        fields = params.get(name)
        if (not isinstance(fields, list) or any(type(field) is not str or not field for field in fields)
                or len(set(fields)) != len(fields)):
            raise ValueError("completion_qualified_update_fields_invalid")
    return params


def evaluate_retained_completion(
    source: Mapping, check: RetainedRowCheck, rule: CreditSpec,
    populations: Mapping[str, TableEvidence], retention: SheetRetentionEvidence,
    effects: EffectEvidence, *, population_sources: Mapping[str, TableSource],
    retention_source: SheetEffectSource,
) -> CompletionEvaluation:
    """Select the latest observed qualified false-to-true goal transition.

    The caller authenticates the current outcome parent and owns stable episode
    consumption. This pure selection never implies unique causal responsibility
    or retroactively revises earlier contributions.
    """
    from .models import CreditSpec

    check = RetainedRowCheck.model_validate(check.model_dump(mode="python", warnings=False))
    rule = CreditSpec.model_validate(rule.model_dump(mode="python", warnings=False))
    retention_source = SheetEffectSource.model_validate(retention_source.model_dump(mode="python", warnings=False))
    if rule.policy != "retained_completion_once@1" or rule.check != check.check_id:
        raise ValueError("completion_rule_check_mismatch")
    if retention_source.kind != "update":
        raise ValueError("completion_requires_update_selector")
    fields = {path[1] for path in _fields(check.retained_when.model_dump(mode="python"))
              if len(path) >= 2 and path[0] == "retained"}
    if not set(rule.goal_fields) <= fields:
        raise ValueError("completion_goal_field_not_read")
    outcome = evaluate_retained_rows(source, check, populations, retention,
        retention_source=retention_source, population_sources=population_sources)
    actual = capture_sheet_effects(source, retention_source)
    if canonical_json(asdict(effects)) != canonical_json(asdict(actual)):
        raise ValueError("completion_effect_source_or_projection_mismatch")
    updates = defaultdict(list)
    for fact in effects.effects:
        params = _update(fact)
        if params is not None:
            updates[params["native_record_id"]].append((fact, params))
    rows = {row.identity: row for row in populations[check.population].rows}
    findings = []
    for goal in outcome.findings:
        status: Literal["eligible", "unavailable", "ineligible"] = "ineligible"
        reason, initial, selected = "completion_terminal_goal_not_met", None, None
        if goal.status == "abstained":
            status, reason = "unavailable", "completion_terminal_goal_unavailable"
        elif goal.status == "inapplicable" or goal.required is not True:
            reason = "completion_not_required"
        elif goal.value == 1 and goal.native_record_id is not None:
            row = rows[goal.candidate_identity]
            context = _context(check, row, populations)
            context["retained"] = json.loads(row.cells_json)
            initial = evaluate_predicate(check.retained_when, context).value
            if initial is True:
                reason = "completion_initially_satisfied"
            elif initial is None:
                status, reason = "unavailable", "completion_initial_goal_unavailable"
            else:
                witnesses = []
                for fact, params in updates[goal.native_record_id]:
                    if not set(rule.goal_fields) & set(params["requested_fields"]) & set(params["changed_fields"]):
                        continue
                    context["retained"] = params["before_cells"]
                    before = evaluate_predicate(check.retained_when, context).value
                    context["retained"] = params["after_cells"]
                    after = evaluate_predicate(check.retained_when, context).value
                    if before is False and after is True:
                        witnesses.append(fact)
                if witnesses:
                    latest = max(cast(int, fact.applied_revision) for fact in witnesses)
                    best = [fact for fact in witnesses if fact.applied_revision == latest]
                    if len(best) != 1:
                        status, reason = "unavailable", "completion_revision_order_ambiguous"
                    else:
                        fact = best[0]
                        selected = CompletionSelection(check.check_id, goal.instance_key,
                            goal.native_record_id, fact.invocation_id, cast(str, fact.effect_id),
                            cast(int, fact.expected_revision), cast(int, fact.applied_revision))
                        status, reason = "eligible", "completion_observed_qualified_transition"
                elif effects.complete:
                    reason = "completion_no_qualified_transition"
                else:
                    status, reason = "unavailable", "completion_action_evidence_unavailable"
        findings.append(CompletionFinding(goal.instance_key, goal.candidate_identity,
            goal.native_record_id, status, reason, initial, selected))
    return CompletionEvaluation(outcome.source_digest, outcome.check_digest,
        _digest(rule.model_dump(mode="json")), outcome, tuple(findings), effects.complete,
        "completion_evaluated_observed_transitions")
