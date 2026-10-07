"""Business-neutral Salesforce record observations and acknowledged write facts.

Requested values and baseline policy belong to manifests. This adapter never
recognizes a task or decides that a particular field value is desirable.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, get_args

from automationbench.schema.salesforce.contact import Contact
from automationbench.schema.salesforce.opportunity import Opportunity

from ..capture import canonical_json
from ..effect_evidence import world_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation, result_payload

# This is an environment service capability, not a task registry.
RECORD_MODELS = {"Opportunity": ("opportunities", Opportunity), "Contact": ("contacts", Contact)}


@dataclass(frozen=True)
class WriteFact:
    occurrence: str
    before_json: str
    after_json: str
    qualified: bool
    reason: str
    requested_fields: tuple[str, ...]


@dataclass(frozen=True)
class RecordEvidence:
    initial_json: str | None
    final_json: str | None
    writes: tuple[WriteFact, ...]
    complete: bool
    recording_complete: bool
    reason: str
    source_digest: str
    selector_digest: str
    declared_fields: tuple[str, ...]


def source_digest(source: dict) -> str:
    return hashlib.sha256(canonical_json(source).encode()).hexdigest()


def selector_digest(selector) -> str:
    return hashlib.sha256(canonical_json(selector.model_dump(mode="json")).encode()).hexdigest()


FIELD_ALIASES = {
    "stage_name": "StageName",
    "amount": "Amount",
    "close_date": "CloseDate",
    "probability": "Probability",
    "description": "Description",
    "campaign_id": "CampaignId",
    "next_step": "NextStep",
    "type": "Type",
    "is_closed": "IsClosed",
    "is_won": "IsWon",
}
CONTACT_FIELD_ALIASES = {
    "first_name": "FirstName", "last_name": "LastName", "email": "Email", "phone": "Phone",
    "mobile_phone": "MobilePhone", "fax": "Fax", "account_id": "AccountId", "account_name": "AccountName",
    "title": "Title", "department": "Department", "assistant_name": "AssistantName", "assistant_email": "AssistantEmail",
    "description": "Description", "notes": "Notes", "status": "Status", "industry": "Industry",
    "years_at_company": "YearsAtCompany", "role": "Role", "seniority_level": "SeniorityLevel",
    "is_primary": "IsPrimary", "engagement_score": "EngagementScore", "lead_score": "LeadScore",
    "webinar_registered": "WebinarRegistered", "email_opt_out": "EmailOptOut", "timezone": "Timezone",
    "nda_status": "NdaStatus", "created_date": "CreatedDate", "owner_id": "OwnerId",
    "last_activity_date": "LastActivityDate", "last_modified_date": "LastModifiedDate",
}


def _aliases(object_type):
    return FIELD_ALIASES if object_type == "Opportunity" else CONTACT_FIELD_ALIASES


RESERVED_ARGUMENTS = {"id", "opportunity_id", "record_id", "recordId", "object", "object_type"}


def target_record(world: Mapping[str, Any], selector, *, declared=False) -> dict:
    capability = RECORD_MODELS.get(selector.object_type)
    if capability is None:
        raise ValueError("record_adapter_object_unsupported")
    collection, model = capability
    service = world.get("salesforce")
    if not isinstance(service, Mapping):
        raise TypeError("record_service_unavailable")
    records = service.get(collection)
    if not isinstance(records, (list, tuple)) or any(
        not isinstance(item, Mapping) for item in records
    ):
        raise ValueError("record_population_unavailable")
    identities = [item.get("id") for item in records]
    if any(not isinstance(item, str) or not item for item in identities) or len(
        set(identities)
    ) != len(identities):
        raise ValueError("record_population_identity_ambiguous")
    matched = [item for item in records if item["id"] == selector.record_id]
    if len(matched) != 1:
        raise ValueError("record_target_absent_or_ambiguous")
    # Business observations must not inherit Pydantic's numeric coercions.
    # Defaults and ISO date normalization remain native schema behavior.
    for name, field in model.model_fields.items():
        value = matched[0].get(name)
        if value is None:
            continue
        kinds = get_args(field.annotation) or (field.annotation,)
        numeric = {kind for kind in kinds if kind in (int, float)}
        if numeric and (type(value) not in (int, float)
                or (numeric == {int} and type(value) is not int)
                or (type(value) is float and not math.isfinite(value))):
            raise ValueError("record_raw_numeric_type_invalid:" + name)
    record = model.model_validate(dict(matched[0]))
    # Wall-clock default factories (created/modified timestamps absent from
    # public state) would make every capture, and so every rescore digest,
    # differ. An absent timestamp stays absent instead of becoming "now".
    clock = {name for name, field in model.model_fields.items()
             if field.default_factory is not None and name not in record.model_fields_set
             and datetime in (get_args(field.annotation) or (field.annotation,))}
    return record.model_dump(mode="json", exclude_unset=declared, exclude=clock or None)


def _requested_matches(requested: Mapping, returned: Mapping, record: dict, object_type: str) -> bool:
    """Bind requested native/display fields to the returned and persisted object."""
    model = RECORD_MODELS[object_type][1]
    display = model.model_validate(record).to_display_dict()
    actual = dict(record) | display
    requested_fields = {
        key: value for key, value in requested.items() if key not in RESERVED_ARGUMENTS
    }
    if not requested_fields:
        return False
    for key, value in requested_fields.items():
        display_key = "AccountName" if object_type == "Contact" and key == "Account.Name" else _aliases(object_type).get(key, key)
        if key not in actual and display_key not in actual:
            return False
        persisted = actual.get(key, actual.get(display_key))
        response = returned.get(display_key, returned.get(key))
        if key == "close_date" or display_key == "CloseDate":
            # Native schema expands a date to datetime, while public PATCH uses a date.
            if (
                not isinstance(value, str)
                or not isinstance(persisted, str)
                or not isinstance(response, str)
            ):
                return False
            try:
                dates = [
                    datetime.fromisoformat(item).date() for item in (value, persisted, response)
                ]
            except ValueError:
                return False
            if dates[0] != dates[1] or dates[0] != dates[2]:
                return False
        elif type(value) is bool:
            if (
                type(persisted) is not bool
                or type(response) is not bool
                or value != persisted
                or value != response
            ):
                return False
        elif (
            type(persisted) is bool
            or type(response) is bool
            or value != persisted
            or value != response
        ):
            return False
    return True


def qualified_requested_fields(action, selector, after: dict) -> tuple[str, ...] | None:
    if action.status != "returned" or action.error_json is not None:
        return None
    name, args = operation(action)
    payload = result_payload(action)
    if payload is None or "error" in payload:
        return None
    if name == "salesforce_opportunity_update" and selector.object_type == "Opportunity":
        if (args.get("id") or args.get("opportunity_id")) != selector.record_id:
            return None
        requested, returned = args, payload.get("opportunity")
    elif name == "salesforce_contact_update" and selector.object_type == "Contact":
        if args.get("id") != selector.record_id:
            return None
        requested, returned = args, payload.get("contact")
    elif name == "salesforce_update_record":
        if (args.get("object") or args.get("object_type")) != selector.object_type or (
            args.get("recordId") or args.get("record_id")
        ) != selector.record_id:
            return None
        requested, returned = args.get("fields"), payload.get("record")
        if isinstance(requested, str):
            requested = json.loads(requested)
    elif name == "api_fetch":
        path = str(args.get("url", "")).split("?", 1)[0]
        if (
            str(args.get("method", "")).upper() != "PATCH"
            or not re.fullmatch(
                r"(?:https?://[^/]+)?/services/data/v[\d.]+/sobjects/"
                + re.escape(selector.object_type)
                + "/"
                + re.escape(selector.record_id),
                path,
            )
            or payload != {}
        ):
            return None
        requested = args.get("body")
        # Documented simulator PATCH returns no record. Route + ACK + state must agree.
        if not isinstance(requested, Mapping):
            return None
        returned = RECORD_MODELS[selector.object_type][1].model_validate(after).to_display_dict()
    else:
        return None
    if not isinstance(requested, Mapping) or not isinstance(returned, Mapping):
        return None
    qualified = (
        (name == "api_fetch" or payload.get("success") is True)
        and (name == "api_fetch" or returned.get("Id") == selector.record_id)
        and _requested_matches(requested, returned, after, selector.object_type)
    )
    if not qualified:
        return None
    reverse = {value: key for key, value in _aliases(selector.object_type).items()}
    if selector.object_type == "Contact":
        reverse["Account.Name"] = "account_name"
    fields = tuple(
        sorted({reverse.get(key, key) for key in requested if key not in RESERVED_ARGUMENTS})
    )
    if not fields or any(field not in RECORD_MODELS[selector.object_type][1].model_fields for field in fields):
        return None
    return fields


def qualified_write(action, selector, after: dict) -> bool:
    return qualified_requested_fields(action, selector, after) is not None


def capture_records(source: dict, selectors: Mapping) -> dict[str, RecordEvidence]:
    """Decode each retained world once; capture union of check and credit inputs."""
    task = source["task_evidence"]
    identity = source_digest(source)
    try:
        index = EffectIndex(world_transitions(source))
        chain = index.serial_chain()
    except (ValueError, KeyError, TypeError) as error:
        index, chain = None, None
        capture_reason = str(error)
    else:
        capture_reason = "record_history_unqualified"
    captured = {}
    for source_id, selector in selectors.items():
        selection = selector_digest(selector)
        try:
            initial = target_record(task["initial"], selector)
            declared = target_record(task["initial"], selector, declared=True)
            final = target_record(task["final"], selector)
        except (ValueError, TypeError, KeyError) as error:
            captured[source_id] = RecordEvidence(
                None,
                None,
                (),
                False,
                False,
                str(error),
                identity,
                selection,
                (),
            )
            continue
        writes, snapshots_ok = [], True
        if index is not None and chain is not None:
            occurrences = chain.ordered if chain.status == "qualified" else index.occurrences
            for item in occurrences:
                try:
                    if item.before_json is None or item.after_json is None:
                        raise ValueError("record_snapshot_unavailable")
                    before = target_record(index.world(item.before_json), selector)
                    after = target_record(index.world(item.after_json), selector)
                    requested = (
                        qualified_requested_fields(item.action, selector, after)
                        if (item.evidence_status == "acknowledged" and item.action is not None)
                        else None
                    )
                    qualified = requested is not None
                    writes.append(
                        WriteFact(
                            item.invocation_id,
                            canonical_json(before),
                            canonical_json(after),
                            qualified,
                            "acknowledged_record_write"
                            if qualified
                            else "not_verified_record_write",
                            requested if requested is not None else (),
                        )
                    )
                except (ValueError, TypeError, KeyError):
                    snapshots_ok = False
        complete = task.get("complete") is True
        recording_complete = bool(
            complete
            and snapshots_ok
            and writes
            and chain is not None
            and index is not None
            and chain.status == "qualified"
            and chain.revision_interval is not None
            and chain.revision_interval[0] == 0
            and all(
                json.loads(writes[0].before_json).get(key) == value
                for key, value in declared.items()
            )
            and chain.ordered[-1].after_json == canonical_json(task["final"])
        )
        captured[source_id] = RecordEvidence(
            canonical_json(initial),
            canonical_json(final),
            tuple(writes),
            complete,
            recording_complete,
            "record_initial_chain_and_terminal_reconciled"
            if recording_complete
            else capture_reason,
            identity,
            selection,
            tuple(sorted(declared)),
        )
    return captured
