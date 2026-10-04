"""Original-object terminal facts from raw state; no action-credit claims."""

import copy

import pytest
from test_contact_record_evidence import public, update
from test_manifest_guards import comparison, field, literal
from test_notification_evidence import run_operations

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.populations import InitialCollectionSource, capture_population
from automationbench_v1.contracts.retained_records import (
    RecordRetentionEvidence,
    RetainedRecordCheck,
    RetainedRecordSource,
    capture_record_retention,
    evaluate_retained_records,
    validate_record_retention,
)


def initial_source(service="salesforce", collection="contacts", fields=None):
    return InitialCollectionSource(path=("task_evidence", "initial", service, collection),
        fields=fields or {"ID": ("id",), "Email": ("email",)}, key_fields=("ID",))


def terminal_source(service="salesforce", collection="contacts", fields=None):
    return RetainedRecordSource(path=("task_evidence", "final", service, collection),
        fields=fields or {"Assistant": ("assistant_name",), "Email": ("assistant_email",)})


def check(**changes):
    return RetainedRecordCheck.model_validate({"check_id": "original-contact", "signal_id": "contact.retained", "role": "goal",
        "population": "contacts", "source": "terminal", "required_when": comparison("eq", field("request", "ID"), literal("contact-1")),
        "retained_when": comparison("eq", field("retained", "Assistant"), literal("New Assistant")), **changes})


def evaluate(source, selected=None, *, population_spec=None, final_spec=None, population=None, retention=None):
    population_spec, final_spec = population_spec or initial_source(), final_spec or terminal_source()
    return evaluate_retained_records(source, selected or check(), {"contacts": population or capture_population(source, population_spec)},
        retention or capture_record_retention(source, final_spec), population_sources={"contacts": population_spec}, retention_source=final_spec)


@pytest.mark.parametrize("calls,value", [([update()], 1), ([], 0),
    ([update(), update({"assistant_name": "Broken"})], 0),
    ([update(), update({"assistant_name": "Broken"}), update()], 1)])
def test_real_handlers_prove_final_original_record_without_best_action_or_credit(calls, value):
    source = run_operations(public(), calls)
    result = evaluate(source)
    assert result.findings[0].value == value and result.scope_complete
    assert result.findings[0].native_record_id == "contact-1"
    assert not hasattr(result.findings[0], "selection")


def test_missing_ack_and_unrelated_action_gaps_do_not_erase_known_final_state():
    source = run_operations(public(), [update()])
    source["state_write_receipts"] = []
    assert evaluate(source).findings[0].value == 1


@pytest.mark.parametrize("predicate", ["required_when", "supported_when"])
def test_schema_invalid_initial_used_field_cannot_freeze_numeric_eligibility(predicate):
    source = run_operations(public(), [update()])
    source["task_evidence"]["initial"]["salesforce"]["contacts"][0]["assistant_name"] = 1
    spec = initial_source(fields={"ID": ("id",), "Policy": ("assistant_name",)})
    selected = check(**{predicate: comparison("eq", field("request", "Policy"), literal(1))})
    receipt = capture_population(source, spec)
    before = receipt.model_dump_json()
    result = evaluate(source, selected, population_spec=spec, population=receipt)
    assert result.findings[0].status == "abstained" and result.findings[0].value is None
    assert result.findings[0].required is (None if predicate == "required_when" else True)
    assert receipt.model_dump_json() == before


def test_schema_invalid_unused_initial_field_preserves_independent_requirement():
    source = run_operations(public(), [update()])
    source["task_evidence"]["initial"]["salesforce"]["contacts"][0]["assistant_name"] = 1
    spec = initial_source(fields={"ID": ("id",), "Unused": ("assistant_name",)})
    assert evaluate(source, population_spec=spec).findings[0].value == 1


@pytest.mark.parametrize("bad", [1, True])
def test_schema_invalid_lookup_read_is_unknown_not_numeric_permission(bad):
    source = run_operations(public(), [update()])
    source["task_evidence"]["initial"]["salesforce"]["contacts"][0]["assistant_name"] = bad
    spec = initial_source(fields={"ID": ("id",), "Policy": ("assistant_name",)})
    selected = check(lookups=[{"source": "directory", "alias": "person", "keys": {"ID": field("request", "ID")}}],
        required_when=comparison("eq", field("person", "Policy"), literal(bad)))
    result = evaluate_retained_records(source, selected,
        {"contacts": capture_population(source, spec), "directory": capture_population(source, spec)},
        capture_record_retention(source, terminal_source()),
        population_sources={"contacts": spec, "directory": spec}, retention_source=terminal_source())
    assert result.findings[0].status == "abstained" and result.findings[0].required is None


@pytest.mark.parametrize("gap", ["missing", "invalid-key"])
def test_lookup_missing_collection_and_invalid_native_key_remain_unavailable(gap):
    source = run_operations(public(), [update()])
    main = initial_source()
    directory = initial_source("zendesk", "tickets", {"ID": ("id",), "Status": ("status",)})
    source["task_evidence"]["initial"]["zendesk"] = {} if gap == "missing" else {
        "tickets": [{"id": 1, "status": "solved"}]}
    selected = check(lookups=[{"source": "directory", "alias": "ticket", "keys": {"ID": field("request", "ID")}}],
        required_when=comparison("eq", field("ticket", "Status"), literal("solved")))
    result = evaluate_retained_records(source, selected,
        {"contacts": capture_population(source, main), "directory": capture_population(source, directory)},
        capture_record_retention(source, terminal_source()),
        population_sources={"contacts": main, "directory": directory}, retention_source=terminal_source())
    assert result.findings[0].status == "abstained" and result.findings[0].required is None


@pytest.mark.parametrize("bad", [True, 1.0, "1"])
def test_initial_literal_native_type_invalidity_is_unknown(bad):
    initial = initial_source("freshdesk", "tickets", {"ID": ("id",), "Priority": ("priority",)})
    final = terminal_source("freshdesk", "tickets", {"Status": ("status",)})
    source = {"task_evidence": {"initial": {"freshdesk": {"tickets": [{"id": "contact-1", "priority": bad}]}},
        "final": {"freshdesk": {"tickets": [{"id": "contact-1", "status": 2}]}}, "complete": True}}
    selected = check(required_when=comparison("eq", field("request", "Priority", domain="number"), literal(1)),
        retained_when=comparison("eq", field("retained", "Status", domain="number"), literal(2)))
    assert evaluate(source, selected, population_spec=initial, final_spec=final).findings[0].required is None


@pytest.mark.parametrize("change", ["delete", "same-key-new-id", "same-id-move"])
def test_original_native_id_cannot_be_replaced_by_matching_business_key(change):
    source = run_operations(public(), [update()])
    contacts = source["task_evidence"]["final"]["salesforce"]["contacts"]
    if change == "delete":
        contacts.clear()
    elif change == "same-key-new-id":
        contacts[0]["id"] = "replacement"
    else:
        contacts.insert(0, {"id": "other", "email": "other@example.com"})
    assert evaluate(source).findings[0].value == (1 if change == "same-id-move" else 0)


def test_unrelated_unknown_and_duplicate_ids_preserve_specific_positive_and_known_false():
    for expected, calls in ((1, [update()]), (0, [])):
        source = run_operations(public(), calls)
        source["task_evidence"]["final"]["salesforce"]["contacts"] += [{"email": "missing-ID"}, {"id": "other"}, {"id": "other"}]
        result = evaluate(source)
        assert result.findings[0].value == expected and not result.scope_complete


def test_duplicate_original_id_abstains_but_does_not_erase_other_original_goal():
    world = public()
    world["salesforce"]["contacts"].append({"id": "contact-2", "last_name": "Other", "email": "other@example.com", "assistant_name": "New Assistant"})
    source = run_operations(world, [update()])
    source["task_evidence"]["final"]["salesforce"]["contacts"].append(copy.deepcopy(source["task_evidence"]["final"]["salesforce"]["contacts"][0]))
    selected = check(required_when=comparison("eq", literal(True), literal(True)))
    result = evaluate(source, selected)
    assert [(item.native_record_id, item.status, item.value) for item in result.findings] == [
        ("contact-1", "abstained", None), ("contact-2", "valid", 1)]


@pytest.mark.parametrize("gap", ["missing", "null", "unknown-id"])
def test_absence_zero_requires_complete_terminal_identity_inventory(gap):
    source = run_operations(public(), [])
    service = source["task_evidence"]["final"]["salesforce"]
    if gap == "missing":
        del service["contacts"]
    elif gap == "null":
        service["contacts"] = None
    else:
        service["contacts"] = [{"email": "original@example.com"}]
    result = evaluate(source)
    assert result.findings[0].status == "abstained" and result.findings[0].value is None


@pytest.mark.parametrize("complete", [False, None, 1, "true"])
def test_finalization_is_exact_true_independent_of_population_closure(complete):
    source = run_operations(public(), [update()])
    source["task_evidence"]["complete"] = complete
    assert evaluate(source).findings[0].reason == "retained_record_finalization_unavailable"


def test_initial_missing_id_never_hydrates_generated_object_or_goal():
    source = run_operations(public(), [update()])
    del source["task_evidence"]["initial"]["salesforce"]["contacts"][0]["id"]
    result = evaluate(source)
    assert not result.findings and not result.scope_complete


@pytest.mark.parametrize("value", [1, True, [], None])
def test_native_string_field_malformed_value_never_blessed_by_numeric_or_other_predicate(value):
    source = run_operations(public(), [])
    source["task_evidence"]["final"]["salesforce"]["contacts"][0]["assistant_name"] = value
    selected = check(retained_when=comparison("eq", field("retained", "Assistant", domain="number"), literal(1)))
    assert evaluate(source, selected).findings[0].status == "abstained"


@pytest.mark.parametrize("value,known", [(1, True), (True, False), (1.0, False), ("1", False)])
def test_installed_numeric_literal_requires_exact_type(value, known):
    fields = {"ID": ("id",), "Priority": ("priority",)}
    initial = initial_source("freshdesk", "tickets", fields)
    final = terminal_source("freshdesk", "tickets", {"Priority": ("priority",)})
    source = {"task_evidence": {"initial": {"freshdesk": {"tickets": [{"id": "contact-1", "priority": 1}]}},
        "final": {"freshdesk": {"tickets": [{"id": "contact-1", "priority": value}]}}, "complete": True}}
    selected = check(retained_when=comparison("eq", field("retained", "Priority", domain="integer"), literal(1)))
    result = evaluate(source, selected, population_spec=initial, final_spec=final)
    assert (result.findings[0].value == 1) is known
    if not known:
        assert result.findings[0].status == "abstained"


@pytest.mark.parametrize("value,known", [(1, True), (10 ** 308, True), (10 ** 400, False), (True, False), ("1", False)])
def test_native_float_allows_finite_integer_without_infinite_normalization(value, known):
    initial = initial_source("salesforce", "opportunities", {"ID": ("id",)})
    final = terminal_source("salesforce", "opportunities", {"Amount": ("amount",)})
    source = {"task_evidence": {"initial": {"salesforce": {"opportunities": [{"id": "contact-1"}]}},
        "final": {"salesforce": {"opportunities": [{"id": "contact-1", "amount": value}]}}, "complete": True}}
    selected = check(retained_when=comparison("eq", field("retained", "Amount", domain="number"), literal(value if known else 1)))
    result = evaluate(source, selected, population_spec=initial, final_spec=final)
    assert (result.findings[0].value == 1) is known


def test_missing_bad_declared_field_does_not_erase_independent_true_branch():
    source = run_operations(public(), [update()])
    source["task_evidence"]["final"]["salesforce"]["contacts"][0]["assistant_email"] = 1
    assert evaluate(source).findings[0].value == 1
    selected = check(retained_when={"op": "all", "args": [check().retained_when.model_dump(mode="json"),
        comparison("eq", field("retained", "Email"), literal("new@example.com"))]})
    assert evaluate(source, selected).findings[0].status == "abstained"


def test_inapplicable_and_unsupported_do_not_fake_terminal_goal():
    source = run_operations(public(), [update()])
    selected = check(supported_when=comparison("eq", literal(True), literal(False)))
    assert evaluate(source, selected).findings[0].status == "abstained"
    selected = check(required_when=comparison("eq", literal(True), literal(False)))
    source["task_evidence"]["complete"] = False
    assert evaluate(source, selected).findings[0].status == "inapplicable"


def test_terminal_source_rejects_initial_alias_unknown_schema_and_undeclared_read():
    for changes in ({"path": ("task_evidence", "initial", "salesforce", "contacts")},
                    {"fields": {"Email": ("AssistantEmail",)}}, {"path": ("task_evidence", "final", "jira", "issues")}):
        with pytest.raises(ValueError):
            RetainedRecordSource.model_validate({**terminal_source().model_dump(mode="python"), **changes})
    source = run_operations(public(), [])
    with pytest.raises(ValueError, match="projection_undeclared"):
        evaluate(source, check(retained_when=comparison("eq", field("retained", "Undeclared"), literal("value"))))
    with pytest.raises(ValueError, match="context_unknown"):
        check(required_when=comparison("eq", field("retained", "Assistant"), literal("New Assistant")))


@pytest.mark.parametrize("target", ["source", "receipt", "identity", "closed"])
def test_raw_projection_reload_and_copied_metadata_forgery_are_rejected(target):
    source = run_operations(public(), [update()])
    final = terminal_source()
    evidence = capture_record_retention(source, final)
    restored = RecordRetentionEvidence.model_validate_json(evidence.model_dump_json())
    validate_record_retention(restored, source, final)
    if target == "source":
        source["task_evidence"]["final"]["salesforce"]["contacts"][0]["assistant_name"] = "Foreign"
    elif target == "receipt":
        evidence = evidence.model_copy(update={"rows": (evidence.rows[0].model_copy(update={"cells_json": canonical_json({"Assistant": "Foreign"})}),)})
    elif target == "identity":
        evidence = evidence.model_copy(update={"rows": (evidence.rows[0].model_copy(update={"native_record_id": "foreign"}),)})
    else:
        evidence = evidence.model_copy(update={"closed": 1})
    with pytest.raises(ValueError):
        validate_record_retention(evidence, source, final)


def test_empty_initial_inventory_and_budget_are_truthful_not_named_task_claims():
    source = run_operations(public(), [])
    source["task_evidence"]["initial"]["salesforce"]["contacts"] = []
    assert not evaluate(source).findings
    source = run_operations(public(), [])
    source["task_evidence"]["initial"]["salesforce"]["contacts"].append({"id": "other", "email": "other@example.com"})
    result = evaluate(source, check(max_instances=1))
    assert not result.findings and not result.scope_complete
