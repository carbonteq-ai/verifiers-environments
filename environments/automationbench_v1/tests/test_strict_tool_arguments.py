from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from automationbench_v1.limited_tools import RejectUnknownToolArguments
from automationbench_v1.taskset import AutomationBenchTask, AutomationBenchTaskConfig


def test_strict_argument_config_reaches_the_limited_toolset() -> None:
    config = AutomationBenchTaskConfig(
        toolset="limited_zapier",
        allowed_tools=("google_sheets_get_spreadsheet_by_id",),
        strict_tool_arguments=True,
    )
    [tools] = AutomationBenchTask.toolsets(config)
    assert tools.config.strict_tool_arguments is True
    server = MCPServer("strict-config")
    tools.register(server)
    assert (
        sum(isinstance(middleware, RejectUnknownToolArguments) for middleware in server.middleware)
        == 1
    )
    assert AutomationBenchTaskConfig().strict_tool_arguments is False
    with pytest.raises(ValueError, match="only for limited_zapier"):
        AutomationBenchTask.toolsets(AutomationBenchTaskConfig(strict_tool_arguments=True))


def test_real_mcp_rejects_unknown_keys_without_executing_and_accepts_corrected_call() -> None:
    async def scenario(strict: bool) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        server = MCPServer("strict-native-boundary")

        def read(spreadsheet_id: str, includeGridData: bool = False) -> dict[str, Any]:
            value = {"spreadsheet_id": spreadsheet_id, "includeGridData": includeGridData}
            calls.append(value)
            return value

        server.add_tool(read, name="read")
        if strict:
            server.middleware.append(
                RejectUnknownToolArguments(
                    {"read": frozenset({"spreadsheet_id", "includeGridData"})}
                )
            )
        app = server.streamable_http_app(json_response=True, stateless_http=True)
        async with server.session_manager.run():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
            ) as client:

                async def call(identity: int, arguments: dict[str, Any]) -> dict[str, Any]:
                    response = await client.post(
                        "/mcp",
                        json={
                            "jsonrpc": "2.0",
                            "id": identity,
                            "method": "tools/call",
                            "params": {"name": "read", "arguments": arguments},
                        },
                        headers={
                            "Accept": "application/json, text/event-stream",
                            "MCP-Protocol-Version": "2025-06-18",
                        },
                    )
                    response.raise_for_status()
                    return response.json()

                rejected = await call(
                    1, {"spreadsheet_id": "private-sheet-value", "include_grid_data": "True"}
                )
                if strict:
                    assert calls == []
                corrected = await call(
                    2, {"spreadsheet_id": "private-sheet-value", "includeGridData": True}
                )
                return calls, rejected, corrected

    calls, rejected, corrected = asyncio.run(scenario(True))
    assert rejected["result"]["isError"] is True
    text = rejected["result"]["content"][0]["text"]
    assert "include_grid_data" in text and "No action was executed" in text
    assert "private-sheet-value" not in text
    assert not corrected["result"].get("isError", False)
    assert calls == [{"spreadsheet_id": "private-sheet-value", "includeGridData": True}]
    legacy_calls, legacy_result, _ = asyncio.run(scenario(False))
    assert not legacy_result["result"].get("isError", False)
    assert legacy_calls[0]["includeGridData"] is False  # Recorded original defect.
