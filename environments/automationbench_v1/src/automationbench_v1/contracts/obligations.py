"""Required occurrence obligations over declared initial populations.

A witnessed occurrence is not proof of retained terminal state. Initial
satisfaction can discharge an obligation, but never earns new action credit.
An absent baseline predicate means unknown, not initially unsatisfied.

Declared aggregate aliases are recaptured from the raw source for every
evaluation and are visible only to ``effect_match``. An unavailable total leaves
the requirement in place and makes its effect match unknown.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, StrictInt, field_validator, model_validator

from ..capture import canonical_json
from .aggregates import AggregateEvidence, AggregateSpec, evaluate_aggregate
from .base import FrozenModel, Identifier
from .effects import EffectEvidence, EffectFact, EffectSource
from .execution_order import with_execution_order
from .existentials import exists_context, exists_names, exists_size
from .gmail_observations import GmailObservationSource
from .guards import LookupSpec
from .joins import EffectJoin, join_context, validate_join_paths
from .linkedin_reads import LinkedInReadSource
from .notification_effects import NotificationEffectSource
from .populations import InitialCollectionSource, Population, lookup_population, native_record_id
from .predicates import Predicate, evaluate_predicate, parse_predicate, resolve_operand
from .predicates import context_paths as _fields
from .record_writes import RecordWriteSource
from .requests import RequestSource
from .selections import (  # noqa: F401
    AlternativeEffect,
    OrderKey,
    SelectionAlias,
    _better,
    _order_key,
    _select,
)
from .sheet_effects import SheetEffectSource
from .sheet_reads import SheetReadSource
from .slack_effects import SlackEffectSource
from .slack_reads import SlackReadSource
from .tables import TableSource


def _observed_comparisons(raw):
    if raw["op"] in {"all", "any"}:
        return all(_observed_comparisons(arg) for arg in raw["args"])
    if raw["op"] == "not":
        return _observed_comparisons(raw["arg"])
    return bool(tuple(_fields(raw)))


AGGREGATE_FIELDS = frozenset({"value", "selected_count"})
_RESERVED = frozenset({
    "request", "effect", "candidate", "aggregate", "lookup", "member", "selected", "selection", "joined", "join",
})
_JOIN_BUDGET = 1_000_000


class AggregateAlias(FrozenModel):
    alias: Identifier
    aggregate: AggregateSpec


class ObligationCheck(FrozenModel):
    check_id: Identifier
    signal_id: Identifier
    role: Literal["goal"]
    operator: Literal["effects.required_when@1"]
    semantics: Literal["occurrence", "new_occurrence"] = "occurrence"
    population: Identifier
    source: Identifier
    lookups: tuple[LookupSpec, ...] = ()
    required_when: Predicate
    effect_match: Predicate
    initially_satisfied_when: Predicate | None = None
    # per_candidate: one effect may witness several candidates (e.g. one report
    # naming every department); each candidate is judged independently.
    match_cardinality: Literal["unique_candidate", "per_candidate"] = "unique_candidate"
    max_instances: StrictInt = Field(default=4096, ge=1, le=65536)
    # Omitted when empty so legacy declarations keep their canonical digests.
    aggregates: tuple[AggregateAlias, ...] = Field(default=(), exclude_if=lambda value: not value)
    selections: tuple[SelectionAlias, ...] = Field(default=(), exclude_if=lambda value: not value)
    effect_joins: tuple[EffectJoin, ...] = Field(default=(), exclude_if=lambda value: not value)
    alternatives: tuple[AlternativeEffect, ...] = Field(default=(), exclude_if=lambda value: not value)

    @field_validator("required_when", "effect_match", "initially_satisfied_when", mode="before")
    @classmethod
    def bounded_predicates(cls, value):
        if value is None:
            return value
        return parse_predicate(value)

    @model_validator(mode="after")
    def context_and_baseline(self):
        if self.semantics == "new_occurrence" and self.initially_satisfied_when is not None:
            raise ValueError("obligation_new_occurrence_has_no_initial_discharge")
        aliases = [lookup.alias for lookup in self.lookups]
        if len(set(aliases)) != len(aliases) or set(aliases) & _RESERVED:
            raise ValueError("obligation_lookup_alias_conflict")
        totals = {item.alias for item in self.aggregates}
        if len(totals) != len(self.aggregates):
            raise ValueError("obligation_aggregate_alias_conflict")
        chosen: list[str] = []
        for item in self.selections:
            if item.alias in chosen:
                raise ValueError("obligation_selection_alias_conflict")
            raw = [item.where.model_dump(mode="json"), *(key.model_dump(mode="json") for key in item.order_by)]
            for path in _fields(raw):
                if path[0] in {"selected", "selection"}:
                    if len(path) < 2 or path[1] not in chosen or path[0] == "selection" and len(path) != 2:
                        raise ValueError("obligation_selection_reference_unknown")
                elif path[0] == "lookup":
                    if len(path) != 2 or path[1] not in aliases:
                        raise ValueError("obligation_lookup_status_reference_unknown")
                elif len(path) < 2 or path[0] not in {"member", "request", "candidate", *aliases}:
                    raise ValueError("obligation_selection_context_unknown")
            chosen.append(item.alias)
        joined = [item.alias for item in self.effect_joins]
        if len(set(joined)) != len(joined) or set(joined) & _RESERVED:
            raise ValueError("obligation_join_alias_conflict")
        validate_join_paths(self.effect_joins, aliases, chosen)
        available = {"request", "candidate"}
        for lookup in self.lookups:
            if any(
                len(operand.path) < 2 or operand.path[0] not in available
                for operand in lookup.keys.values()
            ):
                raise ValueError("obligation_lookup_context_unavailable")
            available.add(lookup.alias)
        roots = {"request", "candidate", *aliases}
        alternative_aliases = [item.alias for item in self.alternatives]
        if len(set(alternative_aliases)) != len(alternative_aliases):
            raise ValueError("obligation_alternative_alias_conflict")
        named = [(name, getattr(self, name)) for name in ("required_when", "effect_match", "initially_satisfied_when")]
        named += [("effect_match", item.effect_match) for item in self.alternatives]
        for name, predicate in named:
            if predicate is None:
                continue
            raw = predicate.model_dump(mode="json")
            allowed = roots | {"effect"} if name == "effect_match" else roots
            for path in _fields(raw):
                if path[0] == "lookup":
                    if len(path) != 2 or path[1] not in aliases:
                        raise ValueError("obligation_lookup_status_reference_unknown")
                    continue
                if path[0] in {"selected", "selection"}:
                    if len(path) < 2 or path[1] not in chosen or path[0] == "selection" and len(path) != 2:
                        raise ValueError("obligation_selection_reference_unknown")
                    continue
                if path[0] in {"joined", "join"}:
                    if (name != "effect_match" or len(path) < 2 or path[1] not in joined
                            or path[0] == "join" and len(path) != 2):
                        raise ValueError("obligation_join_reference_unknown")
                    continue
                if name == "effect_match" and path[0] == "aggregate":
                    if len(path) != 3 or path[1] not in totals or path[2] not in AGGREGATE_FIELDS:
                        raise ValueError("obligation_aggregate_reference_unknown")
                elif len(path) < 2 or path[0] not in allowed:
                    raise ValueError("obligation_predicate_context_unknown")
            if name == "initially_satisfied_when" and not _observed_comparisons(raw):
                raise ValueError("obligation_baseline_requires_observed_comparisons")
        return self


@dataclass(frozen=True)
class ObligationWitness:
    occurrence: str
    effect_id: str
    expected_revision: int
    applied_revision: int
    evidence_paths: tuple


@dataclass(frozen=True)
class ObligationFinding:
    check_id: str
    instance_key: str
    signal_id: str
    candidate_identity: tuple
    status: Literal["valid", "inapplicable", "abstained"]
    value: float | None
    reason: str
    required: bool | None
    initially_satisfied: bool | None
    baseline_reason: str
    witnesses: tuple[ObligationWitness, ...]
    evidence_paths: tuple


@dataclass(frozen=True)
class ObligationEvaluation:
    source_digest: str
    check_digest: str
    findings: tuple[ObligationFinding, ...]
    scope_complete: bool
    reason: str
    semantics: Literal["occurrence", "new_occurrence"] = "occurrence"
    aggregates: tuple[tuple[str, AggregateEvidence], ...] = ()


@dataclass(frozen=True)
class ObligationCase:
    instance_key: str
    candidate_identity: tuple


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def obligation_population_names(check: ObligationCheck) -> set[str]:
    """Every population a check reads, including declared aggregate populations."""
    return {
        check.population,
        *(lookup.source for lookup in check.lookups),
        *(item.aggregate.population for item in check.aggregates),
        *(item.population for item in check.selections),
        *exists_names(check),
    }


def obligation_effect_names(check: ObligationCheck) -> set[str]:
    """Every effect source a check reads: its own, alternatives and joined sources."""
    return {check.source, *(item.source for item in check.effect_joins),
            *(item.source for item in check.alternatives)}


def evaluate_check_aggregates(source, check, population_sources):
    """Recapture each declared total from raw authority; nothing is accepted prepared."""
    return tuple(
        (
            item.alias,
            evaluate_aggregate(
                source, item.aggregate, population_source=population_sources[item.aggregate.population]
            ),
        )
        for item in check.aggregates
    )


def plan_obligation_instances(
    check: ObligationCheck, population: Population, effects: EffectEvidence
):
    """Inventory identities only; additions/reordering never renumber obligations."""
    potential = len(population.rows) * max(1, len(effects.effects))
    if potential > check.max_instances:
        return (), potential
    return tuple(
        ObligationCase(_digest([check.check_id, population.selector_digest, identity]), identity)
        for identity in dict.fromkeys(row.identity for row in population.rows)
    ), potential


def _bind(source, check, populations, effects, effect_source, population_sources):
    identity = _digest(source)
    required = obligation_population_names(check)
    if set(populations) != required or set(population_sources) != required:
        raise ValueError("obligation_population_inventory_mismatch")
    if effects.source_digest != identity or any(
        pop.source_digest != identity for pop in populations.values()
    ):
        raise ValueError("obligation_evidence_source_mismatch")
    if effects.selector_digest != _digest(effect_source.model_dump(mode="json")):
        raise ValueError("obligation_effect_selector_mismatch")
    for name, pop in populations.items():
        spec = population_sources[name]
        if pop.selector_digest != _digest(spec.model_dump(mode="json", exclude_none=isinstance(spec, RequestSource))):
            raise ValueError("obligation_population_selector_mismatch")
        if isinstance(spec, RequestSource):
            if name != check.population or check.semantics != "new_occurrence" or check.initially_satisfied_when is not None:
                raise ValueError("request_population_requires_new_occurrence")
        elif spec.path[:2] != ("task_evidence", "initial"):
            raise ValueError("obligation_requires_initial_population")
    for lookup in check.lookups:
        if isinstance(population_sources[lookup.source], RequestSource):
            raise ValueError("request_population_lookup_unsupported")  # noqa: TRY004
        if set(lookup.keys) != set(population_sources[lookup.source].key_fields):
            raise ValueError("obligation_lookup_key_inventory_mismatch")


def _context(check, row, populations, shared=None):
    context = {"request": json.loads(row.cells_json), "candidate": {
        "identity": list(row.identity), "native_record_id": native_record_id(row)}} | (shared or {})
    for lookup in check.lookups:
        keys = {}
        for key, operand in lookup.keys.items():
            known, value, _ = resolve_operand(operand, context)
            if not known:
                break
            keys[key] = value
        result = lookup_population(populations[lookup.source], keys)
        # Decided lookup outcomes as data. not_found is only reported for a
        # closed population with known keys; ambiguous/unavailable stay absent
        # so predicates over them are unknown, never a silent false.
        if result.status in {"matched", "not_found"}:
            context.setdefault("lookup", {})[lookup.alias] = result.status
        if result.status == "matched":
            context[lookup.alias] = json.loads(result.matches[0].cells_json)
    for selection in getattr(check, "selections", ()):
        outcome = _select(selection, context, populations[selection.population])
        if outcome is not None:
            status, member = outcome
            context.setdefault("selection", {})[selection.alias] = status
            if member is not None:
                context.setdefault("selected", {})[selection.alias] = member
    return context


def _qualified(effect: EffectFact, kind: str):
    if effect.status != "qualified":
        return None
    if (
        effect.origin != "tool_server"
        or effect.kind != kind
        or not effect.effect_id
        or not effect.invocation_id
        or effect.params_json is None
        or type(effect.expected_revision) is not int
        or effect.expected_revision < 0
        or type(effect.applied_revision) is not int
        or effect.applied_revision != effect.expected_revision + 1
    ):
        raise ValueError("obligation_qualified_effect_metadata_invalid")
    params = json.loads(effect.params_json)
    if not isinstance(params, dict) or canonical_json(params) != effect.params_json:
        raise ValueError("obligation_effect_params_invalid")
    return params


def evaluate_obligations(
    source: Mapping,
    check: ObligationCheck,
    populations: Mapping[str, Population],
    effects: EffectEvidence,
    *,
    effect_source: EffectSource | NotificationEffectSource | SheetEffectSource | SlackEffectSource | GmailObservationSource | SlackReadSource | SheetReadSource | LinkedInReadSource | RecordWriteSource,
    population_sources: Mapping[str, TableSource | InitialCollectionSource | RequestSource],
    join_effects: Mapping[str, EffectEvidence] | None = None,
    join_sources: Mapping[str, object] | None = None,
    alternative_effects: Mapping[str, EffectEvidence] | None = None,
    alternative_sources: Mapping[str, object] | None = None,
) -> ObligationEvaluation:
    """Assess occurrence outcomes independently of positive action attribution."""
    _bind(source, check, populations, effects, effect_source, population_sources)
    alternative_effects = dict(alternative_effects or {})
    alternative_sources = dict(alternative_sources or {})
    if (set(alternative_effects) != {item.alias for item in check.alternatives}
            or set(alternative_sources) != set(alternative_effects)):
        raise ValueError("obligation_alternative_inventory_mismatch")
    for alias, evidence in alternative_effects.items():
        if evidence.source_digest != _digest(source) or evidence.selector_digest != _digest(
            alternative_sources[alias].model_dump(mode="json")  # type: ignore[attr-defined]
        ):
            raise ValueError("obligation_alternative_evidence_mismatch")
    join_effects, join_sources = dict(join_effects or {}), dict(join_sources or {})
    if set(join_effects) != {item.alias for item in check.effect_joins} or set(join_sources) != set(join_effects):
        raise ValueError("obligation_join_inventory_mismatch")
    for alias, evidence in join_effects.items():
        spec = join_sources[alias]
        if evidence.source_digest != _digest(source) or evidence.selector_digest != _digest(
            spec.model_dump(mode="json")  # type: ignore[attr-defined]
        ):
            raise ValueError("obligation_join_evidence_mismatch")
    join_effects = with_execution_order(join_effects, source, check.effect_joins)
    source_id, check_id = _digest(source), _digest(check.model_dump(mode="json"))
    aggregates = evaluate_check_aggregates(source, check, population_sources)
    totals = {
        alias: {"value": evidence.canonical_value, "selected_count": evidence.selected_count}
        for alias, evidence in aggregates
        if evidence.status == "qualified"
    }
    population = populations[check.population]
    cases, potential = plan_obligation_instances(check, population, effects)
    if potential > check.max_instances:
        return ObligationEvaluation(
            source_id, check_id, (), False, "obligation_instance_budget_exceeded", check.semantics,
            aggregates,
        )
    scope_complete = (effects.complete and all(item.complete for item in alternative_effects.values())
                      and all(pop.closed for pop in populations.values()))
    if not population.rows:
        return ObligationEvaluation(
            source_id,
            check_id,
            (),
            scope_complete,
            "obligation_population_empty"
            if population.closed
            else "obligation_population_unavailable",
            check.semantics,
            aggregates,
        )
    facts, channel = {}, {}
    inventories = [("", effects, effect_source.kind, check.effect_match)]
    inventories += [(item.alias, alternative_effects[item.alias],
                     alternative_sources[item.alias].kind, item.effect_match)  # type: ignore[attr-defined]
                    for item in check.alternatives]
    for tag, evidence, kind, predicate in inventories:
        for fact in evidence.effects:
            key = (tag, fact.origin, fact.invocation_id, fact.effect_id)
            if key in facts and facts[key] != fact:
                raise ValueError("obligation_effect_identity_conflict")
            facts[key] = fact
            channel[key] = (kind, predicate)
    shared = exists_context(exists_names(check), populations)
    contexts = [_context(check, row, populations, shared) for row in population.rows]
    extra = {"aggregate": totals} if check.aggregates else {}
    totals_unavailable = len(totals) != len(aggregates)
    matches, unique = {}, {}
    joined_size = sum(len(evidence.effects) for evidence in join_effects.values())
    if len(facts) * len(contexts) * max(1, joined_size) * max(1, exists_size(shared)) > _JOIN_BUDGET:
        return ObligationEvaluation(
            source_id, check_id, (), False, "obligation_join_budget_exceeded", check.semantics, aggregates,
        )
    for key, effect in facts.items():
        kind, predicate = channel[key]
        params = _qualified(effect, kind)
        results = (
            tuple(
                evaluate_predicate(
                    predicate,
                    context | extra | {"effect": params}
                    | (join_context(check.effect_joins, effect, params, context, join_effects) if check.effect_joins else {}),
                )
                for context in contexts
            )
            if params is not None
            else ()
        )
        values = [result.value for result in results]
        matches[key] = results
        unique[key] = population.enumerated and (
            check.match_cardinality == "per_candidate" or values.count(True) == 1 and None not in values
        )
    identities = Counter(row.identity for row in population.rows)
    keys = Counter(row.key_json for row in population.rows if row.key_json is not None)
    case_keys = {case.candidate_identity: case.instance_key for case in cases}
    findings, seen = [], set()
    for index, (row, context) in enumerate(zip(population.rows, contexts, strict=True)):
        if row.identity in seen:
            continue
        seen.add(row.identity)
        if isinstance(population_sources[check.population], RequestSource) and population.status != "qualified":
            findings.append(ObligationFinding(check.check_id, case_keys[row.identity], check.signal_id,
                row.identity, "abstained", None, population.reason, None, None,
                "obligation_new_occurrence_initial_discharge_not_applicable", (), ()))
            continue
        requirement = evaluate_predicate(check.required_when, context)
        baseline = (
            evaluate_predicate(check.initially_satisfied_when, context)
            if check.initially_satisfied_when is not None
            else None
        )
        required = requirement.value
        initial = baseline.value if baseline is not None else None
        baseline_reason = (
            baseline.reason if baseline is not None else "obligation_baseline_not_declared"
        )
        if check.semantics == "new_occurrence":
            baseline_reason = "obligation_new_occurrence_initial_discharge_not_applicable"
        paths = list(requirement.evidence_paths) + (
            list(baseline.evidence_paths) if baseline else []
        )
        witnesses = []
        unresolved = False
        for key, effect in facts.items():
            result = matches[key][index] if matches[key] else None
            if result is not None:
                paths.extend(result.evidence_paths)
            if result is None or result.value is None or result.value is True and not unique[key]:
                unresolved = True
            elif result.value is True:
                witnesses.append(
                    ObligationWitness(
                        effect.invocation_id,
                        effect.effect_id,
                        effect.expected_revision,
                        effect.applied_revision,
                        result.evidence_paths,
                    )
                )
        witnesses.sort(
            key=lambda witness: (witness.applied_revision, witness.occurrence, witness.effect_id)
        )
        ambiguous = (
            not population.enumerated
            or identities[row.identity] > 1
            or row.key_json is None
            or keys[row.key_json] > 1
        )
        if ambiguous:
            status, value, reason = "abstained", None, "obligation_candidate_identity_unavailable"
            required, initial, witnesses = None, None, []
        elif required is False:
            status, value, reason = "inapplicable", None, "obligation_not_required"
        elif required is None:
            status, value, reason = "abstained", None, "obligation_requirement_unavailable"
        elif initial is True:
            status, value, reason = "valid", 1.0, "obligation_initially_satisfied"
        elif witnesses:
            status, value, reason = "valid", 1.0, "obligation_witnessed_required_effect"
        elif initial is None and check.semantics != "new_occurrence":
            status, value, reason = "abstained", None, "obligation_baseline_unavailable"
        elif unresolved and totals_unavailable:
            status, value, reason = "abstained", None, "obligation_aggregate_unavailable"
        elif not scope_complete or unresolved:
            status, value, reason = "abstained", None, "obligation_effect_scope_unavailable"
        else:
            status, value, reason = "valid", 0.0, "obligation_required_effect_missing"
        findings.append(
            ObligationFinding(
                check.check_id,
                case_keys[row.identity],
                check.signal_id,
                row.identity,
                status,
                value,
                reason,
                required,
                initial,
                baseline_reason,
                tuple(witnesses),
                tuple(dict.fromkeys(paths)),
            )
        )
    return ObligationEvaluation(
        source_id,
        check_id,
        tuple(findings),
        scope_complete,
        "obligation_scope_closed" if scope_complete else "obligation_scope_unavailable",
        check.semantics,
        aggregates,
    )


@dataclass(frozen=True)
class ObligationSelection:
    check_id: str
    instance_key: str
    occurrence: str
    effect_id: str
    value: float = 1.0


def select_obligation_credit(
    evaluation: ObligationEvaluation,
    *,
    consumed: Collection[str] = (),
) -> tuple[ObligationSelection, ...]:
    """Choose at most one witnessed action per qualifying obligation.

    Ordinary occurrence goals require observed initial non-satisfaction. The
    explicitly authored new-occurrence mode requires a fresh episode action;
    existing initial objects neither discharge that goal nor supply its witness.

    The caller owns the consumed ledger and must scope it to the same episode
    and contract. Snapshot, run and witness IDs must not reset that ledger.
    Selection uses the earliest *observed qualified* witness, not a claim of
    unique causal responsibility or a complete history's first occurrence.
    """
    selected, seen = [], set(consumed)
    for finding in evaluation.findings:
        if (
            finding.instance_key in seen
            or finding.status != "valid"
            or finding.value != 1
            or finding.required is not True
            or (
                evaluation.semantics != "new_occurrence"
                and finding.initially_satisfied is not False
            )
            or not finding.witnesses
        ):
            continue
        witness = finding.witnesses[0]
        seen.add(finding.instance_key)
        selected.append(
            ObligationSelection(
                finding.check_id, finding.instance_key, witness.occurrence, witness.effect_id
            )
        )
    return tuple(selected)
