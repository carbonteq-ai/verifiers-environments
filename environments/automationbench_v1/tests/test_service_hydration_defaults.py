"""Initial-state reconciliation compares deterministic defaults of omitted fields.

Minimal reproduction (before the repair every case below marked False passed):
an omitted Gmail ``body_html`` hydrates to ``None``, yet an observed native
service carrying invented HTML, labels or recipients reconciled with public
state because omitted record fields were never compared.
"""

import copy

import pytest

from automationbench.schema.world import WorldState
from automationbench_v1.contracts.service_hydration import public_service_matches

POLICY = {
    "id": "m1",
    "from": "cfo@acme.com",
    "to": ["me@acme.com"],
    "subject": "Policy",
    "body": "Cap is $500",
    "date": "2026-01-02T10:00:00Z",
}


def native(initial, service):
    return WorldState.model_validate(copy.deepcopy(initial)).model_dump(mode="json")[service]


def gmail(**message):
    return {"gmail": {"messages": [{**POLICY, **message}]}}


def test_honest_sparse_gmail_reconciles():
    assert public_service_matches(gmail(), "gmail", native(gmail(), "gmail"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("body_html", "<p>Cap is $5,000</p>"),  # omitted -> None
        ("label_ids", ["IMPORTANT"]),  # omitted -> []
        ("cc", ["someone@else.com"]),  # omitted -> []
        ("is_read", True),  # omitted -> False
        ("snippet", "Cap is $5,000"),  # omitted -> None
        ("size_estimate", 7),  # omitted -> 1000
    ],
)
def test_invented_content_in_omitted_deterministic_fields_does_not_reconcile(field, value):
    observed = native(gmail(), "gmail")
    observed["messages"][0][field] = value
    assert not public_service_matches(gmail(), "gmail", observed)


def test_generated_identity_and_clock_defaults_are_tolerated():
    # thread_id is a generated id; with no public date both timestamps are now().
    initial = {
        "gmail": {"messages": [{key: value for key, value in POLICY.items() if key != "date"}]}
    }
    observed = native(initial, "gmail")
    observed["messages"][0]["thread_id"] = "a-different-generated-thread"
    observed["messages"][0]["date"] = 1
    observed["messages"][0]["internal_date"] = 2
    assert public_service_matches(initial, "gmail", observed)


def test_values_derived_from_public_input_are_compared():
    # internal_date is mirrored from the public date by a validator, not generated.
    observed = native(gmail(), "gmail")
    observed["messages"][0]["internal_date"] += 1
    assert not public_service_matches(gmail(), "gmail", observed)


def test_explicit_public_fields_still_compared():
    observed = native(gmail(), "gmail")
    observed["messages"][0]["body_plain"] = "Cap is $5,000"
    assert not public_service_matches(gmail(), "gmail", observed)


def test_free_form_mapping_rejects_observed_keys_absent_from_public_state():
    # Real case: an agent wrote properties.payment_retry_count on HubSpot contacts
    # and the final service still "reconciled" with public initial state.
    initial = {
        "hubspot": {
            "contacts": [{"id": "c1", "properties": {"email": "a@b.com", "firstname": "Al"}}]
        }
    }
    observed = native(initial, "hubspot")
    assert public_service_matches(initial, "hubspot", observed)
    observed["contacts"][0]["properties"]["payment_retry_count"] = "3"
    assert not public_service_matches(initial, "hubspot", observed)


def test_absent_service_and_omitted_top_level_collections_remain_compatible():
    assert public_service_matches(
        {}, "gmail", WorldState.model_validate({}).model_dump(mode="json")["gmail"]
    )
    sparse = {"slack": {"channels": [{"id": "C1", "name": "ops", "channel_type": "public"}]}}
    assert public_service_matches(sparse, "slack", native(sparse, "slack"))


def test_slack_nested_messages_normalization_still_reconciles_and_rejects_invention():
    public = {
        "slack": {
            "channels": [
                {
                    "id": "C1",
                    "name": "ops",
                    "channel_type": "public",
                    "messages": [
                        {"text": "Freeze all changes", "ts": "1741080000.000001", "user_id": "U1"}
                    ],
                }
            ]
        }
    }
    observed = native(public, "slack")
    assert public_service_matches(public, "slack", observed)
    altered = copy.deepcopy(observed)
    message = next(item for item in altered["messages"] if item["ts"] == "1741080000.000001")
    message["is_pinned" if "is_pinned" in message else "text"] = (
        not message["is_pinned"] if "is_pinned" in message else "Different"
    )
    assert not public_service_matches(public, "slack", altered)


def test_explicit_empty_action_mapping_rejects_created_action_records():
    # Real case: public Asana state {"actions": {}} "reconciled" with a terminal
    # world in which the agent had created a task.
    initial = {"asana": {"actions": {}}}
    observed = native(initial, "asana")
    assert public_service_matches(initial, "asana", observed)
    observed["actions"]["create_task"] = [{"action_key": "create_task", "id": "asana_1", "params": {"name": "x"}}]
    assert not public_service_matches(initial, "asana", observed)
