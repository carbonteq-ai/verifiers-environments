from __future__ import annotations

import json
from typing import cast

import pytest

from automationbench.schema.world import WorldState
from automationbench_v1 import limited_tools
from automationbench_v1.limited_tools import (
    AutomationBenchLimitedToolset,
    _json_string_parameters,
)
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState


def tag_ticket(
    world: WorldState,
    ticket_id: str,
    tags: str | None = None,
    label_ids: str | None = None,
    fields_json: str | None = None,
    extra: str | None = None,
) -> str:
    """Tag a ticket.

    Args:
        ticket_id: Ticket to change.
        tags: Comma-separated list of tags.
        label_ids: Comma-separated label ids.
        fields_json: Field values as a JSON string.
        extra: Extra values, a JSON object.
    """
    del world
    return json.dumps(
        {"tags": tags, "label_ids": label_ids, "fields_json": fields_json, "extra": extra}
    )


@pytest.fixture
def toolset(monkeypatch) -> AutomationBenchLimitedToolset:
    monkeypatch.setitem(limited_tools._ZAPIER_TOOLS, "tag_ticket", tag_ticket)
    task = next(
        iter(
            AutomationBenchTaskset(
                AutomationBenchConfig(
                    domains=["simple"], task=AutomationBenchTaskConfig(toolset="limited_zapier")
                )
            ).load()
        )
    )
    [toolset] = task.toolsets(AutomationBenchTaskConfig.model_validate(task.config.model_dump()))
    toolset = cast(AutomationBenchLimitedToolset, toolset)
    object.__setattr__(toolset.config, "allowed_tools", ("tag_ticket",))
    toolset._inert_state = AutomationBenchState(
        world=task.data.initial_state, initial_state=task.data.initial_state
    )
    return toolset


def test_json_parameters_are_read_from_names_and_docstrings() -> None:
    assert _json_string_parameters(tag_ticket) == {"fields_json", "extra"}
    helpscout = limited_tools._ZAPIER_TOOLS["helpscout_create_conversation"]
    assert "tags" in _json_string_parameters(helpscout)  # "or JSON array string"
    gorgias = limited_tools._ZAPIER_TOOLS["gorgias_update_ticket"]
    assert "tags" not in _json_string_parameters(gorgias)


def test_decoded_lists_reach_comma_separated_parameters_as_lists(toolset) -> None:
    # 0.4.3 re-encoded every decoded list as JSON, so tags=["coaching","agent_b"]
    # were saved as the tags '["coaching"' and '"agent_b"]', and label_ids=[] as a
    # label named "[]".
    result = json.loads(
        toolset.invoke(
            "tag_ticket",
            ticket_id="t1",
            tags=["coaching", "agent_b"],
            label_ids=[],
            fields_json={"Name": "Sara Chen"},
            extra=["a", "b"],
        )
    )
    assert result["tags"] == "coaching,agent_b"
    assert result["label_ids"] is None
    assert json.loads(result["fields_json"]) == {"Name": "Sara Chen"}
    assert json.loads(result["extra"]) == ["a", "b"]


def test_plain_strings_pass_through(toolset) -> None:
    result = json.loads(toolset.invoke("tag_ticket", ticket_id="t1", tags="vip, refund"))
    assert result["tags"] == "vip, refund"
