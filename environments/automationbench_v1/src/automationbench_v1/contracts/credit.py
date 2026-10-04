"""Domain credit policies consume retained evidence, separately from outcomes."""

import json
from dataclasses import dataclass

from .engine import Evaluation
from .evidence import selector_digest
from .loader import canonical_contract_digest
from .models import CheckSpec, RecordSource
from .operators import field_equal, fields_equal


@dataclass(frozen=True)
class CreditSelection:
    check_ids: tuple[str, ...]
    channel: str
    occurrence: str
    value: float
    policy: str

    @property
    def check_id(self):
        return self.check_ids[0]


def select_credit(contract, evaluation: Evaluation) -> tuple[CreditSelection, ...]:
    if evaluation.contract_digest != canonical_contract_digest(contract):
        raise ValueError("manifest_credit_contract_mismatch")
    checks = {item.check_id: item for item in contract.checks if isinstance(item, CheckSpec)}
    if {item.check_id for item in evaluation.results} - set(checks):
        raise ValueError("manifest_credit_check_unknown")
    observed = json.loads(evaluation.evidence_json)
    record_sources = {key: value for key, value in contract.sources.items() if isinstance(value, RecordSource)}
    if set(observed) != set(record_sources):
        raise ValueError("manifest_credit_source_inventory_mismatch")
    for key, selector in record_sources.items():
        if observed[key]["selector_digest"] != selector_digest(selector):
            raise ValueError("manifest_credit_selector_mismatch")
    results = {item.check_id: item for item in evaluation.results}
    for result in evaluation.results:
        if result.signal_id != checks[result.check_id].signal_id:
            raise ValueError("manifest_credit_signal_mismatch")
    def witness(check_id):
        if check_id not in results:
            return None
        result, check = results[check_id], checks[check_id]
        if result.status != "valid" or result.value != 1:
            return None
        evidence = observed[check.source]
        if not evidence["recording_complete"] or evidence["initial_json"] is None:
            return None
        if not {field.field for field in check.expected}.issubset(evidence.get("declared_fields", ())):
            return None
        initial = json.loads(evidence["initial_json"])
        if fields_equal(initial, check.expected):
            return None
        seen_completion, damaged, recipient = False, False, None
        for write in evidence["writes"]:
            before, after = json.loads(write["before_json"]), json.loads(write["after_json"])
            before_correct, after_correct = fields_equal(before, check.expected), fields_equal(after, check.expected)
            if before_correct:
                seen_completion = True
            if seen_completion and not after_correct:
                damaged = True
            if after_correct:
                seen_completion = True
            changed = {field.field for field in check.expected if not field_equal(before.get(field.field), field)}
            requested = set(write.get("requested_fields", ()))
            if (not before_correct and after_correct and write["qualified"]
                and changed.issubset(requested) and recipient is None):
                recipient = write["occurrence"]
        return recipient if not damaged else None

    selected = []
    for policy in contract.credit:
        if policy.policy in {"per_effect_negative@1", "required_effect_once@1", "retained_completion_once@1", "created_retained_completion_once@1", "summary_action_negative_once@1"}:
            continue
        check_ids = (policy.check,) if policy.check is not None else policy.checks
        recipients = [witness(check_id) for check_id in check_ids]
        if recipients and recipients[0] is not None and len(set(recipients)) == 1:
            selected.append(CreditSelection(check_ids, policy.channel, recipients[0], 1.0, policy.policy))
    keys = [(item.occurrence, item.channel) for item in selected]
    if len(keys) != len(set(keys)):
        # V1 requires explicit aggregation rather than accidental double reward.
        raise ValueError("manifest_credit_aggregation_required")
    return tuple(selected)
