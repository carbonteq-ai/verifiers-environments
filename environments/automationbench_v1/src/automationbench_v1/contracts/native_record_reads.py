"""Shared receipt and source reconciliation for audited native record searches."""

import hashlib
import json
from collections.abc import Mapping

from ..capture import canonical_json
from ..effect_evidence import observation_transitions
from ..effect_index import EffectIndex
from ..notification_evidence import operation, result_payload
from .effects import EffectEvidence, EffectFact
from .handler_scope import outside_service
from .service_hydration import public_service_matches
from .call_identity import same_call


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _equal(left, right):
    return canonical_json(_plain(left)) == canonical_json(_plain(right))


def capture_native_record_reads(source, spec, *, service, project, writes=()):
    source_id, selector_id = _digest(source), _digest(spec.model_dump(mode="json"))
    facts, reasons = [], []
    try:
        if any(not isinstance(source.get(key), (list, tuple)) for key in ("tool_execution_events", "state_write_receipts")):
            raise ValueError(f"{service}_read_execution_inventory_missing")
        index = EffectIndex(observation_transitions(dict(source)))
        terminals = {}
        for event in source["tool_execution_events"]:
            receipt = json.loads(event["receipt_json"])
            if receipt["phase"] != "dispatch":
                terminals[event["source"], receipt["invocation_id"]] = receipt
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return EffectEvidence(source_id, selector_id, (), False, str(error))
    for occurrence in index.occurrences:
        try:
            if (occurrence.origin != "tool_server" or occurrence.action is None or occurrence.before_json is None
                    or occurrence.after_json is None or EffectIndex((occurrence,)).serial_chain().status != "qualified"):
                raise ValueError(f"{service}_read_ack_or_capture_unavailable")
            action = occurrence.action
            before, after = index.world(occurrence.before_json), index.world(occurrence.after_json)
            name, args = operation(action)
            if outside_service(name, service, before, after):
                continue
            receipt = terminals[occurrence.origin, occurrence.invocation_id]
            arguments = json.loads(receipt.get("arguments_json", "null"))
            if (receipt.get("tool_name") != action.tool_name or not isinstance(arguments, dict)
                    or set(arguments) != {"args", "kwargs"} or arguments["args"] != []
                    or not same_call(action.tool_name, arguments["kwargs"], json.loads(action.arguments_json))):
                raise ValueError(f"{service}_read_native_invocation_mismatch")
            if (action.status != "returned" or action.error_json is not None or action.result_json is None
                    or receipt.get("error_json") is not None or receipt.get("state_error_json") is not None
                    or receipt.get("result_json") != action.result_json):
                raise ValueError(f"{service}_read_local_native_return_mismatch")
            if name in writes:
                continue
            if not _equal(before.get(service), after.get(service)):
                raise ValueError(f"{service}_read_changed_service")
            for params in project(before, name, args, result_payload(action)):
                facts.append(EffectFact(_digest([occurrence.invocation_id, params]), occurrence.invocation_id,
                    "tool_server", spec.kind, canonical_json(params), "qualified", f"acknowledged_native_{service}_search",
                    occurrence.expected_revision, occurrence.applied_revision))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            reasons.append(str(error))
            facts.append(EffectFact(None, occurrence.invocation_id, "tool_server", spec.kind, None,
                "unavailable", str(error), occurrence.expected_revision, occurrence.applied_revision))
    try:
        task = source["task_evidence"]
        if task.get("complete") is not True:
            raise ValueError(f"{service}_read_finalization_unavailable")
        chain = index.serial_chain()
        expected = {item.invocation_id for item in index.occurrences}
        if len(source["state_write_receipts"]) != len(expected) or {r["write_id"] for r in source["state_write_receipts"]} != expected:
            raise ValueError(f"{service}_read_ack_inventory_mismatch")
        if index.occurrences:
            if chain.status != "qualified" or chain.revision_interval is None or chain.revision_interval[0] != 0:
                raise ValueError(f"{service}_read_complete_chain_unavailable")
            first, last = chain.ordered[0], chain.ordered[-1]
            if (not public_service_matches(task["initial"], service, index.world(first.before_json)[service])
                    or not _equal(task["final"][service], index.world(last.after_json)[service])):
                raise ValueError(f"{service}_read_initial_terminal_scope_mismatch")
        elif not public_service_matches(task["initial"], service, task["final"][service]):
            raise ValueError(f"{service}_read_unobserved_scope_change")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        reasons.append(str(error))
    return EffectEvidence(source_id, selector_id, tuple(facts), not reasons,
        reasons[0] if reasons else f"reconciled_{service}_returned_record_inventory")
