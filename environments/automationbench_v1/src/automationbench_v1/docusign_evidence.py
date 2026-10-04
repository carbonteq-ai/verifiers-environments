"""Acknowledged simulator envelope sends, separate from signatures and rewards."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .effect_index import EffectIndex
from .notification_evidence import operation, result_payload


@dataclass(frozen=True)
class EnvelopeSendEffect:
    origin: str
    invocation_id: str
    expected_revision: int | None
    applied_revision: int | None
    status: Literal["qualified", "unavailable"]
    reason: str
    envelope_id: str | None = None
    envelope: Mapping[str, Any] | None = None


def _send_operation(name: str, args: Mapping) -> bool:
    if name in {
        "docusign_send_envelope",
        "docusign_create_envelope_from_template",
        "docusign_create_envelope",
    }:
        return True
    if name == "api_fetch":
        method = str(args.get("method", "")).upper()
        path = str(args.get("url", "")).split("?", 1)[0]
        return bool(
            method == "POST"
            and re.search(r"/accounts/[^/]+/envelopes$", path)
            or method == "PUT"
            and re.search(r"/accounts/[^/]+/envelopes/[^/]+$", path)
        )
    return False


def envelope_sends(index: EffectIndex) -> tuple[EnvelopeSendEffect, ...]:
    """Keep sends at their effect prefix; later voids cannot erase a send.

    Creation in draft mode is not a send. An already-sent record does not prove a
    new delivery. Unknown capture stays unavailable; unchanged envelopes under a
    known unrelated operation can be omitted. No status is promoted to signed.
    """
    effects = []
    for item in index.occurrences:
        identity = None
        envelope = None
        try:
            if item.action is None:
                raise ValueError("envelope_operation_capture_unavailable")
            name, args = operation(item.action)
            supported = _send_operation(name, args)
            if item.before_json is None or item.after_json is None:
                raise ValueError("envelope_world_capture_unavailable")
            before = index.collection(item.before_json, "docusign", "envelopes")
            after = index.collection(item.after_json, "docusign", "envelopes")
            for records in (before, after):
                ids = [record.get("id") for record in records]
                if any(not isinstance(value, str) or not value for value in ids) or len(ids) != len(
                    set(ids)
                ):
                    raise ValueError("envelope_population_identity_unresolved")
            if not supported:
                if before == after:
                    continue
                raise ValueError("envelope_effect_operation_unqualified")
            if item.evidence_status != "acknowledged":
                raise ValueError("envelope_acknowledgement_unavailable")
            if item.action.status != "returned" or item.action.error_json is not None:
                raise ValueError("envelope_operation_failed")
            result = result_payload(item.action)
            if result is None or "error" in result or result.get("success") is False:
                raise ValueError("envelope_result_unqualified")
            payload = result.get("envelope", result)
            if not isinstance(payload, Mapping):
                raise TypeError("envelope_result_schema_unresolved")
            identity = payload.get("envelopeId", payload.get("id"))
            if not isinstance(identity, str) or not identity:
                raise ValueError("envelope_result_identity_unresolved")
            matches = [record for record in after if record.get("id") == identity]
            previous = [record for record in before if record.get("id") == identity]
            if len(matches) != 1:
                raise ValueError("envelope_persisted_identity_unresolved")
            envelope = matches[0]
            if envelope.get("envelope_id") != identity:
                raise ValueError("envelope_alias_identity_unresolved")
            if name == "docusign_send_envelope" and args.get("envelope_id") != identity:
                raise ValueError("envelope_requested_identity_mismatch")
            if name == "docusign_create_envelope_from_template" and (
                args.get("template_id") != envelope.get("template_id")
            ):
                raise ValueError("envelope_requested_template_mismatch")
            if envelope.get("status") != "sent":
                # A supported create/update operation may legitimately be draft.
                if envelope.get("status") == "created":
                    continue
                raise ValueError("envelope_sent_effect_unqualified")
            if previous and previous[0].get("status") == "sent":
                raise ValueError("envelope_new_send_effect_unresolved")
            if payload.get("status") != "sent":
                raise ValueError("envelope_result_status_mismatch")
            signers = envelope.get("signers")
            if not isinstance(signers, (tuple, list)) or not signers or any(
                not isinstance(signer, Mapping)
                or not isinstance(signer.get("email"), str)
                or not signer.get("email")
                for signer in signers
            ):
                raise ValueError("envelope_signer_identity_unresolved")
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            effects.append(
                EnvelopeSendEffect(
                    item.origin, item.invocation_id, item.expected_revision,
                    item.applied_revision, "unavailable", str(error), identity, envelope,
                )
            )
        else:
            effects.append(
                EnvelopeSendEffect(
                    item.origin, item.invocation_id, item.expected_revision,
                    item.applied_revision, "qualified", "native_sent_transition",
                    identity, envelope,
                )
            )
    return tuple(effects)
