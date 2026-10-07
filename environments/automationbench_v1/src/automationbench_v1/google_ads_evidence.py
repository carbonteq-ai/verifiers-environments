"""Acknowledged offline conversion uploads over actual native append effects.

Zapier returns a native conversion ID. The API batch route returns no IDs, so
its support is the exact acknowledged call's ordered append/result join; several
objects share that call recipient. No finer per-object token span is invented.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .effect_index import EffectIndex
from .notification_evidence import operation, result_payload


@dataclass(frozen=True)
class ConversionEffect:
    invocation_id: str
    expected_revision: int | None
    applied_revision: int | None
    status: Literal["qualified", "unavailable"]
    reason: str
    conversion_id: str | None = None
    conversion: Mapping | None = None
    support: str = "call"


def conversions(world: Mapping) -> tuple[Mapping, ...]:
    service = world.get("google_ads", {})
    if not isinstance(service, Mapping):
        raise TypeError("google_ads_state_unresolved")
    records = service.get("conversions", ())
    if not isinstance(records, (tuple, list)) or any(not isinstance(row, Mapping) for row in records):
        raise ValueError("conversion_population_schema_unresolved")
    ids = [row.get("id") for row in records]
    if any(not isinstance(identity, str) or not identity for identity in ids) or len(set(ids)) != len(ids):
        raise ValueError("conversion_population_identity_unresolved")
    return tuple(records)


def _request(name: str, args: Mapping):
    if name in {"google_ads_send_offline_conversion", "google_ads_send_offline_conversion_v2"}:
        return args.get("mainAccountId"), (args,), False
    if name == "api_fetch" and str(args.get("method", "")).upper() == "POST":
        match = re.search(r"/googleads/v19/customers/([^/?]+):uploadClickConversions(?:\?.*)?$", str(args.get("url", "")))
        if match:
            body = args.get("body", {})
            if isinstance(body, str):
                body = json.loads(body)
            if not isinstance(body, Mapping):
                raise TypeError("conversion_request_body_unresolved")
            batch = body.get("conversions")
            if isinstance(batch, (tuple, list)):
                if any(not isinstance(item, Mapping) for item in batch):
                    raise ValueError("conversion_batch_schema_unresolved")
                return match[1], tuple(batch), True
            return match[1], (body,), False
    return None


def _matches(record: Mapping, account, args: Mapping, *, batch: bool):
    pairs = {
        "account_id": account,
        "gclid": args.get("gclid"),
        "conversion_name": args.get("conversionAction", "") if batch else args.get("name", ""),
        "conversion_value": str(args.get("conversionValue")) if batch and args.get("conversionValue") else args.get("value") or "0.01",
        "conversion_currency_code": args.get("currencyCode", "USD") if batch else args.get("currency", "USD"),
        "status": "success",
    }
    if not batch:
        pairs.update(email=args.get("email"), phone=args.get("phone"))
    return all(record.get(key) == value for key, value in pairs.items())


def conversion_uploads(index: EffectIndex) -> tuple[ConversionEffect, ...]:
    effects = []
    for occurrence in index.occurrences:
        try:
            if occurrence.before_json is None or occurrence.after_json is None:
                raise ValueError("conversion_capture_unavailable")
            before = conversions(index.world(occurrence.before_json))
            after = conversions(index.world(occurrence.after_json))
            request = None
            if occurrence.action is not None:
                request = _request(*operation(occurrence.action))
            if request is None:
                if before == after:
                    continue
                raise ValueError("conversion_operation_unqualified")
            if occurrence.action is None or occurrence.evidence_status != "acknowledged" or occurrence.action.status != "returned" or occurrence.action.error_json is not None:
                raise ValueError("conversion_acknowledgement_unavailable")
            result = result_payload(occurrence.action)
            if result is None or result.get("success") is False or "error" in result:
                raise ValueError("conversion_result_unqualified")
            account, entries, batch = request
            ids_before = {row["id"] for row in before}
            created = tuple(row for row in after if row["id"] not in ids_before)
            if len(created) != len(entries) or len(after) != len(before) + len(entries) or any(row not in after for row in before):
                raise ValueError("conversion_append_population_unresolved")
            if batch:
                results = result.get("results")
                if not isinstance(results, (tuple, list)) or len(results) != len(entries):
                    raise ValueError("conversion_batch_result_unresolved")
            else:
                if len(created) != 1 or result.get("conversion_id") != created[0]["id"]:
                    raise ValueError("conversion_returned_identity_unresolved")
            for position, (record, entry) in enumerate(zip(created, entries, strict=True)):
                if not _matches(record, account, entry, batch=batch):
                    raise ValueError("conversion_parameters_effect_disagreement")
                if batch:
                    response = results[position]
                    if not isinstance(response, Mapping) or response.get("gclid") != record.get("gclid") or response.get("conversionAction") != record.get("conversion_name") or datetime.fromisoformat(response.get("conversionDateTime", "")) != datetime.fromisoformat(record.get("conversion_time", "")):
                        raise ValueError("conversion_batch_result_effect_disagreement")
                else:
                    payload = result.get("conversion")
                    if not isinstance(payload, Mapping) or payload.get("conversion_id") != record["id"] or payload.get("googleClickId") != record.get("gclid") or payload.get("conversionValue") != record.get("conversion_value") or payload.get("status") != "success":
                        raise ValueError("conversion_result_effect_disagreement")
                effects.append(ConversionEffect(occurrence.invocation_id, occurrence.expected_revision, occurrence.applied_revision, "qualified", "acknowledged_batch_append" if batch else "acknowledged_native_conversion_id", record["id"], record))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            effects.append(ConversionEffect(occurrence.invocation_id, occurrence.expected_revision, occurrence.applied_revision, "unavailable", str(error)))
    return tuple(effects)
