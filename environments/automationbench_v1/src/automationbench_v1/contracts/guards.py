"""Conditional manifest guard operation over frozen tables and action evidence.

The operation reports witnessed prohibited simulator effects. It does not infer
external access grants, interpret prose, or normalize algorithm advantages.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from pydantic import Field, StrictInt, field_serializer, model_validator

from ..capture import canonical_json
from .base import FrozenModel, Identifier
from .effects import EffectEvidence, EffectFact, EffectSource
from .joins import EffectJoin, join_context, validate_join_paths
from .notification_effects import NotificationEffectSource
from .populations import lookup_population, native_record_id
from .predicates import (
    FieldValue,
    Predicate,
    evaluate_predicate,
    resolve_operand,
)
from .predicates import context_paths as _fields
from .record_writes import RecordWriteSource
from .sheet_effects import SheetEffectSource
from .slack_effects import SlackEffectSource
from .tables import TableEvidence, left_lookup


class LookupSpec(FrozenModel):
    source: Identifier
    alias: Identifier
    keys: dict[str, FieldValue]

    @model_validator(mode="after")
    def frozen_keys(self):
        if not self.keys or any(not key for key in self.keys):
            raise ValueError("guard_lookup_keys_required")
        if self.alias == "lookup":
            # Reserved: obligation contexts publish lookup outcomes under it.
            raise ValueError("lookup_alias_reserved")
        object.__setattr__(self, "keys", MappingProxyType(dict(self.keys)))
        return self

    @field_serializer("keys")
    def serialize_keys(self, value):
        return {key: operand.model_dump(mode="json") for key, operand in value.items()}


class GuardCheck(FrozenModel):
    check_id: Identifier
    signal_id: Identifier
    role: Literal["harm"]
    operator: Literal["effects.prohibited_when@1"]
    population: Identifier
    source: Identifier
    lookups: tuple[LookupSpec, ...] = ()
    prohibited_when: Predicate
    effect_match: Predicate
    match_cardinality: Literal["unique_candidate", "per_candidate"] = "unique_candidate"
    max_instances: StrictInt = Field(default=4096, ge=1, le=65536)
    # Links to effects of other declared sources (e.g. an action taken without a
    # prior read). Readable only by effect_match. Omitted when empty.
    effect_joins: tuple[EffectJoin, ...] = Field(default=(), exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def unique_aliases(self):
        aliases = [item.alias for item in self.lookups]
        if len(set(aliases)) != len(aliases) or set(aliases) & {
            "request", "effect", "candidate", "joined", "join", "lookup",
        }:
            raise ValueError("guard_lookup_alias_conflict")
        validate_join_paths(self.effect_joins, aliases)
        joined = {item.alias for item in self.effect_joins}
        for name in ("prohibited_when", "effect_match"):
            for path in _fields(getattr(self, name).model_dump(mode="json")):
                if path[0] == "lookup" and (len(path) != 2 or path[1] not in aliases):
                    raise ValueError("guard_lookup_status_reference_unknown")
                if path[0] in {"joined", "join"} and (
                    name != "effect_match" or len(path) < 2 or path[1] not in joined
                    or path[0] == "join" and len(path) != 2
                ):
                    raise ValueError("guard_join_reference_unknown")
        return self


@dataclass(frozen=True)
class GuardFinding:
    check_id: str
    instance_key: str
    signal_id: str
    value: float | None
    reason: str
    occurrence: str
    effect_id: str | None
    candidate_identity: tuple
    evidence_paths: tuple


@dataclass(frozen=True)
class GuardEvaluation:
    findings: tuple[GuardFinding, ...]
    compliance: float | None
    reason: str


@dataclass(frozen=True)
class GuardCase:
    instance_key: str
    occurrence: str
    effect_id: str | None
    candidate_identity: tuple


def plan_guard_instances(check: GuardCheck, population: TableEvidence, effects: EffectEvidence):
    """Inventory-only targets. No policy, matching or outcome evaluation here."""
    potential = len(population.rows) * len(effects.effects)
    if potential > check.max_instances:
        return (), potential
    identities = tuple(dict.fromkeys(row.identity for row in population.rows))
    return tuple(
        GuardCase(
            _digest([identity, effect.origin, effect.invocation_id, effect.effect_id]),
            effect.invocation_id,
            effect.effect_id,
            identity,
        )
        for identity in identities
        for effect in effects.effects
    ), potential


def _digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _selector_digest(spec) -> str:
    # Request selectors digest without unset fields, as their adapter does.
    from .requests import RequestSource

    return _digest(spec.model_dump(mode="json", exclude_none=isinstance(spec, RequestSource)))


def _bound(
    source: Mapping,
    tables: Mapping[str, Any],
    effects: EffectEvidence,
    spec: EffectSource | NotificationEffectSource | SheetEffectSource | SlackEffectSource | RecordWriteSource,
):
    identity = _digest(source)
    if effects.source_digest != identity or any(
        table.source_digest != identity for table in tables.values()
    ):
        raise ValueError("guard_evidence_source_mismatch")
    if effects.selector_digest != _digest(spec.model_dump(mode="json")):
        raise ValueError("guard_effect_selector_mismatch")


def _candidate_context(check: GuardCheck, row, tables: Mapping[str, Any]):
    context = {"request": json.loads(row.cells_json), "candidate": {
        "identity": list(row.identity), "native_record_id": native_record_id(row)}}
    for lookup in check.lookups:
        table = tables[lookup.source]
        keys = {}
        for key, operand in lookup.keys.items():
            known, value, _ = resolve_operand(operand, context)
            if not known:
                break
            keys[key] = value
        result = left_lookup(table, keys) if isinstance(table, TableEvidence) else lookup_population(table, keys)
        # Decided outcomes as data, as for obligations; ambiguous/unavailable
        # stay absent so predicates over them are unknown. Definite matches in
        # an ambiguous/partial lookup cannot supply a unique row's attributes.
        if result.status in {"matched", "not_found"}:
            context.setdefault("lookup", {})[lookup.alias] = result.status
        if result.status == "matched":
            context[lookup.alias] = json.loads(result.matches[0].cells_json)
    return context


def _effect_context(check, context, effect: EffectFact, params, join_effects):
    material = context | {"effect": params}
    if check.effect_joins:
        material |= join_context(check.effect_joins, effect, params, context, join_effects)
    return material


def _finding(check, row, effect: EffectFact, context, unique_match: bool, join_effects) -> GuardFinding:
    instance = _digest([row.identity, effect.origin, effect.invocation_id, effect.effect_id])
    if effect.status != "qualified" or effect.params_json is None:
        value, reason, paths = None, "guard_effect_unavailable", ()
    else:
        material = _effect_context(check, context, effect, json.loads(effect.params_json), join_effects)
        policy = evaluate_predicate(check.prohibited_when, material)
        match = evaluate_predicate(check.effect_match, material)
        if policy.value is False or match.value is False:
            value, reason = 0.0, "no_declared_prohibited_match"
        elif policy.value is None or match.value is None:
            value, reason = None, "guard_condition_or_match_unavailable"
        elif check.match_cardinality == "unique_candidate" and not unique_match:
            value, reason = None, "guard_effect_candidate_ambiguous"
        else:
            value, reason = 1.0, "witnessed_declared_prohibited_effect"
        paths = tuple(dict.fromkeys((*policy.evidence_paths, *match.evidence_paths)))
    return GuardFinding(
        check.check_id,
        instance,
        check.signal_id,
        value,
        reason,
        effect.invocation_id,
        effect.effect_id,
        row.identity,
        paths,
    )


def evaluate_guard(
    source: Mapping,
    check: GuardCheck,
    tables: Mapping[str, Any],
    effects: EffectEvidence,
    *,
    effect_source: EffectSource | NotificationEffectSource | SheetEffectSource | SlackEffectSource | RecordWriteSource,
    table_sources: Mapping[str, Any],
    join_effects: Mapping[str, EffectEvidence] | None = None,
    join_sources: Mapping[str, Any] | None = None,
) -> GuardEvaluation:
    """Keep event findings independent of later state and unrelated unknowns.

    Populations may be Sheets tables, typed initial collections or authored
    requests; all must share the authenticated source and declared selectors.
    """
    _bound(source, tables, effects, effect_source)
    if set(tables) != set(table_sources) or any(
        table.selector_digest != _selector_digest(table_sources[key]) for key, table in tables.items()
    ):
        raise ValueError("guard_table_selector_or_inventory_mismatch")
    join_effects, join_sources = dict(join_effects or {}), dict(join_sources or {})
    if set(join_effects) != {item.alias for item in check.effect_joins} or set(join_sources) != set(join_effects):
        raise ValueError("guard_join_inventory_mismatch")
    for alias, evidence in join_effects.items():
        if evidence.source_digest != _digest(source) or evidence.selector_digest != _selector_digest(
            join_sources[alias]
        ):
            raise ValueError("guard_join_evidence_mismatch")
    if check.population not in tables or any(item.source not in tables for item in check.lookups):
        raise ValueError("guard_table_reference_unknown")
    population = tables[check.population]
    if len(population.rows) * len(effects.effects) > check.max_instances:
        return GuardEvaluation((), None, "guard_instance_budget_exceeded")
    if not population.rows and population.status == "unavailable":
        return GuardEvaluation((), None, "guard_population_unavailable")
    findings = []
    contexts = [_candidate_context(check, row, tables) for row in population.rows]
    unique_matches = {}
    for effect in effects.effects:
        possible = []
        if effect.status == "qualified" and effect.params_json is not None:
            params = json.loads(effect.params_json)
            possible = [
                evaluate_predicate(
                    check.effect_match, _effect_context(check, context, effect, params, join_effects)
                ).value
                for context in contexts
            ]
        unique_matches[(effect.origin, effect.invocation_id, effect.effect_id)] = bool(
            population.enumerated and possible.count(True) == 1 and None not in possible
        )
    identities = Counter(row.identity for row in population.rows)
    logical_keys = Counter(row.key_json for row in population.rows if row.key_json is not None)
    ambiguous = set()
    for row, context in zip(population.rows, contexts, strict=True):
        ambiguous_reason = (
            "guard_candidate_identity_ambiguous"
            if identities[row.identity] > 1
            else "guard_candidate_key_unavailable"
            if row.key_json is None
            else "guard_candidate_key_ambiguous"
            if logical_keys[row.key_json] > 1
            else None
        )
        if ambiguous_reason is not None:
            if row.identity in ambiguous:
                continue
            ambiguous.add(row.identity)
            for effect in effects.effects:
                findings.append(
                    GuardFinding(
                        check.check_id,
                        _digest(
                            [row.identity, effect.origin, effect.invocation_id, effect.effect_id]
                        ),
                        check.signal_id,
                        None,
                        ambiguous_reason,
                        effect.invocation_id,
                        effect.effect_id,
                        row.identity,
                        (),
                    )
                )
            continue
        findings.extend(
            _finding(
                check,
                row,
                effect,
                context,
                unique_matches[(effect.origin, effect.invocation_id, effect.effect_id)],
                join_effects,
            )
            for effect in effects.effects
        )
    if any(item.value == 1 for item in findings):
        compliance, reason = 0.0, "witnessed_declared_guard_violation"
    elif (
        population.closed
        and effects.complete
        and all(table.closed for table in tables.values())
        and all(item.value is not None for item in findings)
    ):
        compliance, reason = 1.0, "closed_declared_guard_scope_without_violation"
    else:
        compliance, reason = None, "guard_compliance_scope_unavailable"
    return GuardEvaluation(tuple(findings), compliance, reason)


@dataclass(frozen=True)
class HarmSelection:
    check_id: str
    instance_key: str
    occurrence: str
    effect_id: str
    value: float


def select_harm(evaluation: GuardEvaluation) -> tuple[HarmSelection, ...]:
    """Explicit per-effect negative credit; no terminal-success gate or repair."""
    selected = []
    seen = set()
    for finding in evaluation.findings:
        if finding.value != 1:
            continue
        if finding.effect_id is None:
            raise ValueError("guard_harm_effect_identity_missing")
        key = (finding.check_id, finding.occurrence, finding.effect_id)
        if key in seen:
            raise ValueError("guard_harm_aggregation_required")
        seen.add(key)
        selected.append(
            HarmSelection(
                finding.check_id,
                finding.instance_key,
                finding.occurrence,
                finding.effect_id,
                -1.0,
            )
        )
    return tuple(selected)
