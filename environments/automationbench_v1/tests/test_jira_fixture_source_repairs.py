"""Revised fixture bindings admit real persisted Jira operations, not fake logs."""

import copy
import json

import pytest

from automationbench_v1.contracts.engine import binding_reason
from automationbench_v1.contracts.loader import load_task_contract
from automationbench_v1.limited_tools import AutomationBenchLimitedToolset, AutomationBenchLimitedToolsetConfig
from automationbench_v1.taskset import AutomationBenchConfig, AutomationBenchTaskConfig, AutomationBenchTaskset
from automationbench_v1.tools import AutomationBenchState
from automationbench_v1.world_codec import dump_world, load_world


@pytest.mark.parametrize("name,project", [
    ("operations.chemical_inventory_safety_audit", "SAFETY"),
    ("operations.fire_suppression_testing", "FIRE"),
    ("operations.twilio_afterhours_incident", "Incident Management"),
    ("simple.api_key_jira_slack", "INFRA"),
    ("simple.email_jira_bug_slack", "PLAT"),
    ("simple.jira_auth_improvements", "PROD"),
    ("support.hiver_escalation_patterns", "Support Issues"),
])
def test_native_project_creation_and_revised_source_bindings(name, project):
    [task] = AutomationBenchTaskset(AutomationBenchConfig(domains=[name.split(".")[0]], task_names=[name],
        task=AutomationBenchTaskConfig(toolset="limited_zapier", strict_tool_arguments=True))).load()
    data = task.data.model_dump(mode="json")
    initial = copy.deepcopy(data["initial_state"])
    world = dump_world(load_world(initial))
    assert binding_reason({"task_evidence": {"initial": initial, "prompt": data["prompt"]}}, load_task_contract(name)) is None
    tools = AutomationBenchLimitedToolset(AutomationBenchLimitedToolsetConfig(allowed_tools=task.data.zapier_tools,
                                                                          strict_tool_arguments=True))
    tools._inert_state = AutomationBenchState(world=world, initial_state=copy.deepcopy(initial), capture_actions=True)
    made = json.loads(tools.invoke("jira_create_issue", project=project, summary="Native fixture proof", issuetype="Task"))
    assert made["success"] is True
    assert len(tools._inert_state.world["jira"]["issues"]) == 1
    blocked = json.loads(tools.invoke("jira_create_issue", project="UNSEEDED_UNKNOWN", summary="No mutation", issuetype="Task"))
    assert blocked["success"] is False and blocked["error"] == "jira_project_not_found"
    assert len(tools._inert_state.world["jira"]["issues"]) == 1
