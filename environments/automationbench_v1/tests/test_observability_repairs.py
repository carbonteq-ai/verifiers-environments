"""Opt-in access repairs use real native tools and never change rubric answers."""

import json

import pytest

from automationbench_v1.limited_tools import (
    AutomationBenchLimitedToolset,
    AutomationBenchLimitedToolsetConfig,
    selected_tool_definitions,
)
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState


def load(names, additions=None, clock=False):
    return AutomationBenchTaskset(
        AutomationBenchConfig(
            domains=["finance", "simple"],
            task_names=names,
            task=AutomationBenchTaskConfig(
                toolset="limited_zapier", world_time_context_if_declared=clock
            ),
            additional_tools_by_task=additions or {},
        )
    ).load()


def toolset(task):
    tools = AutomationBenchLimitedToolset(
        AutomationBenchLimitedToolsetConfig(allowed_tools=task.data.zapier_tools)
    )
    tools._inert_state = AutomationBenchState(
        world=task.data.initial_state, initial_state=task.data.initial_state
    )
    return tools


def test_mixed_clock_context_preserves_timeless_tasks_and_existing_strict_mode():
    names = ["finance.prepaid_amortization", "simple.sf_lead_status_qualified"]
    original = {t.key: t for t in load(names)}
    repaired = {t.key: t for t in load(names, clock=True)}
    for key, task in repaired.items():
        before = original[key]
        after_data = task.data.model_dump(mode="json")
        before_data = before.data.model_dump(mode="json")
        assert task.data.assertions == before.data.assertions
        assert task.data.initial_state == before.data.initial_state
        assert after_data["prompt"][1:] == before_data["prompt"][1:]
        if key.startswith("finance"):
            assert "2026-02-01T10:00:00Z" in after_data["prompt"][0]["content"]
            assert task.hash != before.hash
        else:
            assert task.data.prompt == before.data.prompt
            assert task.hash == before.hash
    with pytest.raises(ValueError, match="explicit ISO datetime"):
        AutomationBenchTaskset(
            AutomationBenchConfig(
                domains=["simple"],
                task_names=[names[1]],
                task=AutomationBenchTaskConfig(world_time_context=True),
            )
        ).load()


def test_tax_exemption_is_retrievable_only_after_explicit_reader_addition():
    name = "finance.sales_tax_remittance"
    [original] = load([name])
    [repaired] = load([name], {name: ("gmail_find_email", "gmail_get_email_by_id")})
    assert repaired.data.initial_state == original.data.initial_state
    assert repaired.data.assertions == original.data.assertions
    with pytest.raises(ValueError, match="not enabled"):
        toolset(original).invoke("gmail_find_email", query="exemption")
    result = json.loads(toolset(repaired).invoke("gmail_find_email", query="exemption"))
    assert result["result_count"] == 1
    assert result["messages"][0]["id"] == "msg_exempt_notice"
    assert "$30,000" in result["messages"][0]["body_plain"]
    assert "$45,000" in result["messages"][0]["body_plain"]
    selected_tool_definitions(repaired.data.zapier_tools)


def test_prepaid_channel_discovery_reaches_existing_correction_without_guessing_id():
    name = "finance.prepaid_amortization"
    [task] = load([name], {name: ("slack_list_channels",)})
    tools = toolset(task)
    channels = json.loads(tools.invoke("slack_list_channels"))
    assert "accounting" in json.dumps(channels)
    assert "C_ACCT" in json.dumps(channels)
    # Use the discovered ID, not one leaked through a privileged prompt.
    messages = tools.invoke("slack_get_channel_messages", channel="C_ACCT")
    assert "Correction on the Software License" in messages
    assert "7,200" in messages


def test_additional_tool_selection_is_deduplicated_and_rejects_typos():
    name = "finance.sales_tax_remittance"
    [task] = load([name], {name: ("gmail_send_email", "gmail_find_email")})
    assert task.data.zapier_tools.count("gmail_send_email") == 1
    with pytest.raises(ValueError, match="unknown AutomationBench tool"):
        load([name], {name: ("gmail_nonexistent",)})
    with pytest.raises(ValueError, match="unselected tasks"):
        load([name], {"finance.typo": ("gmail_find_email",)})
