"""Real HubSpot handlers with manufactured acknowledged native envelopes.

These fixtures qualify adapter facts, not business intent or native task credit.
"""

import copy
import json
from typing import Literal

import pytest
from pydantic import ValidationError
from test_manifest_jira_effects import mutate_capture
from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.hubspot.crm import (
    hubspot_add_contact_to_deal,
    hubspot_create_contact,
    hubspot_create_deal,
)
from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.hubspot_objects import (
    HubSpotEvidence,
    HubSpotObjectSource,
    capture_hubspot_evidence,
    validate_hubspot_evidence,
)


def initial():
    return {"hubspot": {"contacts": [{"id": "contact-1", "email": "person@example.com"}],
                        "deals": []}}


def contact(**changes):
    args = {"email": "new@example.com", "first_name": "Jo", **changes}
    return zapier("hubspot_create_contact", args, lambda world: hubspot_create_contact(world, **args))


def deal(**changes):
    args = {"dealname": "Renewal", "dealstage": "qualifiedtobuy", "amount": 0, **changes}
    return zapier("hubspot_create_deal", args, lambda world: hubspot_create_deal(world, **args))


def associate(contact_id="contact-1"):
    args = {"deal_id": "deal-1", "contact_id": contact_id}
    return zapier("hubspot_add_contact_to_deal", args,
        lambda world: hubspot_add_contact_to_deal(world, **args))


def existing():
    value = initial()
    value["hubspot"]["deals"] = [{"id": "deal-1", "dealname": "Renewal", "dealstage": "qualifiedtobuy"}]
    return value


def evidence(source, collection: Literal["contacts", "deals"] = "deals"):
    return capture_hubspot_evidence(source, HubSpotObjectSource(collection=collection))


def qualified(result):
    return [item for item in result.transitions if item.status == "qualified"]


def test_real_creation_aliases_properties_and_zero_amount_are_canonical():
    source = run_operations(initial(), [contact(properties={"custom": 42}), deal()])
    contacts, deals = evidence(source, "contacts"), evidence(source)
    assert contacts.complete and deals.complete
    assert contacts.initial.all_object_ids == ("contact-1",)
    for result in (contacts, deals):
        (created,) = qualified(result)
        assert created.kind == "create" and created.before_object_json is None
        assert created.receipt_id == created.invocation_id != created.object_id
        assert created.object_id not in result.initial.all_object_ids
        assert created.object_id in result.final.all_object_ids
        assert created.expected_revision is not None and created.applied_revision == created.expected_revision + 1
    contact_json = qualified(contacts)[0].after_object_json
    assert contact_json is not None
    native_contact = json.loads(contact_json)
    assert native_contact["firstname"] == "Jo" and native_contact["properties"] == {"custom": "42"}
    deal_json = qualified(deals)[0].after_object_json
    assert deal_json is not None
    native_deal = json.loads(deal_json)
    assert native_deal["amount"] == 0 and "hs_object_id" not in native_deal
    response = json.loads(json.loads(json.loads(source["tool_execution_events"][1]["receipt_json"])["evidence_json"][0])["action"]["result_json"])
    assert json.loads(response)["deal"]["amount"] is None


def test_real_association_preserves_deal_contact_identity_and_timestamp_noop():
    source = run_operations(existing(), [associate(), associate()])
    result = evidence(source)
    assert result.complete
    first, repeated = qualified(result)
    assert first.kind == repeated.kind == "association_update"
    assert first.object_id == repeated.object_id == "deal-1"
    assert first.changed_fields == first.requested_fields == ("associated_contact_ids",)
    assert repeated.changed_fields == () and repeated.requested_fields == first.requested_fields
    assert first.before_object_json is not None and first.after_object_json is not None
    assert json.loads(first.before_object_json)["associated_contact_ids"] == []
    assert json.loads(first.after_object_json)["associated_contact_ids"] == ["contact-1"]
    assert first.receipt_id != repeated.receipt_id


def test_handler_accepts_nonexistent_contact_but_adapter_does_not():
    source = run_operations(existing(), [associate("missing-contact")])
    assert source["task_evidence"]["final"]["hubspot"]["deals"][0]["associated_contact_ids"] == ["missing-contact"]
    result = evidence(source)
    assert not result.complete and not qualified(result)
    assert result.transitions[0].reason == "hubspot_association_contact_or_deal_unavailable"


def test_missing_inventory_never_infers_empty_or_episode_initial_absence():
    source = run_operations(initial(), [deal()])
    source["task_evidence"]["initial"]["hubspot"].pop("deals")
    result = evidence(source)
    assert not result.initial.identities_complete and not result.initial.closed
    assert result.initial.all_object_ids == () and qualified(result)
    assert not result.complete


def test_sparse_explicit_initial_fields_hydrate_only_with_revision_zero_proof():
    source = run_operations(existing(), [associate()])
    source["task_evidence"]["initial"] = existing()
    result = evidence(source)
    assert result.initial.closed
    assert json.loads(result.initial.objects[0].object_json)["associated_contact_ids"] == []
    source["state_write_receipts"] = []
    result = evidence(source)
    assert result.initial.identities_complete and not result.initial.fields_complete
    assert "associated_contact_ids" not in json.loads(result.initial.objects[0].object_json)


@pytest.mark.parametrize("mutation", ["missing_ack", "bool_revision", "raised", "error", "wrong_result", "wrong_requested_id"])
def test_transition_admission_rejects_unqualified_or_conflicting_evidence(mutation):
    source = run_operations(existing(), [associate()])
    if mutation == "missing_ack":
        source["state_write_receipts"] = []
    elif mutation == "bool_revision":
        source["state_write_receipts"][0]["expected_revision"] = False
    else:
        def change(action, before, after, result):
            if mutation == "raised":
                action["status"] = "raised"
            elif mutation == "error":
                action["error_json"] = canonical_json({"type": "RuntimeError"})
            elif mutation == "wrong_result":
                result["deal_id"] = "other"
            else:
                args = json.loads(action["arguments_json"])
                nested = json.loads(args["arguments"])
                nested["deal_id"] = "other"
                args["arguments"] = canonical_json(nested)
                action["arguments_json"] = canonical_json(args)
        source = mutate_capture(source, 0, change)
    result = evidence(source)
    assert not qualified(result) and not result.complete


def test_known_creation_survives_later_unsupported_operation_and_missing_ack():
    unsupported = zapier("custom_update", {}, lambda world: "{}")
    source = run_operations(initial(), [deal(), unsupported])
    source["state_write_receipts"].pop()
    result = evidence(source)
    assert len(qualified(result)) == 1 and result.transitions[1].status == "unavailable"
    assert not result.complete


def test_final_damage_does_not_erase_original_creation_fact():
    def damage(world):
        world.hubspot.deals.clear()
        return "{}"
    source = run_operations(initial(), [deal(), zapier("custom_delete", {}, damage)])
    result = evidence(source)
    assert len(qualified(result)) == 1 and result.final.objects == ()
    assert not result.complete


@pytest.mark.parametrize("bad", [True, 1.0, None])
def test_malformed_object_ids_preserve_independent_known_final_object(bad):
    source = run_operations(initial(), [deal()])
    source["task_evidence"]["final"]["hubspot"]["deals"].append({"id": bad})
    result = evidence(source)
    assert len(result.final.objects) == 1 and not result.final.identities_complete
    assert qualified(result) and not result.complete


def test_duplicate_target_ids_remove_only_ambiguous_object_proof():
    source = run_operations(existing(), [])
    source["task_evidence"]["final"]["hubspot"]["deals"].append(copy.deepcopy(source["task_evidence"]["final"]["hubspot"]["deals"][0]))
    result = evidence(source)
    assert result.final.identities_complete and result.final.duplicate_ids == ("deal-1",)
    assert result.final.objects == () and not result.final.closed


@pytest.mark.parametrize("field,bad", [("amount", True), ("amount", "0"), ("amount", 10**400), ("dealstage", 1)])
def test_raw_field_types_are_not_coerced_or_defaulted(field, bad):
    source = run_operations(initial(), [deal()])
    source["task_evidence"]["final"]["hubspot"]["deals"][0][field] = bad
    result = evidence(source)
    assert field not in json.loads(result.final.objects[0].object_json)
    assert result.final.identities_complete and not result.final.fields_complete


def test_finalization_requires_exact_true_and_does_not_erase_known_facts():
    source = run_operations(initial(), [deal()])
    source["task_evidence"]["complete"] = 1
    result = evidence(source)
    assert not result.final.finalized and not result.final.closed
    assert len(result.final.objects) == len(qualified(result)) == 1


def test_receipt_native_result_disagreement_is_not_accepted():
    source = run_operations(initial(), [deal()])
    receipt = json.loads(source["tool_execution_events"][0]["receipt_json"])
    receipt["result_json"] = canonical_json({"success": True, "deal_id": "other"})
    source["tool_execution_events"][0]["receipt_json"] = canonical_json(receipt)
    assert not qualified(evidence(source))


def test_json_reload_raw_recapture_and_copied_metadata_rejection():
    source = run_operations(existing(), [associate()])
    spec = HubSpotObjectSource(collection="deals")
    result = evidence(source)
    restored = HubSpotEvidence.model_validate_json(result.model_dump_json())
    validate_hubspot_evidence(restored, source, spec)
    forged = restored.model_copy(update={"complete": 1})
    with pytest.raises(ValidationError):
        validate_hubspot_evidence(forged, source, spec)
    forged = restored.model_copy(update={"final": restored.final.model_copy(update={"objects": ()})})
    with pytest.raises(ValueError, match="source_or_selector_mismatch"):
        validate_hubspot_evidence(forged, source, spec)
    source["task_evidence"]["final"]["hubspot"]["deals"][0]["dealstage"] = "lost"
    with pytest.raises(ValueError, match="source_or_selector_mismatch"):
        validate_hubspot_evidence(restored, source, spec)


def test_copied_selector_and_unknown_collection_rejected():
    spec = HubSpotObjectSource(collection="deals").model_copy(update={"collection": True})
    with pytest.raises(ValidationError):
        capture_hubspot_evidence(run_operations(initial(), []), spec)


def test_repeated_identical_creates_are_distinct_native_objects_and_receipts():
    result = evidence(run_operations(initial(), [deal(), deal()]))
    assert result.complete and len(qualified(result)) == 2
    assert len({item.object_id for item in qualified(result)}) == 2
    assert len({item.receipt_id for item in qualified(result)}) == 2


def test_failed_real_handler_return_is_not_a_qualified_association():
    source = run_operations(initial(), [associate()])
    result = evidence(source)
    assert not qualified(result)
    assert result.transitions[0].reason == "hubspot_response_unsuccessful"


def test_duplicate_contact_identity_cannot_prove_the_relationship():
    raw = existing()
    raw["hubspot"]["contacts"].append(copy.deepcopy(raw["hubspot"]["contacts"][0]))
    result = evidence(run_operations(raw, [associate()]))
    assert not qualified(result)
    assert result.transitions[0].reason == "hubspot_association_contact_or_deal_unavailable"


def test_request_field_forgery_and_other_state_mutation_reject_create():
    source = run_operations(initial(), [deal()])
    def field(action, before, after, result):
        after["hubspot"]["deals"][0]["dealstage"] = "invented"
    assert not qualified(evidence(mutate_capture(source, 0, field)))
    def unrelated(action, before, after, result):
        after["hubspot"]["contacts"][0]["email"] = "other@example.com"
    assert not qualified(evidence(mutate_capture(source, 0, unrelated)))


def test_same_native_deal_association_damage_then_repair_is_independent():
    def remove(world):
        world.hubspot.deals[0].associated_contact_ids.clear()
        return "{}"
    source = run_operations(existing(), [associate(), zapier("custom_remove", {}, remove), associate()])
    result = evidence(source)
    assert not result.complete
    writes = qualified(result)
    assert len(writes) == 2 and {item.object_id for item in writes} == {"deal-1"}
    assert all(item.changed_fields == ("associated_contact_ids",) for item in writes)
    assert json.loads(result.final.objects[0].object_json)["associated_contact_ids"] == ["contact-1"]


def test_contact_integer_and_bool_fields_remain_strict_independently():
    source = run_operations(initial(), [contact()])
    raw = source["task_evidence"]["final"]["hubspot"]["contacts"][0]
    raw.update(lead_score=True, demo_requested=1, lifetime_value=10**400)
    result = evidence(source, "contacts")
    record = json.loads(result.final.objects[0].object_json)
    assert all(name not in record for name in ("lead_score", "demo_requested", "lifetime_value"))
    assert record["email"] == "person@example.com" and result.final.identities_complete
    assert not result.final.fields_complete
