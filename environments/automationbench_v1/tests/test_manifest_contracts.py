"""Manifest admission and migration parity, independent of outcome evaluation."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from automationbench_v1.contracts import (
    CheckSpec,
    RecordSource,
    canonical_contract_digest,
    load_contract,
    load_task_contract,
    loader,
)
from automationbench_v1.simple_record_contracts import CONTRACTS


def declaration():
    return {
        "schema_version": 1,
        "manifest_id": "record-update",
        "revision": "1",
        "public_request": "Human-readable audit context, not prompt admission.",
        "sources": {
            "target": {
                "adapter": "salesforce.record@1",
                "object_type": "Opportunity",
                "record_id": "006002",
            }
        },
        "checks": [
            {
                "check_id": "stage",
                "signal_id": "record.stage",
                "role": "goal",
                "operator": "record.fields_equal@1",
                "source": "target",
                "expected": [
                    {"field": "stage_name", "value": "Proposal/Price Quote", "comparison": "string"}
                ],
            }
        ],
        "credit": [{"check": "stage", "policy": "verified_transition_once@1", "channel": "goal"}],
    }


def admitted(data):
    return load_contract(json.dumps(data))


def gmail_read_declaration():
    return {
        "schema_version": 1, "manifest_id": "message-read-fixture", "revision": "1",
        "public_request": "Find the original introduction email.",
        "sources": {
            "initial": {"adapter": "initial.records@1", "path": ["task_evidence", "initial", "gmail", "messages"],
                        "fields": {"id": ["id"], "body": ["body_plain"]}, "key_fields": ["id"]},
            "reads": {"adapter": "gmail.message_reads@1", "kind": "read_message"},
        },
        "checks": [{"check_id": "found", "signal_id": "message.found", "role": "goal",
                    "operator": "effects.required_when@1", "semantics": "new_occurrence",
                    "population": "initial", "source": "reads",
                    "required_when": {"op": "eq", "left": {"kind": "field", "path": ["request", "id"], "domain": "string"},
                                      "right": {"kind": "literal", "value": "original"}},
                    "effect_match": {"op": "eq", "left": {"kind": "field", "path": ["effect", "body_plain"], "domain": "string"},
                                     "right": {"kind": "field", "path": ["request", "body"], "domain": "string"}}}],
        "credit": [{"check": "found", "policy": "required_effect_once@1", "channel": "retrieval"}],
    }


def test_gmail_read_manifest_compiles_and_round_trips():
    from automationbench_v1.contracts import GmailObservationSource
    from automationbench_v1.contracts.engine import compile_contract

    contract = admitted(gmail_read_declaration())
    assert isinstance(contract.sources["reads"], GmailObservationSource)
    assert compile_contract(contract) == ("found",)
    assert admitted(contract.model_dump(mode="json")) == contract


@pytest.mark.parametrize("kind", ["send", "full_message_return", "get", ""])
def test_gmail_read_selector_rejects_unimplemented_kind(kind):
    data = gmail_read_declaration()
    data["sources"]["reads"]["kind"] = kind
    with pytest.raises(ValueError):
        admitted(data)


def test_gmail_read_source_cannot_supply_sheet_retention():
    data = gmail_read_declaration()
    data["checks"][0] = {
        "check_id": "found", "signal_id": "message.found", "role": "goal",
        "operator": "sheets.retained_when@1", "population": "initial", "source": "reads",
        "required_when": data["checks"][0]["required_when"],
        "retained_when": data["checks"][0]["required_when"],
    }
    data["credit"] = []
    with pytest.raises(ValueError):
        admitted(data)


def retained_record_declaration():
    return {
        "schema_version": 1, "manifest_id": "retained-ticket-fixture", "revision": "1",
        "public_request": "Resolve the original ticket.",
        "sources": {
            "initial": {"adapter": "initial.records@1", "path": ["task_evidence", "initial", "zendesk", "tickets"],
                        "fields": {"id": ["id"]}, "key_fields": ["id"]},
            "final": {"adapter": "final.records@1", "path": ["task_evidence", "final", "zendesk", "tickets"],
                      "fields": {"status": ["status"]}},
        },
        "checks": [{"check_id": "resolved", "signal_id": "ticket.resolved", "role": "goal",
                    "operator": "records.retained_when@1", "population": "initial", "source": "final",
                    "required_when": {"op": "eq", "left": {"kind": "field", "path": ["request", "id"], "domain": "string"},
                                      "right": {"kind": "literal", "value": "ZD-501"}},
                    "retained_when": {"op": "eq", "left": {"kind": "field", "path": ["retained", "status"], "domain": "string"},
                                      "right": {"kind": "literal", "value": "solved"}}}],
        "credit": [],
    }


def test_retained_record_manifest_compiles_and_round_trips():
    from automationbench_v1.contracts.engine import compile_contract

    contract = admitted(retained_record_declaration())
    assert compile_contract(contract) == ("resolved",)
    assert admitted(contract.model_dump(mode="json")) == contract


@pytest.mark.parametrize("root", ["request", "retained"])
def test_retained_record_rejects_undeclared_predicate_projection(root):
    declaration = retained_record_declaration()
    predicate = "required_when" if root == "request" else "retained_when"
    declaration["checks"][0][predicate]["left"]["path"][1] = "invented"
    with pytest.raises(ValueError, match="predicate_projection_undeclared"):
        admitted(declaration)


def test_retained_record_rejects_cross_collection():
    declaration = retained_record_declaration()
    declaration["sources"]["final"]["path"][-1] = "users"
    declaration["sources"]["final"]["fields"] = {"name": ["name"]}
    with pytest.raises(ValueError, match="population_scope_mismatch"):
        admitted(declaration)


def test_retained_record_rejects_scalar_tail_and_unknown_candidate_metadata():
    declaration = retained_record_declaration()
    declaration["checks"][0]["retained_when"]["left"]["path"].append("invented")
    with pytest.raises(ValueError, match="population_field_path_unsupported"):
        admitted(declaration)
    declaration = retained_record_declaration()
    declaration["checks"][0]["required_when"]["left"]["path"] = ["candidate", "status"]
    with pytest.raises(ValueError, match="candidate_metadata_unknown"):
        admitted(declaration)


def test_retained_record_rejects_unqualified_credit():
    declaration = retained_record_declaration()
    declaration["credit"] = [{"check": "resolved", "policy": "retained_completion_once@1", "channel": "goal", "goal_fields": ["status"]}]
    with pytest.raises(ValueError, match="credit_policy_check_capability_mismatch"):
        admitted(declaration)


def credited_retained_record_declaration():
    data = retained_record_declaration()
    data["sources"]["initial"]["fields"]["status"] = ["status"]
    data["sources"]["writes"] = {"adapter": "zendesk.ticket_updates@1", "kind": "status_update"}
    data["credit"] = [{"check": "resolved", "policy": "records_retained_completion_once@1", "channel": "goal",
                       "effects": "writes", "goal_fields": ["status"], "completion_selection": "earliest"}]
    return data


def test_record_completion_manifest_round_trips_without_changing_sheets_policy():
    contract = admitted(credited_retained_record_declaration())
    assert admitted(contract.model_dump(mode="json")) == contract
    assert contract.credit[0].policy == "records_retained_completion_once@1"
    assert contract.credit[0].completion_selection == "earliest"


@pytest.mark.parametrize("change,reason", [
    ("no-effects", "record_completion_requires_effects"),
    ("no-earliest", "record_completion_requires_effects"),
    ("missing-baseline", "initial_goal_projection_mismatch"),
    ("wrong-effects", "requires_zendesk_effects"),
    ("unread-goal", "goal_field_not_read"),
])
def test_record_completion_contract_admission_is_explicit(change, reason):
    data = credited_retained_record_declaration()
    if change == "no-effects":
        del data["credit"][0]["effects"]
    elif change == "no-earliest":
        del data["credit"][0]["completion_selection"]
    elif change == "missing-baseline":
        del data["sources"]["initial"]["fields"]["status"]
    elif change == "wrong-effects":
        data["sources"]["writes"] = data["sources"]["final"]
    else:
        data["credit"][0]["goal_fields"] = ["id"]
    with pytest.raises(ValueError, match=reason):
        admitted(data)


def test_other_credit_policy_cannot_accept_a_record_effect_selector():
    data = declaration()
    data["credit"][0]["effects"] = "unused"
    with pytest.raises(ValueError, match="effects_source_only"):
        admitted(data)


def obligation_declaration():
    return {
        "schema_version": 1,
        "manifest_id": "required-message-fixture",
        "revision": "1",
        "public_request": "Notify every pending record.",
        "sources": {
            "requests": {
                "adapter": "initial.records@1",
                "path": ["task_evidence", "initial", "gmail", "messages"],
                "fields": {"Email": ["from_"], "Subject": ["subject"]},
                "key_fields": ["Email"],
            },
            "sends": {"adapter": "gmail.messages@1", "kind": "send"},
        },
        "checks": [{
            "check_id": "required-send", "signal_id": "notifications.sent", "role": "goal",
            "operator": "effects.required_when@1", "population": "requests", "source": "sends",
            "required_when": {
                "op": "eq", "left": {"kind": "literal", "value": True},
                "right": {"kind": "literal", "value": True},
            },
            "effect_match": {
                "op": "in", "left": {"kind": "field", "path": ["request", "Email"], "domain": "string"},
                "right": {"kind": "field", "path": ["effect", "recipients"], "domain": "sequence"},
            },
        }],
        "credit": [{"check": "required-send", "policy": "required_effect_once@1", "channel": "notification-progress"}],
    }


def test_required_effect_manifest_registers_initial_population_without_task_code():
    from automationbench_v1.contracts import InitialCollectionSource, ObligationCheck
    from automationbench_v1.contracts.engine import compile_contract

    selected = admitted(obligation_declaration())
    assert isinstance(selected.sources["requests"], InitialCollectionSource)
    assert isinstance(selected.checks[0], ObligationCheck)
    assert compile_contract(selected) == ("required-send",)
    assert admitted(selected.model_dump(mode="json")) == selected


@pytest.mark.parametrize("policy", ["verified_transition_once@1", "per_effect_negative@1"])
def test_required_effect_cannot_select_an_unrelated_credit_capability(policy):
    data = obligation_declaration()
    data["credit"][0]["policy"] = policy
    with pytest.raises(ValueError):
        admitted(data)


def test_record_goal_cannot_select_required_effect_credit():
    data = declaration()
    data["credit"][0]["policy"] = "required_effect_once@1"
    with pytest.raises(ValueError, match="credit_policy_check_capability_mismatch"):
        admitted(data)


@pytest.mark.parametrize("mode", ["missing", "final"])
def test_installed_manifest_requires_bound_public_policy(monkeypatch, mode):
    data = declaration()
    if mode == "final":
        data["bindings"] = [{
            "path": ["task_evidence", "final"], "canonical_sha256": "0" * 64,
        }]
    manifest = admitted(data)
    monkeypatch.setattr(loader, "load_contract", lambda _: manifest)
    with pytest.raises(ValueError, match="installed_manifest_requires_public_authority_bindings"):
        load_task_contract("simple.sf_opp_amount_update")


@pytest.mark.parametrize("population", ["sends", "absent"])
def test_required_effect_requires_a_supported_declared_population(population):
    data = obligation_declaration()
    data["checks"][0]["population"] = population
    with pytest.raises(ValueError, match="effect_check_requires_supported_population"):
        admitted(data)


def test_packaged_ten_contracts_preserve_public_requests_and_parameters():
    for previous in CONTRACTS:
        contract = load_task_contract(previous.task_name)
        assert isinstance(contract.sources["target"], RecordSource)
        assert contract.public_request == previous.user_request
        assert contract.revision == previous.revision
        assert contract.sources["target"].record_id == previous.record_id
        assert contract.sources["target"].object_type == "Opportunity"
        assert [
            (field.field, field.value, field.comparison)
            for field in contract.sources["target"].baseline_requirements
        ] == [
            (field.name, field.value, field.comparison) for field in previous.baseline_requirements
        ]
        goal, coverage = contract.checks
        assert isinstance(goal, CheckSpec)
        assert [(field.field, field.value, field.comparison) for field in goal.expected] == [
            (field.name, field.value, field.comparison) for field in previous.desired_fields
        ]
        assert (goal.signal_id, coverage.signal_id) == (
            "simple.requested_state",
            "simple.recording_coverage",
        )
        assert contract.credit[0].check == goal.check_id
        assert contract.credit[0].policy == "verified_transition_once@1"
        assert contract.bindings[0].path == ("task_evidence", "prompt", 1, "content")
        assert (
            contract.bindings[0].canonical_sha256
            == hashlib.sha256(
                json.dumps(
                    previous.user_request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
        )


def test_loading_never_invokes_old_task_evaluators(monkeypatch):
    from automationbench_v1 import simple_record_contracts

    def forbidden(*args, **kwargs):
        pytest.fail("contract loading invoked a task evaluator")

    monkeypatch.setattr(simple_record_contracts, "evaluate_simple_record_update", forbidden)
    monkeypatch.setattr(simple_record_contracts, "evaluate_record_update", forbidden)
    assert load_task_contract(CONTRACTS[0].task_name).manifest_id


def test_manifest_values_are_immutable_and_serializable():
    contract = admitted(declaration())
    assert isinstance(contract.sources["target"], RecordSource)
    with pytest.raises(TypeError):
        contract.sources["new"] = contract.sources["target"]
    with pytest.raises(ValidationError):
        contract.sources["target"].record_id = "different"
    with pytest.raises(ValidationError):
        contract.checks = ()
    assert load_contract(contract.model_dump_json()) == contract


def test_digest_is_canonical_but_changes_for_parameters_versions_and_audit_text():
    data = declaration()
    contract = admitted(data)
    encoded = json.dumps(data, indent=4).encode()
    reverse = json.dumps(dict(reversed(list(data.items()))))
    assert (
        canonical_contract_digest(contract)
        == canonical_contract_digest(load_contract(encoded))
        == canonical_contract_digest(load_contract(reverse))
    )
    assert len(canonical_contract_digest(contract)) == 64
    for path, value in (
        ("record_id", "006099"),
        ("public_request", "Different audit prose"),
        ("revision", "2"),
    ):
        changed = copy.deepcopy(data)
        if path == "record_id":
            changed["sources"]["target"][path] = value
        else:
            changed[path] = value
        assert canonical_contract_digest(admitted(changed)) != canonical_contract_digest(contract)


@pytest.mark.parametrize(
    "value", [True, False, None, {}, [], float("inf"), float("-inf"), float("nan")]
)
def test_strict_values_reject_bool_containers_null_and_nonfinite(value):
    data = declaration()
    data["checks"][0]["expected"][0]["value"] = value
    with pytest.raises((ValueError, ValidationError)):
        admitted(data)


@pytest.mark.parametrize("value", [True, "1", 2, 1.0])
def test_schema_versions_require_supported_exact_integer(value):
    data = declaration()
    data["schema_version"] = value
    with pytest.raises((ValueError, ValidationError)):
        admitted(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "adapter",
        "object",
        "operator",
        "policy",
        "unknown_field",
        "baseline_unknown_field",
        "source",
        "credit_check",
        "credit_diagnostic",
        "duplicate_checks",
        "conflicting_signal_roles",
        "duplicate_fields",
        "duplicate_baseline",
        "duplicate_credit",
        "empty_expectation",
        "coverage_expectation",
        "coverage_goal",
        "fields_diagnostic",
        "harm_role",
        "empty_sources",
        "empty_checks",
        "integer_value",
        "number_value",
        "schema_comparator",
        "calendar_invalid",
    ],
)
def test_invalid_contract_structure_and_capabilities_fail_before_scoring(mutation):
    data = declaration()
    check = data["checks"][0]
    field = check["expected"][0]
    target = data["sources"]["target"]
    if mutation == "extra":
        data["callback"] = "tasks.custom_function"
    elif mutation == "adapter":
        target["adapter"] = "salesforce.record@2"
    elif mutation == "object":
        target["object_type"] = "NotInstalled"
    elif mutation == "operator":
        check["operator"] = "python.eval@1"
    elif mutation == "policy":
        data["credit"][0]["policy"] = "sum_every_repeat@1"
    elif mutation == "unknown_field":
        field["field"] = "invented_field"
    elif mutation == "baseline_unknown_field":
        target["baseline_requirements"] = [{"field": "invented_field", "value": "x"}]
    elif mutation == "source":
        check["source"] = "not_declared"
    elif mutation == "credit_check":
        data["credit"][0]["check"] = "not_declared"
    elif mutation == "credit_diagnostic":
        check.update(role="diagnostic", operator="record.coverage@1", expected=[])
    elif mutation == "duplicate_checks":
        data["checks"].append(copy.deepcopy(check))
    elif mutation == "conflicting_signal_roles":
        second = copy.deepcopy(check)
        second["check_id"] = "second"
        second.update(role="diagnostic", operator="record.coverage@1", expected=[])
        data["checks"].append(second)
    elif mutation == "duplicate_fields":
        check["expected"].append(copy.deepcopy(field))
    elif mutation == "duplicate_baseline":
        target["baseline_requirements"] = [copy.deepcopy(field), copy.deepcopy(field)]
    elif mutation == "duplicate_credit":
        data["credit"].append(copy.deepcopy(data["credit"][0]))
    elif mutation == "empty_expectation":
        check["expected"] = []
    elif mutation == "coverage_expectation":
        check.update(operator="record.coverage@1", role="diagnostic")
    elif mutation == "coverage_goal":
        check.update(operator="record.coverage@1", expected=[])
    elif mutation == "fields_diagnostic":
        check["role"] = "diagnostic"
    elif mutation == "harm_role":
        check["role"] = "harm"
    elif mutation == "empty_sources":
        data["sources"] = {}
    elif mutation == "empty_checks":
        data["checks"] = []
    elif mutation == "integer_value":
        field.update(field="probability", value=75.0, comparison="integer")
    elif mutation == "number_value":
        field.update(field="amount", value="45000", comparison="number")
    elif mutation == "schema_comparator":
        field.update(field="amount", value="45000", comparison="string")
    elif mutation == "calendar_invalid":
        field.update(field="close_date", value="2026-02-30", comparison="calendar_date")
    with pytest.raises((ValueError, ValidationError)):
        admitted(data)


@pytest.mark.parametrize(
    "raw",
    [
        '{"schema_version":1,"schema_version":1}',
        '{"nested":{"field":"a","field":"b"}}',
        '{"value":NaN}',
        '{"value":Infinity}',
    ],
)
def test_duplicate_json_keys_and_nonfinite_constants_rejected(raw):
    with pytest.raises(ValueError):
        load_contract(raw)


@pytest.mark.parametrize(
    "path",
    [
        "../task.json",
        "tasks/../../outside.json",
        "/tmp/task.json",
        "tasks\\task.json",
        "tasks/sub/task.json",
        "tasks/task.py",
        "tasks//task.json",
    ],
)
def test_catalog_rejects_paths_outside_packaged_json_namespace(tmp_path, monkeypatch, path):
    (tmp_path / "catalog.json").write_text(
        json.dumps({"schema_version": 1, "tasks": {"task": path}})
    )
    monkeypatch.setattr(loader, "files", lambda package: tmp_path)
    with pytest.raises(ValueError, match="task_catalog_path"):
        load_task_contract("task")


def test_missing_task_is_explicit_selection_error():
    with pytest.raises(ValueError, match="task_manifest_unregistered"):
        load_task_contract("new.task_without_manifest")


def test_separate_obligations_can_share_signal_with_consistent_role():
    data = declaration()
    second = copy.deepcopy(data["checks"][0])
    second["check_id"] = "second-obligation"
    second["expected"] = [{"field": "type", "value": "New Business", "comparison": "string"}]
    data["checks"].append(second)
    contract = admitted(data)
    assert len(contract.checks) == 2
    assert contract.checks[0].signal_id == contract.checks[1].signal_id


@pytest.mark.parametrize(
    "path", [[], [True], ["task", False], ["task", -1], ["task", 1.0], ["task", None]]
)
def test_source_bindings_reject_empty_bool_negative_and_non_strict_paths(path):
    data = declaration()
    data["bindings"] = [{"path": path, "canonical_sha256": "a" * 64}]
    with pytest.raises(ValidationError):
        admitted(data)


@pytest.mark.parametrize("digest", ["x" * 64, "a" * 63, "a" * 65, True])
def test_source_bindings_require_exact_canonical_sha256(digest):
    data = declaration()
    data["bindings"] = [{"path": ["task", 0, "value"], "canonical_sha256": digest}]
    with pytest.raises(ValidationError):
        admitted(data)


def test_duplicate_binding_path_rejects_even_if_hashes_differ():
    data = declaration()
    data["bindings"] = [
        {"path": ["task"], "canonical_sha256": digest * 64} for digest in ("a", "b")
    ]
    with pytest.raises(ValidationError, match="duplicate_source_binding"):
        admitted(data)


@pytest.mark.parametrize(
    "rule",
    [
        {"policy": "verified_transition_once@1", "channel": "goal"},
        {
            "policy": "verified_transition_once@1",
            "check": "stage",
            "checks": ["stage", "second"],
            "channel": "goal",
        },
        {"policy": "joint_verified_transition_once@1", "checks": ["stage"], "channel": "goal"},
        {
            "policy": "joint_verified_transition_once@1",
            "checks": ["stage", "stage"],
            "channel": "goal",
        },
        {
            "policy": "joint_verified_transition_once@1",
            "check": "stage",
            "checks": ["stage", "second"],
            "channel": "goal",
        },
        {
            "policy": "joint_verified_transition_once@1",
            "checks": ["stage", "unknown"],
            "channel": "goal",
        },
    ],
)
def test_joint_credit_requires_only_two_or_more_unique_known_goal_parents(rule):
    data = declaration()
    second = copy.deepcopy(data["checks"][0])
    second["check_id"] = "second"
    data["checks"].append(second)
    data["credit"] = [rule]
    with pytest.raises(ValidationError):
        admitted(data)


def test_valid_joint_credit_retains_both_goal_references():
    data = declaration()
    second = copy.deepcopy(data["checks"][0])
    second["check_id"] = "second"
    data["checks"].append(second)
    data["credit"] = [
        {
            "policy": "joint_verified_transition_once@1",
            "checks": ["stage", "second"],
            "channel": "goal",
        }
    ]
    contract = admitted(data)
    assert contract.credit[0].check is None and contract.credit[0].checks == ("stage", "second")


def test_joint_credit_rejects_undefined_cross_signal_aggregation():
    data = declaration()
    second = copy.deepcopy(data["checks"][0])
    second.update(check_id="second", signal_id="another.goal")
    data["checks"].append(second)
    data["credit"] = [
        {
            "policy": "joint_verified_transition_once@1",
            "checks": ["stage", "second"],
            "channel": "goal",
        }
    ]
    with pytest.raises(ValidationError, match="joint_credit_requires_shared_signal"):
        admitted(data)


def test_catalog_supported_tasks_matches_all_packaged_contracts():
    from automationbench_v1.contracts import supported_tasks

    assert supported_tasks() == tuple(sorted({
        *(item.task_name for item in CONTRACTS),
        "sales.multi_hop_lookup", "simple.email_airtable_customer_welcome", "sales.docusign_void_resend",
        "finance.prepaid_amortization",
        "simple.feature_launch_slack",
        "simple.jira_accessibility_audit",
        "marketing.content_repurpose",
        "hr.docusign_nda_collection",
        "support.zoho_account_health", "marketing.brand_mention_analysis",
        "simple.zendesk_resolve_email",
        "simple.email_sf_contact_assistant_update", "simple.email_sf_contact_account_update",
        "simple.email_zendesk_ack_reply", "finance.escrow_tracking", "hr.airtable_learning_path_assignment",
        "operations.zoom_training_setup", "operations.calendly_equipment_inspection",
        *json.loads((Path(__file__).with_name("installed_candidate_manifests.json")).read_text()),
    }))


def mixed_declaration():
    from test_manifest_guards import declaration as guard_declaration

    data = declaration()
    for name in ("queue", "directory"):
        data["sources"][name] = {
            "adapter": "google_sheets.rows@1",
            "path": ["task_evidence", "initial", "google_sheets"],
            "spreadsheet_id": "sheet",
            "worksheet_id": name,
            "key_fields": ["Email"],
        }
    data["sources"]["creates"] = {"adapter": "asana.actions@1", "kind": "create_task"}
    data["checks"].append(guard_declaration())
    data["credit"].append(
        {"check": "prohibited-provision", "policy": "per_effect_negative@1", "channel": "harm"}
    )
    return data


def test_single_manifest_accepts_record_table_effect_sources_and_harm_checks():
    from automationbench_v1.contracts import EffectSource, GuardCheck, RecordSource, TableSource

    contract = admitted(mixed_declaration())
    assert isinstance(contract.sources["target"], RecordSource)
    assert isinstance(contract.sources["queue"], TableSource)
    assert isinstance(contract.sources["creates"], EffectSource)
    assert isinstance(contract.checks[-1], GuardCheck)
    assert load_contract(contract.model_dump_json()) == contract
    assert contract.credit[-1].policy == "per_effect_negative@1"


@pytest.mark.parametrize(
    "mutation",
    [
        "record-on-table",
        "guard-on-record",
        "population-on-effect",
        "lookup-on-record",
        "lookup-key",
        "negative-on-goal",
        "positive-on-harm",
        "negative-joint",
        "conflicting-role",
    ],
)
def test_manifest_rejects_incompatible_capabilities_references_and_credit(mutation):
    data = mixed_declaration()
    guard = data["checks"][-1]
    if mutation == "record-on-table":
        data["checks"][0]["source"] = "queue"
    elif mutation == "guard-on-record":
        guard["source"] = "target"
    elif mutation == "population-on-effect":
        guard["population"] = "creates"
    elif mutation == "lookup-on-record":
        guard["lookups"][0]["source"] = "target"
    elif mutation == "lookup-key":
        data["sources"]["directory"]["key_fields"] = ["Another key"]
    elif mutation == "negative-on-goal":
        data["credit"][0]["policy"] = "per_effect_negative@1"
    elif mutation == "positive-on-harm":
        data["credit"][-1]["policy"] = "verified_transition_once@1"
    elif mutation == "negative-joint":
        data["credit"][-1].update(check=None, checks=["stage", "prohibited-provision"])
    else:
        guard["signal_id"] = data["checks"][0]["signal_id"]
    with pytest.raises(ValidationError):
        admitted(data)
