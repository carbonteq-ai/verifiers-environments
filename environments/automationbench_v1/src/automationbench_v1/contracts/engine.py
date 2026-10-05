"""Compile required checks before evaluation; retain one immutable output receipt."""

import hashlib
import json
import re
from dataclasses import asdict
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, model_validator

from ..capture import canonical_json
from .created_objects import CreatedRetainedCheck
from .evidence import RecordEvidence, WriteFact, capture_records, selector_digest, source_digest
from .guards import GuardCheck
from .loader import canonical_contract_digest
from .models import CheckSpec, ContractSpec, RecordSource
from .no_clarification import NoClarificationCheck
from .obligations import ObligationCheck
from .operators import OPERATORS, fields_equal
from .retained import RetainedRowCheck
from .retained_records import RetainedRecordCheck
from .summary_policy import SummaryExclusionCheck
from .terminal_counts import TerminalCountCheck


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    check_id: str
    signal_id: str
    status: Literal["valid", "abstained"]
    value: float | None
    reason: str
    evidence_refs: tuple[str, ...]

    @model_validator(mode="after")
    def value_matches_status(self):
        if (self.status == "valid") != (self.value is not None):
            raise ValueError("manifest_result_status_value_mismatch")
        if self.value is not None and self.value not in (0, 1):
            raise ValueError("manifest_result_binary_value_required")
        return self


class Evaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    contract_digest: str
    source_digest: str
    results: tuple[CheckResult, ...]
    evidence_json: str

    @model_validator(mode="after")
    def unique_checks(self):
        if len({item.check_id for item in self.results}) != len(self.results):
            raise ValueError("manifest_evaluation_duplicate_check")
        if self.evidence_json != canonical_json(json.loads(self.evidence_json)):
            raise ValueError("manifest_evaluation_noncanonical_evidence")
        evidence = restore_evidence(self.evidence_json)
        if any(item.source_digest != self.source_digest for item in evidence.values()):
            raise ValueError("manifest_evaluation_evidence_source_mismatch")
        return self


def compile_contract(contract: ContractSpec) -> tuple[str, ...]:
    """Pure validation/planning: expected IDs do not depend on passing outcomes."""
    for check in contract.checks:
        if not isinstance(check, (GuardCheck, ObligationCheck, RetainedRowCheck, RetainedRecordCheck, TerminalCountCheck, CreatedRetainedCheck, SummaryExclusionCheck, NoClarificationCheck)) and check.operator not in OPERATORS:
            raise ValueError("manifest_operator_unsupported")
    return tuple(check.check_id for check in contract.checks)


def restore_evidence(text: str) -> dict[str, RecordEvidence]:
    material = json.loads(text)
    if not isinstance(material, dict):
        raise TypeError("manifest_record_evidence_object_required")

    def nonempty(value):
        return isinstance(value, str) and bool(value)

    def fields(value):
        return (
            isinstance(value, (list, tuple))
            and all(nonempty(item) for item in value)
            and len(set(value)) == len(value)
        )

    def state(value):
        return (
            isinstance(value, str)
            and isinstance(json.loads(value), dict)
            and value == canonical_json(json.loads(value))
        )

    for key, value in material.items():
        if (
            not nonempty(key)
            or not isinstance(value, dict)
            or set(value)
            != {
                "initial_json",
                "final_json",
                "writes",
                "complete",
                "recording_complete",
                "reason",
                "source_digest",
                "selector_digest",
                "declared_fields",
            }
        ):
            raise ValueError("manifest_record_evidence_fields_mismatch")
        if type(value["complete"]) is not bool or type(value["recording_complete"]) is not bool:
            raise ValueError("manifest_record_evidence_strict_boolean_required")
        if not nonempty(value["reason"]) or not fields(value["declared_fields"]):
            raise ValueError("manifest_record_evidence_metadata_invalid")
        if any(
            not isinstance(value[name], str) or re.fullmatch(r"[0-9a-f]{64}", value[name]) is None
            for name in ("source_digest", "selector_digest")
        ):
            raise ValueError("manifest_record_evidence_digest_invalid")
        for record in (value["initial_json"], value["final_json"]):
            if record is not None and not state(record):
                raise ValueError("manifest_record_state_object_required")
        if not isinstance(value["writes"], (list, tuple)):
            raise TypeError("manifest_record_writes_sequence_required")
        if value["recording_complete"] and (
            not value["complete"]
            or value["initial_json"] is None
            or value["final_json"] is None
            or not value["writes"]
        ):
            raise ValueError("manifest_record_coverage_inputs_unavailable")
        for write in value["writes"]:
            if (
                not isinstance(write, dict)
                or set(write)
                != {
                    "occurrence",
                    "before_json",
                    "after_json",
                    "qualified",
                    "reason",
                    "requested_fields",
                }
                or type(write["qualified"]) is not bool
            ):
                raise ValueError("manifest_write_evidence_invalid")
            if not isinstance(write["occurrence"], str) or not write["occurrence"]:
                raise ValueError("manifest_write_occurrence_required")
            if not all(state(write[name]) for name in ("before_json", "after_json")):
                raise ValueError("manifest_write_state_object_required")
            if (
                not nonempty(write["reason"])
                or not fields(write["requested_fields"])
                or write["qualified"] != bool(write["requested_fields"])
            ):
                raise ValueError("manifest_write_requested_fields_invalid")
            write["requested_fields"] = tuple(write["requested_fields"])
        value["declared_fields"] = tuple(value["declared_fields"])
    return {
        key: RecordEvidence(
            **(value | {"writes": tuple(WriteFact(**item) for item in value["writes"])})
        )
        for key, value in material.items()
    }


def binding_reason(source: dict, contract: ContractSpec) -> str | None:
    """Normative bindings are explicit data; public_request remains audit text."""
    for binding in contract.bindings:
        value: Any = source
        try:
            for part in binding.path:
                if type(part) is int:
                    if not isinstance(value, (list, tuple)):
                        raise KeyError(part)
                    value = value[cast(int, part)]
                else:
                    if not isinstance(value, dict):
                        raise KeyError(part)
                    value = value[cast(str, part)]
        except (KeyError, IndexError, TypeError):
            return "manifest_source_binding_missing"
        if hashlib.sha256(canonical_json(value).encode()).hexdigest() != binding.canonical_sha256:
            return "manifest_source_binding_mismatch"
    return None


def evaluate_contract(
    source: dict,
    contract: ContractSpec,
    *,
    check_ids: tuple[str, ...] | None = None,
    evidence: dict[str, RecordEvidence] | None = None,
) -> Evaluation:
    expected_ids = compile_contract(contract)
    record_checks = tuple(check for check in contract.checks if isinstance(check, CheckSpec))
    record_ids = tuple(check.check_id for check in record_checks)
    record_sources = {key: value for key, value in contract.sources.items() if isinstance(value, RecordSource)}
    if check_ids is None:
        expected_ids = record_ids
    elif set(check_ids) - set(record_ids):
        raise ValueError("manifest_requested_check_unknown_or_duplicate")
    if check_ids is not None:
        if len(set(check_ids)) != len(check_ids) or set(check_ids) - set(expected_ids):
            raise ValueError("manifest_requested_check_unknown_or_duplicate")
        expected_ids = tuple(key for key in expected_ids if key in check_ids)
    identity = source_digest(source)
    authority_reason = binding_reason(source, contract)
    if evidence is None:
        evidence = (
            capture_records(source, record_sources)
            if authority_reason is None
            else {
                key: RecordEvidence(
                    None,
                    None,
                    (),
                    False,
                    False,
                    authority_reason,
                    identity,
                    selector_digest(selector),
                    (),
                )
                for key, selector in record_sources.items()
            }
        )
    evidence = restore_evidence(
        canonical_json({key: asdict(value) for key, value in evidence.items()})
    )
    if set(evidence) != set(record_sources):
        raise ValueError("manifest_evidence_source_inventory_mismatch")
    for key, observed in evidence.items():
        if observed.source_digest != identity or observed.selector_digest != selector_digest(
            record_sources[key]
        ):
            raise ValueError("manifest_evidence_source_or_selector_mismatch")
    results = []
    for check in record_checks:
        if check.check_id not in expected_ids:
            continue
        observed = evidence[check.source]
        selector = record_sources[check.source]
        baseline_valid = True
        if selector.baseline_requirements and check.operator == "record.fields_equal@1":
            baseline_valid = observed.initial_json is not None and (
                fields_equal(json.loads(observed.initial_json), selector.baseline_requirements)
                or fields_equal(json.loads(observed.initial_json), check.expected)
            )
        value, reason = (
            (None, authority_reason)
            if authority_reason is not None
            else OPERATORS[check.operator](check, observed)
            if baseline_valid
            else (None, "record_baseline_interpretation_unresolved")
        )
        results.append(
            CheckResult(
                check_id=check.check_id,
                signal_id=check.signal_id,
                status="valid" if value is not None else "abstained",
                value=value,
                reason=reason,
                evidence_refs=(
                    "task_evidence.initial",
                    "task_evidence.final",
                    "tool_execution_events",
                    "state_write_receipts",
                ),
            )
        )
    if tuple(item.check_id for item in results) != expected_ids:
        raise ValueError("manifest_expected_check_coverage_mismatch")
    return Evaluation(
        contract_digest=canonical_contract_digest(contract),
        source_digest=identity,
        results=tuple(results),
        evidence_json=canonical_json({key: asdict(value) for key, value in evidence.items()}),
    )
