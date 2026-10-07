"""Original-object terminal facts from raw state; no action-credit claims."""

import copy

import pytest
from test_contact_record_evidence import public, update
from test_manifest_guards import comparison, field, literal
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.gorgias.tickets import gorgias_update_ticket
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


@pytest.mark.parametrize("moved,expected,damage", [([0, 1, 2], [1, 1, 1], None),
    ([3, 4, 5], [1, 1, 1], None), ([0], [0, 1, 1], None), ([0, 1], [0, 1, 1], None),
    ([0, 1, 2], [None, None, None], "missing_assignee"),
    ([0, 1, 2], [None, None, None], "duplicate_id"),
    ([0, 1, 2], [None, None, None], "unfinished"),
    ([0, 1, 2], [1, 1, 1], "missing_ack")])
def test_terminal_count_primitive_uses_roster_including_zero_ticket_agents(monkeypatch, moved, expected, damage):
    from automationbench.tools.zapier.zoho_desk.tickets import zoho_desk_update_ticket
    from automationbench_v1.contracts.tables import TableSource
    from automationbench_v1.contracts.terminal_counts import (
        TerminalCountCheck,
        capture_terminal_count_population,
        evaluate_terminal_counts,
    )

    initial = {"google_sheets": {"rows": [
        {"spreadsheet_id": "capacity", "worksheet_id": "roster", "row_id": index + 2,
         "cells": {"Agent": agent, "Max": maximum}}
        for index, (agent, maximum) in enumerate((("a1", "3"), ("a2", "4"), ("a3", "1")))],
        "spreadsheets": [{"id": "capacity", "title": "Capacity"}],
        "worksheets": [{"id": "roster", "spreadsheet_id": "capacity", "title": "Roster"}]},
        "zoho_desk": {"tickets": [{"id": f"t{index}", "subject": "Capacity",
            "assignee_id": "a1", "department_id": "eng"} for index in range(6)]}}
    calls = []
    for index in moved:
        args = {"ticket_id": f"t{index}", "assignee_id": "a2"}
        calls.append(zapier("zoho_desk_update_ticket", args,
            lambda world, args=args: zoho_desk_update_ticket(world, **args)))
    source = run_operations(initial, calls)
    if damage == "missing_assignee":
        del source["task_evidence"]["final"]["zoho_desk"]["tickets"][0]["assignee_id"]
    elif damage == "duplicate_id":
        source["task_evidence"]["final"]["zoho_desk"]["tickets"][1]["id"] = "t0"
    elif damage == "unfinished":
        source["task_evidence"]["complete"] = False
    elif damage == "missing_ack":
        source["state_write_receipts"] = []
    roster = TableSource(path=("task_evidence", "initial", "google_sheets"),
        spreadsheet_id="capacity", worksheet_id="roster", key_fields=("Agent",), required_fields=("Max",))
    terminal = terminal_source("zoho_desk", "tickets", {"Agent": ("assignee_id",)})
    selected = TerminalCountCheck(check_id="capacity", signal_id="capacity", population="roster", source="tickets",
        counts=[{"alias": "assigned", "where": comparison("eq", field("member", "Agent"), field("request", "Agent"))}],
        required_when=comparison("eq", literal(True), literal(True)),
        counts_when=comparison("lte", {"kind": "field", "path": ["count", "assigned"], "domain": "integer"},
            {"kind": "derived", "expression": {"kind": "input", "format": "decimal_string", "path": ["request", "Max"]}}))
    result = evaluate_terminal_counts(source, selected, capture_terminal_count_population(source, roster),
        capture_record_retention(source, terminal), population_source=roster, retention_source=terminal)
    assert [finding.value for finding in result.findings] == expected
    assert result.scope_complete is all(value is not None for value in expected)
    assert all(finding.native_record_id is None for finding in result.findings)
    if damage == "unfinished":
        # This fixture finalizes the native task during scoring. The primitive
        # above separately verifies that an unfinished source must abstain.
        return
    # Exercise the same declaration through native assessment transport, not
    # just the primitive. Terminal counts must never imply causal credit.
    import asyncio

    import verifiers.v1 as vf
    from test_manifest_guard_assessments import native_fixture, penalties, terminal_records

    from automationbench_v1 import manifest_assessments
    from automationbench_v1.contracts import load_contract

    declaration = load_contract(canonical_json({"schema_version": 1,
        "manifest_id": "manufactured-roster-capacity", "revision": "1",
        "public_request": "Manufactured policy: each roster agent must stay within its declared capacity.",
        "sources": {"roster": roster.model_dump(mode="json"), "tickets": terminal.model_dump(mode="json")},
        "checks": [selected.model_dump(mode="json")]}))
    assert load_contract(declaration.model_dump_json()) == declaration
    monkeypatch.setattr(manifest_assessments, "load_task_contract", lambda _: declaration)
    task, episode, trace = native_fixture(source)
    scalar = copy.deepcopy(trace.rewards)
    asyncio.run(task.score(trace))
    assert not trace.assessment_errors and not trace.credit_errors
    values = [item.value for item in terminal_records(trace) if item.signal.signal_id == "capacity"]
    assert sorted(values, key=lambda value: -1 if value is None else value) == sorted(
        expected, key=lambda value: -1 if value is None else value)
    assert not penalties(trace) and trace.rewards == scalar
    loaded = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    replay = loaded.traces[0]
    replay.state = trace.state
    asyncio.run(task.score(replay))
    assert not replay.assessment_errors and not replay.credit_errors
    original = [(item.signal.signal_id, item.status, item.value) for item in terminal_records(trace)]
    assert [(item.signal.signal_id, item.status, item.value) for item in terminal_records(replay)][-len(original):] == original
    rejected = declaration.model_dump(mode="json")
    rejected["credit"] = [{"check": "capacity", "policy": "records_retained_completion_once@1",
        "channel": "capacity", "effects": "tickets", "goal_fields": ["Agent"], "completion_selection": "earliest"}]
    with pytest.raises(ValueError, match="credit_policy_check_capability_mismatch"):
        load_contract(canonical_json(rejected))


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


def grouped_source(*closed):
    world = {"gorgias": {"tickets": [
        {"id": "a", "subject": "A", "status": "open", "customer": {"id": "ca", "email": "same@example.com"}},
        {"id": "b", "subject": "B", "status": "open", "customer": {"id": "cb", "email": "same@example.com"}},
        {"id": "hold", "subject": "Held", "status": "open", "customer": {"id": "ch", "email": "same@example.com"}},
        {"id": "decoy", "subject": "Different email", "status": "open", "customer": {"id": "cd", "email": "other@example.com"}},
    ]}}
    calls = [zapier("gorgias_update_ticket", {"ticket_id": identity, "status": "closed"},
        lambda world, identity=identity: gorgias_update_ticket(world, ticket_id=identity, status="closed")) for identity in closed]
    return run_operations(world, calls)


def grouped_check(**changes):
    membership = {"op": "all", "args": [
        comparison("eq", field("member", "Email"), field("request", "Email")),
        comparison("eq", field("member", "Status"), literal("open")),
        comparison("ne", field("member", "ID"), literal("hold")),
    ]}
    return check(required_when={"op": "in", "left": field("request", "ID"), "right": literal(["a", "b"])},
        counts=[{"alias": "open_siblings", "where": membership}],
        retained_when=comparison("eq", field("count", "open_siblings", domain="integer"), literal(1)), **changes)


def grouped_evaluate(source, selected=None):
    fields = {"ID": ("id",), "Email": ("customer", "email"), "Status": ("status",)}
    return evaluate(source, selected or grouped_check(), population_spec=initial_source("gorgias", "tickets", fields),
                    final_spec=terminal_source("gorgias", "tickets", fields))


@pytest.mark.parametrize("closed,expected", [(("a",), 1), (("b",), 1), ((), 0), (("a", "b"), 0)])
def test_terminal_count_accepts_any_valid_survivor_with_real_handlers(closed, expected):
    source = grouped_source(*closed)
    result = grouped_evaluate(source)
    goals = [finding for finding in result.findings if finding.native_record_id in {"a", "b"}]
    assert len(goals) == 2 and all(item.value == expected for item in goals)
    assert result.scope_complete
    # Held same-email and different-email tickets are not silently chosen/closed.
    assert all(ticket["status"] == "open" for ticket in source["task_evidence"]["final"]["gorgias"]["tickets"]
               if ticket["id"] in {"hold", "decoy"})


@pytest.mark.parametrize("gap", ["duplicate", "missing-id", "missing-status", "nonfinal", "malformed-status", "budget"])
def test_terminal_count_unknown_inventory_or_membership_never_becomes_zero(gap):
    source = grouped_source("b")
    tickets = source["task_evidence"]["final"]["gorgias"]["tickets"]
    if gap == "duplicate":
        tickets.append(copy.deepcopy(tickets[0]))
    elif gap == "missing-id":
        tickets.append({"status": "closed"})
    elif gap == "missing-status":
        del tickets[0]["status"]
    elif gap == "malformed-status":
        tickets[0]["status"] = 1
    elif gap == "nonfinal":
        source["task_evidence"]["complete"] = False
    else:
        tickets.extend({**copy.deepcopy(tickets[-1]), "id": f"extra-{index}"} for index in range(16400))
    result = grouped_evaluate(source)
    assert all(item.status == "abstained" and item.value is None for item in result.findings if item.required)


@pytest.mark.parametrize("change", ["undeclared-alias", "member-in-goal", "count-in-required", "retained-in-count", "undeclared-member"])
def test_terminal_count_context_and_projected_fields_are_admitted(change):
    if change == "undeclared-alias":
        args = {"retained_when": comparison("eq", field("count", "missing"), literal(1))}
    elif change == "member-in-goal":
        args = {"retained_when": comparison("eq", field("member", "Status"), literal("open"))}
    elif change == "count-in-required":
        args = {"required_when": comparison("eq", field("count", "open_siblings"), literal(1))}
    else:
        root = "retained" if change == "retained-in-count" else "member"
        args = {"counts": [{"alias": "open_siblings", "where": comparison("eq", field(root, "Undeclared"), literal("open"))}]}
    declaration = grouped_check().model_dump(mode="python")
    declaration.update(args)
    with pytest.raises(ValueError):
        grouped_evaluate(grouped_source("b"), RetainedRecordCheck.model_validate(declaration))


def test_terminal_counts_compile_and_roundtrip_through_generic_contract_engine():
    from automationbench_v1.contracts import load_contract

    fields = {"ID": ("id",), "Email": ("customer", "email"), "Status": ("status",)}
    declaration = {"schema_version": 1, "manifest_id": "manufactured-terminal-count", "revision": "1",
        "public_request": "Manufactured policy: one eligible open ticket per exact email; preserve the held ticket.",
        "sources": {"contacts": initial_source("gorgias", "tickets", fields).model_dump(mode="json"),
                    "terminal": terminal_source("gorgias", "tickets", fields).model_dump(mode="json")},
        "checks": [grouped_check().model_dump(mode="json")]}
    manifest = load_contract(canonical_json(declaration))
    restored = load_contract(manifest.model_dump_json())
    for closed, expected in (("a", 1), ("b", 1), (None, 0)):
        evaluation = grouped_evaluate(grouped_source(*(() if closed is None else (closed,))), restored.checks[0])
        finding_values = [item.value for item in evaluation.findings if item.required]
        assert finding_values == [expected, expected]


def test_terminal_counts_do_not_inherit_local_record_completion_credit():
    from test_manifest_record_retained_credit import contract

    from automationbench_v1.contracts import load_contract

    declaration = contract().model_dump(mode="json")
    declaration["checks"][0]["counts"] = [{"alias": "solved", "where": comparison(
        "eq", field("member", "status"), literal("solved"))}]
    with pytest.raises(ValueError, match="record_terminal_counts_are_outcome_only"):
        load_contract(canonical_json(declaration))
