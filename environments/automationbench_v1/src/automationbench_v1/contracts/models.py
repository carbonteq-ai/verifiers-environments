"""Strict immutable pilot manifests; task identity never selects checking code."""

import math
from datetime import date, datetime
from types import MappingProxyType
from typing import Annotated, Literal, cast, get_args

from pydantic import (
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_serializer,
    field_validator,
    model_validator,
)

from automationbench.schema.salesforce.contact import Contact
from automationbench.schema.salesforce.opportunity import Opportunity

from .aggregates import _admit as admit_aggregate
from .authored_outputs import AuthoredOutputSource
from .base import FrozenModel, Identifier
from .created_objects import CreatedRetainedCheck
from .created_records import CreatedRecordSource
from .effects import EffectSource
from .existentials import exists_names
from .external_outputs import ExternalOutputSource
from .gmail_observations import GmailObservationSource
from .guards import GuardCheck
from .hubspot_objects import HubSpotObjectSource
from .jira_effects import JiraIssueSource
from .linkedin_reads import LinkedInReadSource
from .no_clarification import NoClarificationCheck
from .notification_effects import NotificationEffectSource
from .obligations import ObligationCheck, _fields
from .populations import InitialCollectionSource, _field, _model
from .record_writes import RecordWriteSource
from .requests import RequestSource
from .retained import RetainedRowCheck
from .retained_records import RetainedRecordCheck, RetainedRecordSource
from .sheet_effects import SheetEffectSource
from .sheet_reads import SheetReadSource
from .slack_effects import SlackEffectSource
from .slack_reads import SlackReadSource
from .summary_policy import SummaryExclusionCheck
from .tables import TableSource
from .zendesk_effects import ZendeskTicketEffectSource


class FieldSpec(FrozenModel):
    field: Identifier
    value: StrictStr | StrictInt | StrictFloat
    comparison: Literal["string", "number", "integer", "calendar_date"] = "string"

    @field_validator("value", mode="before")
    @classmethod
    def strict_value(cls, value):
        if (
            type(value) not in {str, int, float}
            or isinstance(value, float)
            and not math.isfinite(value)
        ):
            raise ValueError("field_value_requires_finite_strict_scalar")
        return value

    @model_validator(mode="after")
    def comparison_value(self):
        valid = (
            type(self.value) is str
            if self.comparison in {"string", "calendar_date"}
            else type(self.value) is int
            if self.comparison == "integer"
            else type(self.value) in {int, float}
        )
        if not valid:
            raise ValueError("field_comparison_value_type_mismatch")
        if self.comparison == "calendar_date" and (
            not isinstance(self.value, str)
            or date.fromisoformat(self.value).isoformat() != self.value
        ):
            raise ValueError("calendar_date_requires_canonical_iso_date")
        return self


def _unique_fields(fields: tuple[FieldSpec, ...]):
    if len({field.field for field in fields}) != len(fields):
        raise ValueError("duplicate_record_field")


class RecordSource(FrozenModel):
    adapter: Literal["salesforce.record@1"]
    object_type: Identifier
    record_id: Identifier
    baseline_requirements: tuple[FieldSpec, ...] = ()

    @model_validator(mode="after")
    def supported_source(self):
        _unique_fields(self.baseline_requirements)
        # This explicit installed capability registry is service/schema based;
        # adding task data cannot dynamically import code or unlock an adapter.
        if self.object_type not in {"Opportunity", "Contact"}:
            raise ValueError("record_object_capability_unimplemented")
        for field in self.baseline_requirements:
            _validate_installed_field(self.object_type, field)
        return self


def _validate_installed_field(object_type: str, field: FieldSpec):
    schema = {"Opportunity": Opportunity, "Contact": Contact}.get(object_type)
    if schema is None or field.field not in schema.model_fields:
        raise ValueError("record_schema_field_unimplemented")
    annotation = schema.model_fields[field.field].annotation
    kinds = get_args(annotation) or (annotation,)
    allowed = {
        str: {"string"},
        int: {"integer", "number"},
        float: {"number"},
        datetime: {"calendar_date"},
        date: {"calendar_date"},
    }
    if not any(field.comparison in allowed.get(kind, set()) for kind in kinds):
        raise ValueError("record_schema_comparison_incompatible")


class CheckSpec(FrozenModel):
    check_id: Identifier
    signal_id: Identifier
    role: Literal["goal", "diagnostic"]
    operator: Literal["record.fields_equal@1", "record.coverage@1"]
    source: Identifier
    expected: tuple[FieldSpec, ...] = ()

    @model_validator(mode="after")
    def check_shape(self):
        _unique_fields(self.expected)
        if self.operator == "record.fields_equal@1":
            if not self.expected or self.role != "goal":
                raise ValueError("fields_equal_requires_goal_and_expected_fields")
        elif self.expected or self.role != "diagnostic":
            raise ValueError("coverage_requires_diagnostic_without_expected_fields")
        return self


class CreditSpec(FrozenModel):
    check: Identifier | None = None
    checks: tuple[Identifier, ...] = ()
    policy: Literal[
        "verified_transition_once@1",
        "joint_verified_transition_once@1",
        "per_effect_negative@1",
        "required_effect_once@1",
        "retained_completion_once@1",
        "created_retained_completion_once@1",
        "records_retained_completion_once@1",
        "summary_action_negative_once@1",
    ]
    channel: Identifier
    goal_fields: tuple[Identifier, ...] = Field(default=(), exclude_if=lambda value: not value)
    completion_selection: Literal["earliest"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    effects: Identifier | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="before")
    @classmethod
    def completion_fields_only(cls, value):
        if isinstance(value, dict):
            if "goal_fields" in value and value.get("policy") not in {
                "retained_completion_once@1",
                "created_retained_completion_once@1",
                "records_retained_completion_once@1",
            }:
                raise ValueError("goal_fields_only_for_retained_completion")
            if "completion_selection" in value and value.get("policy") not in {
                "created_retained_completion_once@1",
                "records_retained_completion_once@1",
            }:
                raise ValueError("completion_selection_only_for_created_retained")
            if "effects" in value and value.get("policy") != "records_retained_completion_once@1":
                raise ValueError("effects_source_only_for_record_retained_completion")
        return value

    @model_validator(mode="after")
    def policy_shape(self):
        if self.policy in {
            "verified_transition_once@1",
            "per_effect_negative@1",
            "required_effect_once@1",
            "retained_completion_once@1",
            "created_retained_completion_once@1",
            "records_retained_completion_once@1",
            "summary_action_negative_once@1",
        }:
            if self.check is None or self.checks:
                raise ValueError("solo_credit_requires_check_only")
        elif (
            self.check is not None
            or len(self.checks) < 2
            or len(set(self.checks)) != len(self.checks)
        ):
            raise ValueError("joint_credit_requires_unique_goal_checks")
        if self.policy == "retained_completion_once@1" and (
            not self.goal_fields or len(set(self.goal_fields)) != len(self.goal_fields)
        ):
            raise ValueError("retained_completion_requires_unique_goal_fields")
        if self.policy == "created_retained_completion_once@1" and (
            self.completion_selection != "earliest"
            or not self.goal_fields
            or len(set(self.goal_fields)) != len(self.goal_fields)
        ):
            raise ValueError(
                "created_completion_requires_explicit_selection_and_unique_goal_fields"
            )
        if self.policy == "records_retained_completion_once@1" and (
            self.completion_selection != "earliest"
            or self.effects is None
            or not self.goal_fields
            or len(set(self.goal_fields)) != len(self.goal_fields)
        ):
            raise ValueError("record_completion_requires_effects_earliest_and_unique_goal_fields")
        return self


class SourceBinding(FrozenModel):
    path: tuple[StrictStr | StrictInt, ...]
    canonical_sha256: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def valid_path(self):
        if not self.path or any(type(part) is int and part < 0 for part in self.path):
            raise ValueError("source_binding_path_empty_or_negative")
        return self


class ContractSpec(FrozenModel):
    schema_version: Literal[1]
    manifest_id: Identifier
    revision: Identifier
    public_request: StrictStr
    bindings: tuple[SourceBinding, ...] = ()
    sources: dict[
        str,
        Annotated[
            RecordSource
            | TableSource
            | InitialCollectionSource
            | RetainedRecordSource
            | RequestSource
            | EffectSource
            | NotificationEffectSource
            | SheetEffectSource
            | SlackEffectSource
            | RecordWriteSource
            | GmailObservationSource
            | SlackReadSource
            | SheetReadSource
            | LinkedInReadSource
            | JiraIssueSource
            | HubSpotObjectSource
            | CreatedRecordSource
            | ZendeskTicketEffectSource
            | AuthoredOutputSource
            | ExternalOutputSource,
            Field(discriminator="adapter"),
        ],
    ]
    checks: tuple[
        Annotated[
            CheckSpec
            | GuardCheck
            | ObligationCheck
            | RetainedRowCheck
            | RetainedRecordCheck
            | CreatedRetainedCheck
            | SummaryExclusionCheck
            | NoClarificationCheck,
            Field(discriminator="operator"),
        ],
        ...,
    ]
    credit: tuple[CreditSpec, ...] = ()

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int:
            raise ValueError("schema_version_requires_integer")
        return value

    @model_validator(mode="after")
    def resolved_references(self):
        if not self.sources or any(not key.strip() for key in self.sources) or not self.checks:
            raise ValueError("manifest_requires_named_sources_and_checks")
        checks = {check.check_id: check for check in self.checks}
        if len(checks) != len(self.checks):
            raise ValueError("duplicate_check_identity")
        signal_roles = {}
        for check in self.checks:
            if check.signal_id in signal_roles and signal_roles[check.signal_id] != check.role:
                raise ValueError("signal_role_meaning_conflict")
            signal_roles[check.signal_id] = check.role
        for check in self.checks:
            source = self.sources.get(check.source)
            if source is None:
                raise ValueError("unknown_check_source")
            existential = exists_names(check)
            if existential:
                if not isinstance(check, (ObligationCheck, GuardCheck)):
                    raise ValueError("exists_requires_effect_check")
                if any(lookup.alias == "population" for lookup in check.lookups):
                    raise ValueError("exists_context_alias_conflict")
                for name in existential:
                    population = self.sources.get(name)
                    if not isinstance(population, (TableSource, InitialCollectionSource)) or (
                        population.path[:2] != ("task_evidence", "initial")
                    ):
                        raise ValueError("exists_requires_initial_population")
            if isinstance(check, (SummaryExclusionCheck, NoClarificationCheck)):
                if not isinstance(source, AuthoredOutputSource) or not isinstance(
                    self.sources.get(check.external), ExternalOutputSource
                ):
                    raise ValueError("summary_requires_authored_and_external_output_sources")  # noqa: TRY004
            elif isinstance(check, CheckSpec):
                if not isinstance(source, RecordSource):
                    raise ValueError("record_check_requires_record_source")  # noqa: TRY004
                for field in check.expected:
                    _validate_installed_field(source.object_type, field)
            elif isinstance(check, RetainedRecordCheck):
                population = self.sources.get(check.population)
                if not isinstance(source, RetainedRecordSource) or not isinstance(
                    population, InitialCollectionSource
                ):
                    raise ValueError("record_retained_requires_typed_collections")  # noqa: TRY004
                if population.path[2:] != source.path[2:]:
                    raise ValueError("record_retained_population_scope_mismatch")
                projections = {"request": population, "retained": source}
                for lookup in check.lookups:
                    lookup_source = self.sources.get(lookup.source)
                    if not isinstance(lookup_source, InitialCollectionSource):
                        raise ValueError("record_retained_requires_initial_lookup")  # noqa: TRY004
                    if set(lookup.keys) != set(lookup_source.key_fields):
                        raise ValueError("record_retained_lookup_key_inventory_mismatch")
                    projections[lookup.alias] = lookup_source
                for predicate in (check.required_when, check.supported_when, check.retained_when):
                    if predicate is None:
                        continue
                    for path in _fields(predicate.model_dump(mode="python")):
                        if path[0] == "candidate":
                            if len(path) != 2 or path[1] not in {"identity", "native_record_id"}:
                                raise ValueError("record_retained_candidate_metadata_unknown")
                            continue
                        projection = projections[path[0]]
                        if path[1] not in projection.fields:
                            raise ValueError("record_retained_predicate_projection_undeclared")
                        _field(
                            _model(cast(str, projection.path[2]), cast(str, projection.path[3])),
                            (*projection.fields[path[1]], *path[2:]),
                        )
            elif isinstance(check, CreatedRetainedCheck):
                if not isinstance(source, (JiraIssueSource, HubSpotObjectSource, CreatedRecordSource)):
                    raise ValueError("created_requires_issue_selector")  # noqa: TRY004
                if not isinstance(self.sources.get(check.population), RequestSource):
                    raise ValueError("created_requires_authored_request_population")  # noqa: TRY004
            else:
                if isinstance(check, RetainedRowCheck) and not isinstance(
                    source, SheetEffectSource
                ):
                    raise ValueError("retained_requires_sheet_selector")  # noqa: TRY004
                if isinstance(source, GmailObservationSource) and not isinstance(
                    check, ObligationCheck
                ):
                    raise ValueError("gmail_observation_requires_obligation_check")  # noqa: TRY004
                if isinstance(source, SlackReadSource) and not isinstance(check, ObligationCheck):
                    raise ValueError("slack_read_requires_obligation_check")  # noqa: TRY004
                if isinstance(source, SheetReadSource) and not isinstance(check, ObligationCheck):
                    raise ValueError("sheet_read_requires_obligation_check")  # noqa: TRY004
                if isinstance(source, LinkedInReadSource) and not isinstance(check, ObligationCheck):
                    raise ValueError("linkedin_read_requires_obligation_check")  # noqa: TRY004
                if not isinstance(
                    source,
                    (
                        EffectSource,
                        NotificationEffectSource,
                        SheetEffectSource,
                        SlackEffectSource,
                        GmailObservationSource,
                        SlackReadSource,
                        SheetReadSource,
                        LinkedInReadSource,
                        RecordWriteSource,
                    ),
                ):
                    raise ValueError("guard_requires_effect_source")  # noqa: TRY004
                population_types = (
                    (TableSource, InitialCollectionSource, RequestSource)
                    if isinstance(check, (ObligationCheck, GuardCheck))
                    else (TableSource,)
                )
                if not isinstance(self.sources.get(check.population), population_types):
                    raise ValueError("effect_check_requires_supported_population")  # noqa: TRY004
                if isinstance(self.sources.get(check.population), RequestSource) and (
                    isinstance(check, RetainedRowCheck)
                    or isinstance(check, ObligationCheck) and (
                        check.semantics != "new_occurrence" or check.initially_satisfied_when is not None
                    )
                ):
                    raise ValueError("request_population_requires_new_occurrence")
                if isinstance(check, ObligationCheck):
                    for alternative in check.alternatives:
                        if not isinstance(self.sources.get(alternative.source), (
                            EffectSource, NotificationEffectSource, SheetEffectSource, SlackEffectSource,
                            GmailObservationSource, SlackReadSource, SheetReadSource, LinkedInReadSource, RecordWriteSource,
                        )):
                            raise ValueError("obligation_alternative_requires_effect_source")  # noqa: TRY004
                if isinstance(check, GuardCheck):
                    for alternative in check.alternatives:
                        if not isinstance(self.sources.get(alternative.source), (
                            EffectSource, NotificationEffectSource, SheetEffectSource, SlackEffectSource,
                            RecordWriteSource,
                        )):
                            raise ValueError("guard_alternative_requires_effect_source")  # noqa: TRY004
                    for selection in check.selections:
                        if not isinstance(self.sources.get(selection.population), (
                            TableSource, InitialCollectionSource,
                        )):
                            raise ValueError("guard_selection_requires_initial_population")  # noqa: TRY004
                if isinstance(check, (ObligationCheck, GuardCheck)):
                    for join in check.effect_joins:
                        if not isinstance(self.sources.get(join.source), (
                            EffectSource, NotificationEffectSource, SheetEffectSource, SlackEffectSource,
                            GmailObservationSource, SlackReadSource, SheetReadSource, LinkedInReadSource, RecordWriteSource,
                        )):
                            raise ValueError("obligation_join_requires_effect_source")  # noqa: TRY004
                for item in check.aggregates if isinstance(check, ObligationCheck) else ():
                    aggregate_source = self.sources.get(item.aggregate.population)
                    if not isinstance(aggregate_source, (TableSource, InitialCollectionSource)):
                        raise ValueError("obligation_aggregate_requires_initial_population")  # noqa: TRY004
                    admit_aggregate(item.aggregate, aggregate_source)
                if isinstance(check, RetainedRowCheck):
                    population = self.sources[check.population]
                    assert isinstance(population, TableSource) and isinstance(
                        source, SheetEffectSource
                    )
                    if population.path[:2] != ("task_evidence", "initial"):
                        raise ValueError("retained_requires_initial_population")
                    if (population.spreadsheet_id, population.worksheet_id) != (
                        source.spreadsheet_id,
                        source.worksheet_id,
                    ):
                        raise ValueError("retained_population_scope_mismatch")
                for lookup in check.lookups:
                    table = self.sources.get(lookup.source)
                    if isinstance(table, RequestSource):
                        raise ValueError("request_population_lookup_unsupported")  # noqa: TRY004
                    if not isinstance(table, population_types):
                        raise ValueError("effect_lookup_requires_supported_population")  # noqa: TRY004
                    if set(lookup.keys) != set(table.key_fields):
                        raise ValueError("guard_lookup_key_inventory_mismatch")
                    if isinstance(check, RetainedRowCheck) and table.path[:2] != (
                        "task_evidence",
                        "initial",
                    ):
                        raise ValueError("retained_requires_initial_population")
        if len({binding.path for binding in self.bindings}) != len(self.bindings):
            raise ValueError("duplicate_source_binding_path")
        if len(
            {(rule.check, tuple(sorted(rule.checks)), rule.channel) for rule in self.credit}
        ) != len(self.credit):
            raise ValueError("duplicate_credit_check_channel")
        for rule in self.credit:
            parents = (rule.check,) if rule.check is not None else rule.checks
            role = (
                "harm"
                if rule.policy in {"per_effect_negative@1", "summary_action_negative_once@1"}
                else "goal"
            )
            if any(parent not in checks or checks[parent].role != role for parent in parents):
                raise ValueError("credit_requires_known_" + role + "_check")
            expected_type = (
                SummaryExclusionCheck
                if rule.policy == "summary_action_negative_once@1"
                else RetainedRecordCheck
                if rule.policy == "records_retained_completion_once@1"
                else CreatedRetainedCheck
                if rule.policy == "created_retained_completion_once@1"
                else RetainedRowCheck
                if rule.policy == "retained_completion_once@1"
                else ObligationCheck
                if rule.policy == "required_effect_once@1"
                else GuardCheck
                if rule.policy == "per_effect_negative@1"
                else CheckSpec
            )
            if any(not isinstance(checks[parent], expected_type) for parent in parents):
                raise ValueError("credit_policy_check_capability_mismatch")
            if rule.policy == "required_effect_once@1" and any(
                getattr(checks[parent], "match_cardinality", None) == "per_candidate" for parent in parents
            ):
                # One effect can witness many candidates; once-only credit would
                # need an explicit aggregation policy.
                raise ValueError("per_candidate_obligation_credit_requires_aggregation")
            if len({checks[parent].signal_id for parent in parents}) != 1:
                raise ValueError("joint_credit_requires_shared_signal")
            if rule.policy == "records_retained_completion_once@1":
                check = checks[parents[0]]
                assert isinstance(check, RetainedRecordCheck)
                initial, final = self.sources[check.population], self.sources[check.source]
                assert isinstance(initial, InitialCollectionSource) and isinstance(
                    final, RetainedRecordSource
                )
                if not isinstance(
                    self.sources.get(cast(str, rule.effects)), ZendeskTicketEffectSource
                ):
                    raise ValueError("record_completion_requires_zendesk_effects")
                if final.path[2:] != ("zendesk", "tickets"):
                    raise ValueError("record_completion_effect_scope_mismatch")
                read = {
                    path[1]
                    for path in _fields(check.retained_when.model_dump(mode="python"))
                    if path[0] == "retained"
                }
                if not set(rule.goal_fields) <= read:
                    raise ValueError("record_completion_goal_field_not_read")
                if any(initial.fields.get(alias) != final.fields[alias] for alias in read):
                    raise ValueError("record_completion_initial_goal_projection_mismatch")
            if rule.policy == "retained_completion_once@1":
                assert rule.check is not None
                check = checks[rule.check]
                assert isinstance(check, RetainedRowCheck)
                selector = self.sources[check.source]
                if not isinstance(selector, SheetEffectSource) or selector.kind != "update":
                    raise ValueError("retained_completion_requires_update_selector")
                fields = {
                    path[1]
                    for path in _fields(check.retained_when.model_dump(mode="python"))
                    if len(path) >= 2 and path[0] == "retained"
                }
                if not set(rule.goal_fields) <= fields:
                    raise ValueError("retained_completion_goal_field_not_read")
            if rule.policy == "created_retained_completion_once@1":
                assert rule.check is not None
                check = checks[rule.check]
                assert isinstance(check, CreatedRetainedCheck)
                if isinstance(self.sources[check.source], CreatedRecordSource):
                    # Outcome-only adapter: retained objects never imply action credit.
                    raise ValueError("created_completion_requires_native_object_adapter")
                fields = {
                    path[2]
                    for path in _fields(check.retained_when.model_dump(mode="python"))
                    if len(path) >= 3 and path[:2] == ("retained", "fields")
                }
                if not set(rule.goal_fields) <= fields:
                    raise ValueError("created_completion_goal_field_not_read")
        object.__setattr__(self, "sources", MappingProxyType(dict(self.sources)))
        return self

    @field_serializer("sources")
    def serialize_sources(self, value):
        return {key: source.model_dump(mode="json") for key, source in value.items()}
