"""Calculation admission is initial authority, distinct from applicability."""

import copy

import pytest
from test_manifest_retained import check, evaluate
from test_manifest_sheet_effects import initial, update
from test_notification_evidence import run_operations
from test_retained_completion import evaluate as completion

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.predicates import Comparison, FieldValue, parse_predicate
from automationbench_v1.contracts.retained import RetainedRowCheck, _digest


def equal(path, value):
    return {"op": "eq", "left": {"kind": "field", "path": path, "domain": "string"},
            "right": {"kind": "literal", "value": value}}


def supported(value):
    return {"op": "eq", "left": {"kind": "literal", "value": value},
            "right": {"kind": "literal", "value": True}}


def test_absent_support_preserves_legacy_serialization_and_check_identity():
    original = check()
    explicit = check(supported_when=None)
    old_keys = {"check_id", "signal_id", "role", "operator", "population", "source", "lookups",
                "required_when", "retained_when", "max_instances"}
    for mode in ("python", "json"):
        assert set(original.model_dump(mode=mode)) == old_keys
        assert explicit.model_dump(mode=mode) == original.model_dump(mode=mode)
    assert _digest(original.model_dump(mode="json")) == _digest(explicit.model_dump(mode="json"))
    assert "supported_when" not in canonical_json(original.model_dump(mode="json"))


@pytest.mark.parametrize("amount,expected", [("$20", 1), ("$30", 0)])
def test_known_supported_initial_domain_keeps_normal_terminal_outcomes(amount, expected):
    selected = check(supported_when=equal(["request", "Amount"], "$10"))
    outcome = evaluate(run_operations(initial(), [update(cells={"Amount": amount})]), selected)
    assert outcome.findings[0].status == "valid" and outcome.findings[0].value == expected
    assert outcome.scope_complete
    assert ("request", "Amount") in outcome.findings[0].evidence_paths


@pytest.mark.parametrize("predicate,reason", [
    (supported(False), "retained_calculation_domain_unsupported"),
    (equal(["request", "Missing"], "value"), "retained_calculation_domain_unavailable"),
])
def test_unsupported_or_unknown_is_required_unavailable_not_failed_or_skipped(predicate, reason):
    selected = check(supported_when=predicate)
    data = run_operations(initial(), [update()])
    outcome = evaluate(data, selected)
    finding = outcome.findings[0]
    assert finding.status == "abstained" and finding.value is None and finding.required is True
    assert finding.reason == reason and not outcome.scope_complete
    credit = completion(data, selected)
    assert credit.outcome == outcome
    assert credit.findings[0].status == "unavailable" and credit.findings[0].selection is None


@pytest.mark.parametrize("requirement,status,required,reason", [
    (supported(False), "inapplicable", False, "retained_not_required"),
    (equal(["request", "Missing"], "value"), "abstained", None, "retained_requirement_unavailable"),
])
def test_requirement_precedes_support(requirement, status, required, reason):
    selected = check(required_when=requirement, supported_when=equal(["request", "Other Missing"], "value"))
    outcome = evaluate(run_operations(initial(), [update()]), selected)
    finding = outcome.findings[0]
    assert (finding.status, finding.required, finding.reason) == (status, required, reason)
    assert ("request", "Other Missing") not in finding.evidence_paths


@pytest.mark.parametrize("root", ["retained", "effect", "unknown"])
@pytest.mark.parametrize("derived", [False, True])
def test_support_cannot_use_final_effect_or_undeclared_context_even_in_derived_values(root, derived):
    predicate = equal([root, "Amount"], "$10")
    if derived:
        predicate = {"op": "eq", "left": {"kind": "derived", "expression": {
            "kind": "input", "format": "usd_string", "path": [root, "Amount"]}},
            "right": {"kind": "derived", "expression": {"kind": "input", "format": "usd_string", "literal": "$10"}}}
    with pytest.raises(ValueError, match="predicate_context_unknown"):
        check(supported_when=predicate)


def test_copied_check_cannot_bypass_support_context_revalidation():
    copied = check().model_copy(update={"supported_when": parse_predicate(equal(["retained", "Amount"], "$20"))})
    with pytest.raises(ValueError, match="predicate_context_unknown"):
        evaluate(run_operations(initial(), [update()]), copied)


def test_copied_malformed_predicate_cannot_bypass_strict_re_admission():
    predicate = parse_predicate(equal(["request", "Amount"], "$10"))
    assert isinstance(predicate, Comparison) and isinstance(predicate.left, FieldValue)
    malformed = predicate.model_copy(update={"left": predicate.left.model_copy(update={"path": ("request", True)})})
    copied = check().model_copy(update={"supported_when": malformed})
    with pytest.raises(ValueError):
        evaluate(run_operations(initial(), [update()]), copied)


def test_unsupported_members_keep_inventory_and_do_not_erase_independent_known_goal():
    public = initial()
    second = copy.deepcopy(public["google_sheets"]["rows"][0])
    second.update(id="second-native-id", row_id=3)
    second["cells"].update(Name="Other", Amount="$20")
    public["google_sheets"]["rows"].append(second)
    data = run_operations(public, [update()])
    old = evaluate(data)
    outcome = evaluate(data, check(supported_when=equal(["request", "Name"], "Item")))
    assert len(outcome.findings) == len(old.findings) == 2
    assert [finding.instance_key for finding in outcome.findings] == [finding.instance_key for finding in old.findings]
    assert outcome.findings[0].value == 1 and outcome.findings[0].status == "valid"
    assert outcome.findings[1].status == "abstained" and outcome.findings[1].required is True
    assert not outcome.scope_complete


def test_live_source_repair_cannot_rewrite_initial_supported_domain():
    selected = check(supported_when=equal(["request", "Amount"], "$30"))
    data = run_operations(initial(), [update(cells={"Amount": "$30"}), update()])
    finding = evaluate(data, selected).findings[0]
    assert finding.status == "abstained" and finding.reason == "retained_calculation_domain_unsupported"
    assert completion(data, selected).findings[0].selection is None


def test_explicit_true_support_roundtrips_and_changes_policy_digest():
    baseline = check()
    selected = check(supported_when=supported(True))
    restored = RetainedRowCheck.model_validate_json(selected.model_dump_json())
    assert restored == selected
    assert _digest(selected.model_dump(mode="json")) != _digest(baseline.model_dump(mode="json"))
