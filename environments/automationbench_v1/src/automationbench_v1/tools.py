"""Task-scoped v1 MCP tools backed by AutomationBench's simulated world."""

from __future__ import annotations

import inspect
import json
from typing import Any, cast, get_type_hints

import verifiers.v1 as vf
from pydantic import ConfigDict, Field, create_model

from automationbench.schema.world import WorldState
from automationbench.tools import ALL_TOOLS
from automationbench.tools.zapier.meta import ToolRegistry


class _PortableToolRegistry(ToolRegistry):
    """AutomationBench registry without its optional OpenAI Agents dependency.

    The benchmark uses OpenAI Agents only to derive JSON Schema. Verifiers
    already runs on MCP 2, which cannot coexist with that package's MCP <2
    constraint, so derive the same visible callable schema with Pydantic.
    """

    @staticmethod
    def _get_parameter_schema(func: Any) -> dict[str, Any]:
        signature = inspect.signature(func)
        hints = get_type_hints(func)
        fields: dict[str, tuple[Any, Any]] = {}
        for name, parameter in signature.parameters.items():
            if name == "world":
                continue
            default = ... if parameter.default is inspect.Parameter.empty else parameter.default
            fields[name] = (hints.get(name, Any), default)
        arguments = create_model(
            f"{func.__name__}_arguments",
            __config__=ConfigDict(extra="forbid"),
            **cast(Any, fields),
        )
        schema = arguments.model_json_schema()
        schema.pop("$defs", None)
        return schema


_REGISTRY: _PortableToolRegistry | None = None


def _registry() -> _PortableToolRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _PortableToolRegistry(list(ALL_TOOLS))
    return _REGISTRY


class AutomationBenchState(vf.State):
    world: dict[str, object] = Field(default_factory=dict)
    initial_state: dict[str, object] = Field(default_factory=dict)
    assertions: tuple[dict[str, object], ...] = ()
    search_top_k: int = 20


class AutomationBenchToolset(vf.Toolset[vf.ToolsetConfig, AutomationBenchState]):
    """AutomationBench's canonical Zapier meta-tool interface."""

    TOOL_PREFIX = None

    @vf.tool
    def search_tools(self, query: str, top_k: int = 5) -> str:
        """Find Zapier-style tools by service name, action, or description."""

        bounded = max(1, min(top_k, self.state.search_top_k))
        return json.dumps(_registry().bm25(query, top_k=bounded), indent=2)

    @vf.tool
    def execute_tool(self, tool_name: str, arguments: str) -> str:
        """Execute a tool found by ``search_tools`` against this rollout's world."""

        world = WorldState.model_validate(self.state.world)
        result = _registry().execute(tool_name, arguments, world=world)
        self.state.world = world.model_dump(mode="json")
        return result


if __name__ == "__main__":
    AutomationBenchToolset.run()


__all__ = ["AutomationBenchState", "AutomationBenchToolset"]
