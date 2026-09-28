from __future__ import annotations

import json
from typing import cast

from automationbench.schema.world import WorldState
from automationbench_v1.limited_tools import AutomationBenchLimitedToolset
from automationbench_v1.scoring import score_world
from automationbench_v1.taskset import (
    AutomationBenchConfig,
    AutomationBenchTaskConfig,
    AutomationBenchTaskset,
)
from automationbench_v1.tools import AutomationBenchState
from automationbench_v1.world_codec import PRIVATE_KEY, dump_world, load_world

TASK = "support.gorgias_refund_processing"


def _task():
    tasks = AutomationBenchTaskset(
        AutomationBenchConfig(
            domains=["support"], task=AutomationBenchTaskConfig(toolset="limited_zapier")
        )
    ).load()
    return next(task for task in tasks if task.data.task_name == TASK)


def test_updated_rows_survive_the_json_round_trip() -> None:
    world = WorldState.model_validate(_task().data.initial_state)
    object.__setattr__(world.google_sheets, "_updated_row_keys", {"ss:ws:3"})
    data = dump_world(world)
    assert data[PRIVATE_KEY] == {"google_sheets_updated_row_keys": ["ss:ws:3"]}
    json.dumps(data)  # still plain JSON
    assert getattr(load_world(data).google_sheets, "_updated_row_keys") == {"ss:ws:3"}


def test_a_world_without_updates_dumps_as_before() -> None:
    world = WorldState.model_validate(_task().data.initial_state)
    assert dump_world(world) == world.model_dump(mode="json")


def test_row_update_through_the_toolset_reaches_the_scorer() -> None:
    # Each tool call rebuilds the world from JSON; before the codec, the private
    # updated-row record was dropped, so row_not_updated always passed and a
    # row_updated check without cell text could never pass.
    task = _task()
    [toolset] = task.toolsets(AutomationBenchTaskConfig.model_validate(task.config.model_dump()))
    toolset = cast(AutomationBenchLimitedToolset, toolset)
    object.__setattr__(toolset.config, "allowed_tools", ("google_sheets_update_row",))
    world = WorldState.model_validate(task.data.initial_state)
    [row] = [
        r
        for r in world.google_sheets.rows
        if r.worksheet_id == "ws_orders" and r.cells.get("Order Number") == "4501"
    ]
    toolset._inert_state = AutomationBenchState(
        world=dump_world(world), initial_state=task.data.initial_state
    )
    result = json.loads(
        toolset.invoke(
            "google_sheets_update_row",
            spreadsheet="ss_refund_policy",
            worksheet="ws_orders",
            row=str(row.row_id),
            cells=json.dumps({"Status": "Refunded"}),
        )
    )
    assert result.get("success") is True, result

    check = {
        "type": "google_sheets_row_not_updated",
        "spreadsheet_id": "ss_refund_policy",
        "worksheet_id": "ws_orders",
        "row_id": row.row_id,
    }
    snapshot = score_world(
        world=toolset.state.world, initial_state=task.data.initial_state, assertions=(check,)
    )
    [outcome] = [r for r in snapshot.assertion_results if r.get("type") == check["type"]]
    assert outcome["passed"] is False  # the update is seen, so "not updated" fails
