import json

from test_notification_evidence import run_operations, zapier

from automationbench.tools.zapier.asana.actions import asana_add_task_to_section, asana_create_task
from automationbench_v1.asana_evidence import asana_effects
from automationbench_v1.effect_evidence import world_transitions
from automationbench_v1.effect_index import EffectIndex


def task_and_section(*, notes="Email: a@example.com\nDepartment: Engineering", section="sec_prov"):
    create_args = {
        "workspace": "ws_it",
        "project": "proj_access",
        "name": "Provision request",
        "notes": notes,
    }
    section_args = {
        "task_id": "",
        "workspace": "ws_it",
        "projects": "proj_access",
        "section": section,
    }

    def create(world):
        result = asana_create_task(world, **create_args)
        section_args["task_id"] = json.loads(result)["results"][0]["id"]
        return result

    return [
        zapier("asana_create_task", create_args, create),
        zapier(
            "asana_add_task_to_section",
            section_args,
            lambda world: asana_add_task_to_section(world, **section_args),
        ),
    ]


def test_acknowledged_creation_and_section_have_distinct_record_and_task_identity():
    source = run_operations({}, task_and_section())
    effects = asana_effects(EffectIndex(world_transitions(source)))
    assert len(effects) == 2 and all(effect.status == "qualified" for effect in effects)
    assert effects[0].record_id == effects[1].params["task_id"]
    assert effects[0].record_id != effects[1].record_id


def test_missing_receipt_never_becomes_qualified_action_record():
    source = run_operations({}, task_and_section())
    source["state_write_receipts"] = source["state_write_receipts"][:1]
    effects = asana_effects(EffectIndex(world_transitions(source)))
    assert effects[0].status == "qualified"
    assert effects[1].status == "unavailable"
