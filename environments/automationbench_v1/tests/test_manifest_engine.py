"""Executed native state checks authored by manifests rather than task code."""

import copy
import hashlib
import json

import pytest
from test_record_update_evidence import CONTRACTS, public, source, update

from automationbench_v1.contracts import load_contract, load_task_contract
from automationbench_v1.contracts.engine import Evaluation, compile_contract, evaluate_contract


@pytest.mark.parametrize("previous", CONTRACTS, ids=lambda item: item.task_name)
def test_ten_packaged_manifest_goals_on_executed_native_updates(previous):
    contract = load_task_contract(previous.task_name)
    evaluation = evaluate_contract(source(previous), contract)
    assert [(item.status, item.value) for item in evaluation.results] == [
        ("valid", 1),
        ("valid", 1),
    ]
    assert tuple(item.check_id for item in evaluation.results) == compile_contract(contract)
    assert evaluation.source_digest and evaluation.contract_digest
    assert Evaluation.model_validate_json(evaluation.model_dump_json()) == evaluation


@pytest.mark.parametrize("previous", [CONTRACTS[0], CONTRACTS[2], CONTRACTS[3], CONTRACTS[4]])
@pytest.mark.parametrize("generic,api", [(True, False), (False, True)])
def test_generic_and_api_native_updates_accept_string_number_date_and_integer(
    previous, generic, api
):
    evaluation = evaluate_contract(
        source(previous, [update(previous, generic=generic, api=api)]),
        load_task_contract(previous.task_name),
    )
    assert [item.value for item in evaluation.results] == [1, 1]


@pytest.mark.parametrize("mutation", ["absent", "duplicate", "schema"])
def test_missing_ambiguous_or_invalid_target_is_unavailable(mutation):
    data = source()
    rows = data["task_evidence"]["initial"]["salesforce"]["opportunities"]
    if mutation == "absent":
        rows.clear()
    elif mutation == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    else:
        rows[0]["invented_native_field"] = "unsupported"
    evaluation = evaluate_contract(data, load_task_contract(CONTRACTS[0].task_name))
    assert evaluation.results[0].status == "abstained"
    assert evaluation.results[0].value is None


@pytest.mark.parametrize(
    "previous,field,value",
    [
        (CONTRACTS[5], "description", "Existing context"),
        (CONTRACTS[6], "stage_name", "Negotiation/Review"),
    ],
)
def test_baseline_authority_mismatch_does_not_become_goal_zero(previous, field, value):
    initial = copy.deepcopy(public(previous)["info"]["initial_state"])
    initial["salesforce"]["opportunities"][0][field] = value
    evaluation = evaluate_contract(
        source(previous, initial=initial), load_task_contract(previous.task_name)
    )
    assert evaluation.results[0].status == "abstained"
    assert evaluation.results[0].reason == "record_baseline_interpretation_unresolved"


def test_requested_state_zero_is_distinct_from_unavailable_recording():
    previous = CONTRACTS[0]
    data = source(previous, [update(previous, "Prospecting")])
    data["state_write_receipts"] = []
    evaluation = evaluate_contract(data, load_task_contract(previous.task_name))
    assert evaluation.results[0].status == "valid" and evaluation.results[0].value == 0
    assert evaluation.results[1].status == "abstained" and evaluation.results[1].value is None


def test_new_identity_value_and_task_are_data_only():
    previous = CONTRACTS[0]
    manifest = load_task_contract(previous.task_name).model_dump(mode="json")
    manifest["manifest_id"] = "another-opportunity-instance"
    manifest["public_request"] = "Changed human-readable request; not runtime admission."
    manifest["sources"]["target"]["record_id"] = "new-record-901"
    manifest["checks"][0]["expected"][0]["value"] = "Closed Lost"
    manifest["bindings"] = [
        {
            "path": ["task_evidence", "prompt", 0, "content"],
            "canonical_sha256": hashlib.sha256(
                json.dumps("A different task instance").encode()
            ).hexdigest(),
        }
    ]
    contract = load_contract(json.dumps(manifest))
    initial = copy.deepcopy(public(previous)["info"]["initial_state"])
    initial["salesforce"]["opportunities"][0]["id"] = "new-record-901"
    data = source(previous, [update(previous, "Closed Lost", target="new-record-901")], initial)
    data["task_evidence"].update(
        task_name="custom.new_record_task",
        prompt=[{"role": "user", "content": "A different task instance"}],
    )
    assert [item.value for item in evaluate_contract(data, contract).results] == [1, 1]


def test_engine_does_not_call_old_task_evaluators(monkeypatch):
    from automationbench_v1 import simple_record_contracts

    data = source()

    def forbidden(*args, **kwargs):
        pytest.fail("manifest runtime called a legacy task evaluator")

    monkeypatch.setattr(simple_record_contracts, "evaluate_record_update", forbidden)
    monkeypatch.setattr(simple_record_contracts, "evaluate_simple_record_update", forbidden)
    assert evaluate_contract(data, load_task_contract(CONTRACTS[0].task_name)).results[0].value == 1


def test_expected_check_selection_cannot_depend_on_outcome_or_unknown_targets():
    contract = load_task_contract(CONTRACTS[0].task_name)
    assert compile_contract(contract) == ("requested-state", "recording-coverage")
    assert len(evaluate_contract(source(), contract, check_ids=("requested-state",)).results) == 1
    for checks in (("unknown",), ("requested-state", "requested-state")):
        with pytest.raises(ValueError, match="requested_check"):
            evaluate_contract(source(), contract, check_ids=checks)


def test_cached_record_evidence_cannot_be_reused_for_another_executed_source():
    from automationbench_v1.contracts.evidence import capture_records

    contract = load_task_contract(CONTRACTS[0].task_name)
    good = source()
    wrong = source(operations=[update(CONTRACTS[0], "Prospecting")])
    cache = capture_records(good, contract.sources)
    assert evaluate_contract(good, contract, evidence=cache).results[0].value == 1
    assert evaluate_contract(wrong, contract).results[0].value == 0
    with pytest.raises(ValueError, match="source_or_selector_mismatch"):
        evaluate_contract(wrong, contract, evidence=cache)


def test_cached_evidence_cannot_be_reused_for_changed_selector():
    from automationbench_v1.contracts.evidence import capture_records

    contract = load_task_contract(CONTRACTS[0].task_name)
    data = source()
    cache = capture_records(data, contract.sources)
    manifest = contract.model_dump(mode="json")
    manifest["sources"]["target"]["record_id"] = "another-record"
    with pytest.raises(ValueError, match="source_or_selector_mismatch"):
        evaluate_contract(data, load_contract(json.dumps(manifest)), evidence=cache)


@pytest.mark.parametrize("variation", ["missing", "different"])
def test_explicit_public_fragment_binding_failure_abstains(variation):
    data = source()
    if variation == "missing":
        data["task_evidence"]["prompt"] = []
    else:
        data["task_evidence"]["prompt"][1]["content"] = "Different public instruction"
    evaluation = evaluate_contract(data, load_task_contract(CONTRACTS[0].task_name))
    assert all(
        result.status == "abstained" and result.value is None for result in evaluation.results
    )
