from __future__ import annotations

import json
from typing import cast

import pytest
from mcp.server.mcpserver.utilities.func_metadata import func_metadata

from automationbench.schema.world import WorldState
from automationbench_v1 import limited_tools
from automationbench_v1.limited_tools import AutomationBenchLimitedToolset
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tool_mistakes import (
    EMPTY_RESULT,
    INVALID_ARGUMENTS,
    MISSING_ARGUMENTS,
    OTHER_FAILURE,
    UNKNOWN_ID,
    UNKNOWN_TOOL,
    AutomationBenchMistakePenaltyConfig,
    classify_tool_result,
    is_mistake,
)
from automationbench_v1.tools import AutomationBenchState

# Error texts as they appeared in LFM2.5-2.6B VORTEX training traces.
OBSERVED = [
    (
        "reamaze_create_conversation",
        (
            "Error executing tool reamaze_create_conversation: 1 validation error for "
            "reamaze_create_conversationArguments\ntags\n  Input should be a valid string "
            "[type=string_type, input_value=['migration'], input_type=list]"
        ),
        INVALID_ARGUMENTS,
    ),
    (
        "calendly_book_meeting",
        (
            "Error executing tool calendly_book_meeting: 4 validation errors for "
            "calendly_book_meetingArguments\nevent_type\n  Field required [type=missing, "
            "input_value={}, input_type=dict]"
        ),
        MISSING_ARGUMENTS,
    ),
    (
        "google_sheets_get_worksheet",
        "error: unknown tool 'google_sheets_get_worksheet'",
        UNKNOWN_TOOL,
    ),
    (
        "gmail_get_email_by_id",
        json.dumps({"success": False, "error": "Message with id '4b91ab27' not found"}),
        UNKNOWN_ID,
    ),
    (
        "zoom_find_meeting",
        json.dumps({"success": False, "error": "No matching meeting found"}),
        EMPTY_RESULT,
    ),
    (
        "salesforce_contact_find",
        json.dumps({"success": False, "error": "Contact not found"}),
        EMPTY_RESULT,
    ),
    (
        "gmail_send_email",
        json.dumps({"success": False, "error": "Daily send quota exceeded"}),
        OTHER_FAILURE,
    ),
    ("gmail_send_email", json.dumps({"success": True, "id": "m1"}), None),
    ("google_sheets_get_rows", "31 rows", None),
]


@pytest.mark.parametrize(("tool", "content", "kind"), OBSERVED)
def test_observed_tool_results_classify_by_what_the_model_controls(tool, content, kind) -> None:
    assert classify_tool_result(tool, content) == kind
    assert is_mistake(kind) == (
        kind in {INVALID_ARGUMENTS, MISSING_ARGUMENTS, UNKNOWN_TOOL, UNKNOWN_ID}
    )


def test_mistake_penalty_is_small_and_capped() -> None:
    config = AutomationBenchMistakePenaltyConfig(per_mistake=0.02, cap=0.1)
    assert [config.penalty(count) for count in (0, 1, 3, 5, 12)] == pytest.approx(
        [0.0, 0.02, 0.06, 0.1, 0.1]
    )


def test_json_string_arguments_reach_the_tool_as_strings_after_mcp_decoding(monkeypatch) -> None:
    # MCP decodes a JSON-looking string unless the parameter is exactly ``str``;
    # ``fields_json: str | None`` then failed validation although the model sent
    # the string the tool asks for.
    seen: dict[str, object] = {}

    def create_record(
        world: WorldState, applicationId: str, tableName: str, fields_json: str | None = None
    ) -> str:
        del world
        seen.update(applicationId=applicationId, tableName=tableName, fields_json=fields_json)
        return json.dumps({"success": True})

    monkeypatch.setitem(limited_tools._ZAPIER_TOOLS, "airtable_create_record", create_record)
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
    object.__setattr__(toolset.config, "allowed_tools", ("airtable_create_record",))
    toolset._inert_state = AutomationBenchState(
        world=task.data.initial_state, initial_state=task.data.initial_state
    )

    wrapper = toolset._tool_wrapper("airtable_create_record", create_record)
    metadata = func_metadata(wrapper)
    sent = {
        "applicationId": "base_crm",
        "tableName": "Leads",
        "fields_json": '{"Name": "Sara Chen"}',
    }
    decoded = metadata.pre_parse_json(sent)
    assert decoded["fields_json"] == {"Name": "Sara Chen"}  # what MCP hands on
    metadata.arg_model.model_validate(decoded)  # accepted instead of rejected

    toolset.invoke("airtable_create_record", **decoded)
    assert isinstance(seen["fields_json"], str) and json.loads(cast(str, seen["fields_json"])) == {
        "Name": "Sara Chen"
    }
