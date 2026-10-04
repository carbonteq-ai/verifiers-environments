"""Actual initial collections and adversarial population closure boundaries."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.populations import (
    InitialCollectionSource,
    PopulationEvidence,
    capture_population,
    lookup_population,
    validate_population_evidence,
)
from automationbench_v1.contracts.tables import TableSource, capture_table


def spec(**changes):
    return InitialCollectionSource.model_validate({
        "path": ["task_evidence", "initial", "gmail", "messages"],
        "fields": {"Email": ["from_"], "Subject": ["subject"], "Recipients": ["to"]},
        "key_fields": ["Email"], "required_fields": ["Subject"], **changes})


@pytest.mark.parametrize('service,collection,field', [
    ('salesforce', 'accounts', 'account_name'), ('salesforce', 'contacts', 'email'),
    ('helpscout', 'conversations', 'customer_email'), ('hubspot', 'contacts', 'email'),
    ('hubspot', 'deals', 'dealname'), ('zendesk', 'tickets', 'subject'),
    ('zendesk', 'users', 'email'), ('quickbooks', 'payments', 'customer_id'),
])
def test_installed_typed_collection_admission_uses_explicit_raw_identity(service, collection, field):
    source = InitialCollectionSource(path=('task_evidence', 'initial', service, collection),
        fields={'Key': (field,)}, key_fields=('Key',))
    raw = {'task_evidence': {'initial': {service: {collection: [{'id': 'native', field: 'exact'}]}}}}
    evidence = capture_population(raw, source)
    assert evidence.closed and len(evidence.rows) == 1
    assert evidence.rows[0].identity[-1] == 'native'
    assert lookup_population(evidence, {'Key': 'exact'}).status == 'matched'
    restored = PopulationEvidence.model_validate_json(evidence.model_dump_json())
    validate_population_evidence(restored, raw)
    raw['task_evidence']['initial'][service][collection][0][field] = 'changed'
    with pytest.raises(ValueError, match='source_or_projection'):
        validate_population_evidence(restored, raw)


@pytest.mark.parametrize('service,collection,field', [
    ('missing', 'records', 'id'), ('gmail', 'missing', 'id'),
    ('jira', 'issues', 'id'), ('asana', 'actions', 'id'),
    ('slack', 'messages', 'text'), ('zoom', 'meetings', 'topic'),
    ('salesforce', 'contacts', 'Email'),
])
def test_schema_registry_rejects_unknown_untyped_optional_union_and_alias_fields(service, collection, field):
    with pytest.raises(ValidationError):
        InitialCollectionSource(path=('task_evidence', 'initial', service, collection),
            fields={'Key': (field,)}, key_fields=('Key',))


def test_new_collection_never_hydrates_absence_or_missing_generated_identity():
    source = InitialCollectionSource(path=('task_evidence', 'initial', 'salesforce', 'contacts'),
        fields={'Email': ('email',)}, key_fields=('Email',))
    absent = capture_population({'task_evidence': {'initial': {'salesforce': {}}}}, source)
    empty = capture_population({'task_evidence': {'initial': {'salesforce': {'contacts': []}}}}, source)
    no_id = capture_population({'task_evidence': {'initial': {'salesforce': {'contacts': [{'email': 'exact'}]}}}}, source)
    assert not absent.closed and absent.status == 'unavailable'
    assert empty.closed and empty.enumerated
    assert not no_id.closed and not no_id.enumerated and not no_id.rows


def test_new_collection_receipts_reject_installed_schema_drift(monkeypatch):
    from automationbench_v1.contracts.populations import _model

    source = InitialCollectionSource(path=('task_evidence', 'initial', 'salesforce', 'contacts'),
        fields={'Email': ('email',)}, key_fields=('Email',))
    raw = {'task_evidence': {'initial': {'salesforce': {'contacts': [{'id': 'native', 'email': 'exact'}]}}}}
    evidence = capture_population(raw, source)
    model = _model('salesforce', 'contacts')
    schema = model.model_json_schema()
    changed = copy.deepcopy(schema)
    changed['title'] = 'Changed installed schema'
    monkeypatch.setattr(model, 'model_json_schema', lambda: changed)
    with pytest.raises(ValueError, match='schema|source_or_projection'):
        validate_population_evidence(evidence, raw)


def material(records=None):
    return {"task_evidence": {"initial": {"gmail": {"messages": records if records is not None
            else [{"id": "native-1", "from_": "person@example.com", "subject": "Exact", "to": []}]}}}}


def test_initial_projection_is_immutable_exact_and_source_bound():
    raw = material()
    evidence = capture_population(raw, spec())
    assert evidence.closed and evidence.enumerated
    assert lookup_population(evidence, {"Email": "person@example.com"}).status == "matched"
    assert json.loads(evidence.rows[0].cells_json)["Recipients"] == []
    assert evidence.rows[0].identity == (
        "initial.records@1", canonical_json(spec().path), "str", "native-1")
    restored = PopulationEvidence.model_validate_json(evidence.model_dump_json())
    validate_population_evidence(restored, raw)
    raw["task_evidence"]["initial"]["gmail"]["messages"][0]["subject"] = "Changed"
    assert json.loads(evidence.rows[0].cells_json)["Subject"] == "Exact"
    with pytest.raises(ValueError, match="source_or_projection"):
        validate_population_evidence(restored, raw)
    with pytest.raises(TypeError):
        evidence.source.fields["Email"] = ("subject",)


def test_missing_collection_never_becomes_empty():
    missing = capture_population({"task_evidence": {"initial": {"gmail": {}}}}, spec())
    empty = capture_population(material([]), spec())
    assert not missing.closed and missing.status == "unavailable"
    assert empty.closed and lookup_population(empty, {"Email": "nobody"}).status == "not_found"


@pytest.mark.parametrize("bad", [None, True, 7, "", {}, []])
def test_unqualified_native_identity_blocks_closure_but_keeps_known_members(bad):
    raw = material()
    raw["task_evidence"]["initial"]["gmail"]["messages"].append({"id": bad})
    evidence = capture_population(raw, spec())
    result = lookup_population(evidence, {"Email": "person@example.com"})
    assert not evidence.closed and result.status == "unavailable" and len(result.matches) == 1


def test_duplicate_ids_and_keys_preserve_multiplicity():
    rows = material()["task_evidence"]["initial"]["gmail"]["messages"]
    duplicate = capture_population(material(rows * 2), spec())
    assert duplicate.status == "unavailable" and len(duplicate.rows) == 2
    different = copy.deepcopy(rows[0])
    different["id"] = "native-2"
    evidence = capture_population(material([rows[0], different]), spec())
    assert evidence.closed
    result = lookup_population(evidence, {"Email": "person@example.com"})
    assert result.status == "ambiguous" and len(result.matches) == 2


def test_missing_keys_and_unrelated_required_fields_are_scoped():
    rows = material()["task_evidence"]["initial"]["gmail"]["messages"]
    no_key = capture_population(material([*rows, {"id": "other", "subject": "Other"}]), spec())
    result = lookup_population(no_key, {"Email": "person@example.com"})
    assert result.status == "unavailable" and len(result.matches) == len(result.unresolved_rows) == 1
    no_subject = capture_population(material([*rows, {"id": "other", "from_": "other"}]), spec())
    assert lookup_population(no_subject, {"Email": "person@example.com"}).status == "matched"
    assert lookup_population(no_subject, {"Email": "other"}).status == "unavailable"


@pytest.mark.parametrize("value", [None, "", False, 1, 1.0])
def test_null_empty_bool_and_numeric_key_types_are_not_coerced(value):
    evidence = capture_population(material([{"id": "one", "from_": value, "subject": "Exact"}]), spec())
    result = lookup_population(evidence, {"Email": value})
    assert result.status == ("unavailable" if value is None or type(value) is bool else "matched")
    assert lookup_population(evidence, {"Email": "1"}).status != "matched"


@pytest.mark.parametrize("changes", [
    {"path": ["task_evidence", "final", "gmail", "messages"]},
    {"path": ["task_evidence", "initial", "gmail", "unregistered"]},
    {"path": ["task_evidence", "initial", "gmail", True]},
    {"fields": {"Email": ["invented"]}},
    {"fields": {"Email": ["to", 0]}},
    {"identity_path": ["subject"]},
    {"key_fields": ["Unprojected"]},
])
def test_manifest_projection_paths_are_installed_capabilities(changes):
    with pytest.raises(ValidationError):
        spec(**changes)


def test_salesforce_installed_record_fields_are_supported_without_alias_hydration():
    source = InitialCollectionSource(path=("task_evidence", "initial", "salesforce", "opportunities"),
        fields={"Name": ("name",), "Stage": ("stage_name",)}, key_fields=("Name",))
    evidence = capture_population({"task_evidence": {"initial": {"salesforce": {"opportunities": [
        {"id": "opp", "name": "Deal", "stage": "Alias only"}]}}}}, source)
    assert evidence.closed and "Stage" not in json.loads(evidence.rows[0].cells_json)


@pytest.mark.parametrize("field,value", [
    ("closed", 1), ("source_digest", "x"), ("selector_digest", "0" * 64),
    ("schema_digest", "0" * 64),
])
def test_retained_population_metadata_is_strict(field, value):
    data = capture_population(material(), spec()).model_dump(mode="json")
    data[field] = value
    with pytest.raises(ValidationError):
        PopulationEvidence.model_validate(data)


def test_retained_projection_cannot_lie_about_raw_cells_or_identity():
    evidence = capture_population(material(), spec())
    for field, value in [("cells_json", canonical_json({"Email": "invented"})),
                         ("key_json", canonical_json([["str", "invented"]])),
                         ("identity", ["initial.records@1", "wrong", "str", "native-1"]),
                         ("missing_fields", ["Subject"])]:
        data = evidence.model_dump(mode="json")
        data["rows"][0][field] = value
        with pytest.raises(ValidationError):
            PopulationEvidence.model_validate(data)
    forged = evidence.model_copy(update={"source_digest": "0" * 64})
    with pytest.raises(ValueError):
        validate_population_evidence(forged, material())


def test_existing_sheet_population_uses_same_structural_exact_lookup():
    source = TableSource(path=("task_evidence", "initial", "google_sheets"),
        spreadsheet_id="sheet", worksheet_id="tab", key_fields=("Email",))
    evidence = capture_table({"task_evidence": {"initial": {"google_sheets": {
        "worksheets": [{"spreadsheet_id": "sheet", "id": "tab"}],
        "rows": [{"spreadsheet_id": "sheet", "worksheet_id": "tab", "row_id": 1,
                  "cells": {"Email": "person"}}]}}}}, source)
    assert lookup_population(evidence, {"Email": "person"}).status == "matched"


@pytest.mark.parametrize("field", ["source_path", "closed", "enumerated"])
def test_model_copy_boolean_integer_equality_cannot_authenticate_receipts(field):
    raw = material([{"id": "one", "from_": "one", "subject": "Exact"},
                    {"id": "two", "from_": "two", "subject": "Exact"}])
    evidence = capture_population(raw, spec())
    if field == "source_path":
        second = evidence.rows[1].model_copy(update={"source_path": (*spec().path, True)})
        forged = evidence.model_copy(update={"rows": (evidence.rows[0], second)})
    else:
        forged = evidence.model_copy(update={field: 1})
    with pytest.raises(ValidationError):
        validate_population_evidence(forged, raw)


def test_sha_bound_selected_luna_initial_messages_are_real_population():
    index = Path("/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate/cross-category-selection.json")
    if not index.exists():
        pytest.skip("selected development sources unavailable")
    selected = next(item for item in json.loads(index.read_text())["tasks"]
                    if item["task_name"] == "simple.email_airtable_customer_welcome")
    raw = Path(selected["source_episode_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == selected["source_episode_sha256"]
    initial = json.loads(raw)["task"]["data"]["initial_state"]
    data = {"task_evidence": {"initial": initial}}
    evidence = capture_population(data, spec())
    assert evidence.closed and len(evidence.rows) == len(initial["gmail"]["messages"]) > 0
    assert [row.identity[-1] for row in evidence.rows] == [row["id"] for row in initial["gmail"]["messages"]]
    validate_population_evidence(PopulationEvidence.model_validate_json(evidence.model_dump_json()), data)


def test_frozen_public_contact_collection_uses_installed_schema_without_hydration():
    pack = Path('/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/manifest-authoring-105/batch-08.json')
    if not pack.exists():
        pytest.skip('local immutable public authoring pack unavailable')
    entry = next(item for item in json.loads(pack.read_text())['tasks']
        if item['task_name'] == 'simple.email_sf_contact_assistant_update')
    public = entry['public_input']
    assert hashlib.sha256(canonical_json(public).encode()).hexdigest() == entry['public_input_sha256']
    source = InitialCollectionSource(path=('task_evidence', 'initial', 'salesforce', 'contacts'),
        fields={'NativeID': ('id',)}, key_fields=('NativeID',))
    raw = {'task_evidence': {'initial': public['initial_state']}}
    original = copy.deepcopy(raw)
    evidence = capture_population(raw, source)
    actual = public['initial_state']['salesforce']['contacts']
    assert evidence.closed and len(evidence.rows) == len(actual) > 0
    assert [item.identity[-1] for item in evidence.rows] == [item['id'] for item in actual]
    validate_population_evidence(PopulationEvidence.model_validate_json(evidence.model_dump_json()), raw)
    assert raw == original
