"""Public request evidence only; these tests do not qualify Jira or whole tasks."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from automationbench_v1.capture import canonical_json
from automationbench_v1.contracts.models import SourceBinding
from automationbench_v1.contracts.populations import lookup_population
from automationbench_v1.contracts.requests import (
    RequestPopulationEvidence,
    RequestSource,
    capture_request_population,
    validate_request_population,
)

PROMPT = ("task_evidence", "prompt")
PARAMS = ("task_evidence", "initial", "asana", "actions", "find_section", 0, "params")


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def raw():
    return {"task_evidence": {"prompt": [{"role": "user", "content": "Create exact task in Sprint 8."}],
        "initial": {"asana": {"actions": {"find_section": [{"id": "lookup-record", "params": {
            "section": "sec_sprint8", "name": "Sprint 8", "project": "proj_eng"}}]}}}}}


def bindings(material):
    return (SourceBinding(path=PROMPT, canonical_sha256=digest(material["task_evidence"]["prompt"])),
            SourceBinding(path=PARAMS, canonical_sha256=digest(
                material["task_evidence"]["initial"]["asana"]["actions"]["find_section"][0]["params"])))


def spec(**changes):
    return RequestSource.model_validate({"member_key": "requested-task", "fields": {
        "name": {"value": "Exact task", "authority_paths": [[*PROMPT, 0, "content"]]},
        "section": {"copy_from": [*PARAMS, "section"], "authority_paths": [list(PARAMS)]}}, **changes})


def test_literal_and_public_projection_are_one_immutable_authored_member():
    material = raw()
    evidence = capture_request_population(material, spec(), bindings(material))
    assert evidence.closed and evidence.enumerated and len(evidence.rows) == 1
    row = evidence.rows[0]
    assert json.loads(row.cells_json) == {"request_key": "requested-task", "name": "Exact task", "section": "sec_sprint8"}
    assert row.identity == ("public.request@1", evidence.selector_digest, "authored", "requested-task")
    assert lookup_population(evidence, {"request_key": "requested-task"}).status == "matched"
    assert json.loads(row.authority_paths_json)["name"] == [[*PROMPT, 0, "content"]]
    assert json.loads(evidence.authority_bindings_json)[0]["canonical_sha256"] == bindings(material)[0].canonical_sha256
    with pytest.raises(TypeError):
        evidence.source.fields["invented"] = evidence.source.fields["name"]


@pytest.mark.parametrize("value", ["", "1", 1, 1.5, True, False])
def test_strict_scalar_values_preserve_types_without_coercion(value):
    material = raw()
    selector = spec(fields={"value": {"value": value, "authority_paths": [list(PROMPT)]}})
    evidence = capture_request_population(material, selector, bindings(material))
    actual = json.loads(evidence.rows[0].cells_json)["value"]
    assert type(actual) is type(value) and actual == value


@pytest.mark.parametrize("mutation", ["prompt_content", "prompt_role", "source_record", "missing_prompt", "missing_record"])
def test_authority_changes_are_unavailable_with_one_known_untrusted_obligation(mutation):
    material = raw()
    authority = bindings(material)
    if mutation == "prompt_content":
        material["task_evidence"]["prompt"][0]["content"] = "Different task"
    elif mutation == "prompt_role":
        material["task_evidence"]["prompt"][0]["role"] = "system"
    elif mutation == "source_record":
        material["task_evidence"]["initial"]["asana"]["actions"]["find_section"][0]["params"]["section"] = "other"
    elif mutation == "missing_prompt":
        del material["task_evidence"]["prompt"]
    else:
        del material["task_evidence"]["initial"]
    evidence = capture_request_population(material, spec(), authority)
    assert evidence.status == "unavailable" and not evidence.closed and evidence.enumerated
    assert len(evidence.rows) == 1 and json.loads(evidence.rows[0].cells_json) == {"request_key": "requested-task"}
    assert evidence.rows[0].missing_fields == ("name", "section")
    assert lookup_population(evidence, {"request_key": "requested-task"}).status == "unavailable"


def test_every_field_requires_bound_public_authority_and_prompt_binding():
    material = raw()
    assert capture_request_population(material, spec(), ()).reason == "request_public_prompt_binding_missing"
    assert capture_request_population(material, spec(), bindings(material)[:1]).reason == "request_field_authority_unbound"
    selector = spec(fields={"name": {"value": "Exact", "authority_paths": [[*PROMPT, 7, "content"]]}})
    assert capture_request_population(material, selector, bindings(material)).reason == "request_field_authority_missing"


def test_unavailable_non_alphabetical_fields_survive_canonical_reload_and_reject_inventory_forgery():
    material = raw()
    selector = spec(fields={"zeta": {"value": "Z", "authority_paths": [list(PROMPT)]},
                            "alpha": {"value": "A", "authority_paths": [list(PROMPT)]}})
    evidence = capture_request_population(material, selector, ())
    assert evidence.rows[0].missing_fields == ("alpha", "zeta")
    restored = RequestPopulationEvidence.model_validate_json(canonical_json(evidence.model_dump(mode="json")))
    assert restored == evidence
    validate_request_population(restored, material, ())
    for missing in (("alpha",), ("alpha", "extra", "zeta")):
        forged = restored.model_dump(mode="json")
        forged["rows"][0]["missing_fields"] = missing
        with pytest.raises(ValueError, match="request_unavailable_fields_must_be_untrusted"):
            RequestPopulationEvidence.model_validate(forged)


@pytest.mark.parametrize("value", [None, [], {}, float("inf"), float("nan")])
def test_projected_non_scalar_or_nonfinite_is_not_trusted(value):
    material = raw()
    material["task_evidence"]["initial"]["asana"]["actions"]["find_section"][0]["params"]["section"] = value
    if type(value) is float:
        # Malformed non-JSON raw material cannot even receive a canonical source identity.
        with pytest.raises(ValueError):
            capture_request_population(material, spec(), ())
    else:
        evidence = capture_request_population(material, spec(), bindings(material))
        assert evidence.reason == "request_projected_scalar_unavailable" and not evidence.closed


@pytest.mark.parametrize("changes", [
    {"member_key": True}, {"member_key": ""},
    {"fields": {"request_key": {"value": "shadow", "authority_paths": [list(PROMPT)]}}},
    {"fields": {}}, {"key_fields": ["name"]},
    {"fields": {"x": {"value": None, "authority_paths": [list(PROMPT)]}}},
    {"fields": {"x": {"value": float("inf"), "authority_paths": [list(PROMPT)]}}},
    {"fields": {"x": {"value": "v", "copy_from": [*PARAMS, "section"], "authority_paths": [list(PARAMS)]}}},
    {"fields": {"x": {"value": "v", "authority_paths": [[*PROMPT, True]]}}},
    {"fields": {"x": {"value": "v", "authority_paths": [[*PROMPT, -1]]}}},
    {"fields": {"x": {"copy_from": [*PARAMS, "section"], "authority_paths": [list(PROMPT)]}}},
    {"fields": {"x": {"copy_from": [*PARAMS, True], "authority_paths": [list(PARAMS)]}}},
    {"fields": {"x": {"copy_from": ["task_evidence", "final", "id"], "authority_paths": [list(PROMPT)]}}},
    {"fields": {"x": {"value": "v", "authority_paths": [["task_evidence", "final"]]}}},
    {"fields": {"x": {"value": "v", "authority_paths": [["tool_execution_events", 0]]}}},
    {"fields": {"x": {"value": "v", "authority_paths": [["task_evidence", "assertions"]]}}},
])
def test_malformed_or_private_selectors_fail_schema_admission(changes):
    with pytest.raises(ValidationError):
        spec(**changes)


def test_reload_recomputes_against_fresh_source_and_copied_metadata_cannot_bypass():
    material = raw()
    authority = bindings(material)
    evidence = capture_request_population(material, spec(), authority)
    restored = RequestPopulationEvidence.model_validate_json(evidence.model_dump_json())
    validate_request_population(restored, material, authority)
    for changes in ({"closed": 1}, {"source_digest": "0" * 64}, {"selector_digest": "0" * 64},
                    {"binding_digest": "0" * 64}, {"enumerated": 1}):
        with pytest.raises(ValueError):
            validate_request_population(restored.model_copy(update=changes), material, authority)
    row = restored.rows[0]
    cells = json.loads(row.cells_json)
    cells["section"] = "forged"
    forged = restored.model_copy(update={"rows": (row.model_copy(update={"cells_json": canonical_json(cells)}),)})
    with pytest.raises(ValueError, match="raw_source_or_projection"):
        validate_request_population(forged, material, authority)
    changed = copy.deepcopy(material)
    changed["task_evidence"]["prompt"][0]["content"] = "Changed"
    with pytest.raises(ValueError):
        validate_request_population(restored, changed, authority)


def test_copied_boolean_path_is_rejected_before_python_bool_int_equality():
    material = raw()
    selector = spec()
    field = selector.fields["name"].model_copy(update={"authority_paths": ((*PROMPT, False, "content"),)})
    copied = selector.model_copy(update={"fields": {**selector.fields, "name": field}})
    with pytest.raises(ValidationError):
        capture_request_population(material, copied, bindings(material))


def test_parameter_variants_require_rebound_public_authority_without_python_changes():
    original = raw()
    changed = raw()
    changed["task_evidence"]["prompt"][0]["content"] = "Create Different task in Sprint 9."
    changed["task_evidence"]["initial"]["asana"]["actions"]["find_section"][0]["params"].update(
        section="sec_sprint9", name="Sprint 9", project="proj_other")
    selector = spec(fields={"name": {"value": "Different task", "authority_paths": [list(PROMPT)]},
        "section": {"copy_from": [*PARAMS, "section"], "authority_paths": [list(PARAMS)]}})
    assert not capture_request_population(changed, selector, bindings(original)).closed
    admitted = capture_request_population(changed, selector, bindings(changed))
    assert admitted.closed and json.loads(admitted.rows[0].cells_json)["section"] == "sec_sprint9"
    assert admitted.rows[0].identity[-1] == "requested-task"


def test_forged_identity_and_binding_path_cannot_pass_reload_or_recapture():
    material = raw()
    authority = bindings(material)
    evidence = capture_request_population(material, spec(), authority)
    row = evidence.rows[0].model_copy(update={"identity": (*evidence.rows[0].identity[:3], True)})
    with pytest.raises(ValueError):
        validate_request_population(evidence.model_copy(update={"rows": (row,)}), material, authority)
    binding = authority[0].model_copy(update={"path": (*PROMPT, False)})
    with pytest.raises(ValueError):
        capture_request_population(material, spec(), (binding, authority[1]))
    duplicate = (authority[0], authority[0], authority[1])
    with pytest.raises(ValueError, match="duplicate_binding"):
        capture_request_population(material, spec(), duplicate)


def test_actual_sha_bound_public_asana_request_proves_evidence_interface_only():
    path = Path("/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/manifest-authoring-105/batch-04.json")
    if not path.exists():
        pytest.skip("immutable development public pack unavailable")
    blob = path.read_bytes()
    assert hashlib.sha256(blob).hexdigest() == "08fa811e527fb7cf01213ae2f3424e9ec2dcdcb6f33618e74f4f3499aee963c8"
    public = next(task["public_input"] for task in json.loads(blob)["tasks"] if task["task_name"] == "simple.asana_sprint_section_task")
    material = {"task_evidence": {"prompt": public["prompt"], "initial": public["initial_state"]}}
    declaration = spec(fields={
        "name": {"value": "Refactor payment module", "authority_paths": [list(PROMPT)]},
        "due_date": {"value": "2026-03-14", "authority_paths": [list(PROMPT)]},
        "workspace": {"value": "ws_prod", "authority_paths": [list(PROMPT)]},
        "project": {"value": "proj_eng", "authority_paths": [list(PROMPT)]},
        "section": {"copy_from": [*PARAMS, "section"], "authority_paths": [list(PARAMS)]}})
    evidence = capture_request_population(material, declaration, bindings(material))
    assert evidence.closed and json.loads(evidence.rows[0].cells_json)["section"] == "sec_sprint8"
    assert evidence.rows[0].identity[-1] == "requested-task"
    validate_request_population(evidence, material, bindings(material))
