"""One public direct-record-update strategy; native objects remain replay authority.

Contracts are authored from requests and schema, not from benchmark assertions.
Outcome, recording coverage and action attribution are separate. A successful
state check is not an inventory of general safety guards or a training weight.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import ValidationError

from automationbench.schema.salesforce.opportunity import Opportunity

from .capture import canonical_json
from .effect_evidence import world_transitions
from .effect_index import EffectIndex
from .hr_rules import Finding
from .notification_evidence import operation, result_payload


@dataclass(frozen=True)
class RecordField:
    name: str
    value: str | int | float
    comparison: Literal["string", "number", "integer", "calendar_date"] = "string"


@dataclass(frozen=True)
class RecordUpdateContract:
    revision: str
    task_name: str
    user_request: str
    service: str
    collection: str
    record_id: str
    desired_fields: tuple[RecordField, ...]
    baseline_requirements: tuple[RecordField, ...] = ()


def _equal(value, field: RecordField) -> bool:
    if field.comparison == "string":
        return isinstance(value, str) and value == field.value
    if field.comparison in {"number", "integer"}:
        if type(value) not in {int, float} or type(field.value) not in {int, float}:
            return False
        if field.comparison == "integer" and type(value) is not int:
            return False
        left, right = Decimal(str(value)), Decimal(str(field.value))
        return left.is_finite() and right.is_finite() and left == right
    if field.comparison == "calendar_date":
        if not isinstance(value, str) or not isinstance(field.value, str):
            return False
        try:
            return datetime.fromisoformat(value).date().isoformat() == field.value
        except ValueError:
            return False
    raise ValueError("record_field_comparison_unresolved")


def _records(world: Mapping, contract: RecordUpdateContract) -> tuple[Mapping, ...]:
    service = world.get(contract.service)
    if not isinstance(service, Mapping):
        raise TypeError("record_service_schema_unavailable")
    records = service.get(contract.collection)
    if not isinstance(records, (list, tuple)) or any(
        not isinstance(record, Mapping) for record in records
    ):
        raise ValueError("record_collection_schema_unavailable")
    identities = [record.get("id") for record in records]
    if any(not isinstance(identity, str) or not identity for identity in identities) or len(
        set(identities)
    ) != len(identities):
        raise ValueError("record_population_identity_unresolved")
    return tuple(records)


def _target(world: Mapping, contract: RecordUpdateContract) -> dict:
    if (contract.service, contract.collection) != ("salesforce", "opportunities"):
        raise ValueError("record_model_adapter_unimplemented")
    matches = [record for record in _records(world, contract) if record["id"] == contract.record_id]
    if len(matches) != 1:
        raise ValueError("record_target_absent_or_ambiguous")
    # Normalize dates/numbers exactly as the maintained native schema does.
    record = Opportunity.model_validate(dict(matches[0])).model_dump(mode="json")
    fields = contract.desired_fields + contract.baseline_requirements
    if any(field.name not in record for field in fields):
        raise ValueError("record_contract_field_schema_unavailable")
    return record


def _matches(record: Mapping, fields: tuple[RecordField, ...]) -> bool:
    return all(field.name in record and _equal(record[field.name], field) for field in fields)


_API_FIELDS = {
    "stage_name": "StageName",
    "amount": "Amount",
    "close_date": "CloseDate",
    "probability": "Probability",
    "description": "Description",
    "campaign_id": "CampaignId",
    "next_step": "NextStep",
    "type": "Type",
}


def _qualified_update(action, contract: RecordUpdateContract, after: Mapping) -> bool:
    """Bind supported operation, requested target/fields and native response identity.

    Salesforce PATCH explicitly returns an empty object in this simulator. Its
    route identity plus the acknowledged exact persisted field delta is required;
    the empty response alone never proves success.
    """
    name, args = operation(action)
    payload = result_payload(action)
    if payload is None or "error" in payload or payload.get("success") is False:
        return False
    if name == "salesforce_opportunity_update":
        if (args.get("id") or args.get("opportunity_id")) != contract.record_id:
            return False
        requested = args
        returned = payload.get("opportunity")
    elif name == "salesforce_update_record":
        if (args.get("object") or args.get("object_type")) != "Opportunity" or (
            args.get("recordId") or args.get("record_id")
        ) != contract.record_id:
            return False
        requested = args.get("fields")
        if isinstance(requested, str):
            try:
                requested = json.loads(requested)
            except json.JSONDecodeError:
                return False
        returned = payload.get("record")
    elif name == "api_fetch":
        path = str(args.get("url", "")).split("?", 1)[0]
        if (
            str(args.get("method", "")).upper() != "PATCH"
            or not re.fullmatch(
                r"(?:https?://[^/]+)?/services/data/v[\d.]+/sobjects/Opportunity/"
                + re.escape(contract.record_id),
                path,
            )
            or payload != {}
        ):
            return False
        requested = args.get("body")
        returned = None
    else:
        return False
    if not isinstance(requested, Mapping):
        return False
    for field in contract.desired_fields:
        key = field.name if field.name in requested else _API_FIELDS.get(field.name)
        if key is None or key not in requested or not _equal(requested[key], field):
            return False
    if name != "api_fetch":
        if payload.get("success") is not True:
            return False
        if not isinstance(returned, Mapping) or returned.get("Id") != contract.record_id:
            return False
        for field in contract.desired_fields:
            key = _API_FIELDS.get(field.name)
            if key is None or key not in returned or not _equal(returned[key], field):
                return False
    return _matches(after, contract.desired_fields)


def evaluate_record_update(source: dict, contract: RecordUpdateContract) -> tuple[Finding, ...]:
    """Assess final requested state and attribute a qualified surviving transition.

    Initial satisfaction survives without action credit. A write that first
    completes the request, damages it, and later restores it does not earn new
    accomplishment credit. Missing relevant capture prevents failure/coverage
    conclusions; independently supported final state can remain a goal fact.
    """
    evidence = source["task_evidence"]
    users = [item.get("content") for item in evidence["prompt"] if item.get("role") == "user"]
    if evidence["task_name"] != contract.task_name or users != [contract.user_request]:
        raise ValueError("record_exact_public_request_unresolved")
    if (
        not contract.revision
        or not contract.desired_fields
        or len({field.name for field in contract.desired_fields}) != len(contract.desired_fields)
    ):
        raise ValueError("record_update_contract_unresolved")
    try:
        initial = _target(evidence["initial"], contract)
        final = _target(evidence["final"], contract)
        if not _matches(initial, contract.baseline_requirements) and not _matches(
            initial, contract.desired_fields
        ):
            raise ValueError("record_baseline_interpretation_contract_required")
    except (ValueError, TypeError, KeyError, ValidationError) as error:
        return (
            Finding("simple.requested_state", None, str(error)),
            Finding("simple.recording_coverage", None, "target_or_schema_unavailable"),
        )
    index = EffectIndex(world_transitions(source))
    chain = index.serial_chain()
    complete = evidence.get("complete") is True
    captured = []
    schema_available = True
    for item in chain.ordered if chain.status == "qualified" else index.occurrences:
        try:
            if item.before_json is None or item.after_json is None:
                raise ValueError("record_snapshot_unavailable")
            before = _target(index.world(item.before_json), contract)
            after = _target(index.world(item.after_json), contract)
            captured.append((item, before, after))
        except (ValueError, TypeError, KeyError, ValidationError):
            schema_available = False
    coverage = (
        complete
        and chain.status == "qualified"
        and schema_available
        and bool(captured)
        and chain.revision_interval is not None
        and chain.revision_interval[0] == 0
        and all(
            captured[0][1].get(key) == value
            for key, value in Opportunity.model_validate(
                dict(
                    next(
                        record
                        for record in _records(evidence["initial"], contract)
                        if record["id"] == contract.record_id
                    )
                )
            )
            .model_dump(mode="json", exclude_unset=True)
            .items()
        )
        and chain.ordered[-1].after_json == canonical_json(evidence["final"])
    )
    initially_correct = _matches(initial, contract.desired_fields)
    finally_correct = _matches(final, contract.desired_fields)
    recipient = None
    damaged_after_completion = False
    seen_completion = initially_correct
    for item, before, after in captured:
        before_correct, after_correct = (
            _matches(before, contract.desired_fields),
            _matches(after, contract.desired_fields),
        )
        if seen_completion and not after_correct:
            damaged_after_completion = True
        if after_correct:
            seen_completion = True
        if (
            not before_correct
            and after_correct
            and recipient is None
            and item.evidence_status == "acknowledged"
            and item.action is not None
            and item.action.status == "returned"
            and item.action.error_json is None
            and _qualified_update(item.action, contract, after)
        ):
            recipient = item.invocation_id
    if complete and finally_correct:
        goal = Finding(
            "simple.requested_state",
            1.0,
            "already_correct_state"
            if initially_correct
            else "verified_final_requested_record_state",
            recipient
            if coverage and not initially_correct and not damaged_after_completion
            else None,
        )
    else:
        goal = Finding(
            "simple.requested_state",
            0.0 if coverage else None,
            "requested_record_not_completed" if coverage else "record_completion_unresolved",
        )
    return goal, Finding(
        "simple.recording_coverage",
        1.0 if coverage else None,
        "record_initial_chain_and_terminal_reconciled"
        if coverage
        else "record_recording_or_finalization_unresolved",
    )
