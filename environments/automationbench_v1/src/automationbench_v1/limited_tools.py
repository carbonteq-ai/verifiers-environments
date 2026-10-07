"""AutomationBench's task-filtered concrete Zapier tool mode."""

from __future__ import annotations

import functools
import inspect
import json
import re
import types
from collections.abc import Callable
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

import verifiers.v1 as vf
from pydantic import ConfigDict, create_model

from automationbench.tools import ALL_TOOLS

from .capture import capture_action, capture_rejection
from .simulation import simulated_tool_call
from .tools import AutomationBenchState
from .world_codec import dump_world, load_world

_ZAPIER_TOOLS = {tool.__name__: tool for tool in ALL_TOOLS}

_TOOL_CONTRACTS: dict[str, dict[str, Any]] = {
    "asana_create_task": {
        "input_aliases": {
            "due_date": {
                "canonical": "dueDate",
                "fallback_aliases": ["due_on"],
                "precedence": "dueDate is used when both fields are supplied",
            },
            "description": {
                "canonical": "notes",
                "fallback_aliases": ["description"],
                "precedence": "notes is used when both fields are supplied",
            },
        },
        "result_semantics": {
            "authoritative_applied_fields": [
                "results[].workspace",
                "results[].dueType",
                "results[].dueDate",
                "results[].name",
                "results[].notes",
                "results[].completed",
                "results[].liked",
                "results[].assignee",
                "results[].followers",
                "results[].tags",
                "results[].custom_field_info",
                "results[].project",
            ],
            "legacy_template_fields": [
                "results[].due_on",
                "results[].due_at",
                "results[].projects",
                "results[].memberships",
            ],
            "precedence": (
                "The scalar fields copied from the recorded action are the applied simulated-world state. "
                "Legacy template fields are non-authoritative examples and must not override them."
            ),
        },
    }
}


def enrich_tool_definitions(definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach executable alias and result semantics to judge-visible tools."""

    enriched: list[dict[str, Any]] = []
    for definition in definitions:
        copied = {**definition, "function": dict(definition.get("function", {}))}
        function = copied["function"]
        name = function.get("name")
        contract = _TOOL_CONTRACTS.get(name)
        if contract is not None:
            function["x-automationbench-contract"] = contract
            parameters = function.get("parameters")
            if isinstance(parameters, dict):
                parameters = {**parameters, "properties": dict(parameters.get("properties", {}))}
                function["parameters"] = parameters
                properties = parameters["properties"]
                for family, alias_contract in contract["input_aliases"].items():
                    canonical = alias_contract["canonical"]
                    aliases = alias_contract["fallback_aliases"]
                    if canonical in properties:
                        properties[canonical] = {
                            **properties[canonical],
                            "description": (
                                f"Canonical {family}; {alias_contract['precedence']}. "
                                f"Compatibility aliases: {', '.join(aliases)}."
                            ),
                        }
                    for alias in aliases:
                        if alias in properties:
                            properties[alias] = {
                                **properties[alias],
                                "description": (
                                    f"Compatibility alias for {canonical}; used only when {canonical} is omitted."
                                ),
                            }
        enriched.append(copied)
    return enriched


# FastMCP decodes a JSON-looking string argument into an object unless the
# parameter is declared exactly ``str``. A tool that takes ``fields_json: str |
# None`` then rejects the object the model never sent. Such parameters accept
# the decoded object at the MCP boundary and get a string back before the tool
# runs; the schema shown to the model still says string. Parameters documented
# as JSON get the JSON text back. The others are comma-separated lists
# (``tags``, ``label_ids``, ``keywords``): a list becomes "a,b", and an empty
# list means the argument was not given.
_DECODED = str | dict[str, Any] | list[Any] | None
_ARG_LINE = re.compile(r"^\s{4,}(\w+):\s*(.*)$")


def _optional_string_parameters(func: Callable[..., Any]) -> frozenset[str]:
    names = set()
    for name, hint in get_type_hints(func).items():
        if get_origin(hint) in (Union, types.UnionType) and set(get_args(hint)) == {
            str,
            type(None),
        }:
            names.add(name)
    return frozenset(names)


def _json_string_parameters(func: Callable[..., Any]) -> frozenset[str]:
    """Parameters whose docstring or name says they take JSON text."""

    names = {name for name in _optional_string_parameters(func) if name.endswith("_json")}
    current = None
    for line in (inspect.getdoc(func) or "").splitlines():
        match = _ARG_LINE.match("    " + line) if line.startswith("    ") else None
        if match:
            current = match.group(1)
            text = match.group(2)
        elif line.strip() and not line.startswith(" "):
            current = None
            continue
        else:
            text = line
        if current and "json" in text.lower():
            names.add(current)
    return frozenset(names) & _optional_string_parameters(func)


def _string_argument(value: dict[str, Any] | list[Any], as_json: bool) -> str | None:
    """The string a string parameter expects for an object MCP decoded."""

    if as_json or isinstance(value, dict) or any(isinstance(v, dict | list) for v in value):
        return json.dumps(value)
    if not value:
        return None
    return ",".join(str(item) for item in value)


def selected_tool_definitions(names: tuple[str, ...]) -> list[dict[str, Any]]:
    """Return OpenAI-style definitions for exactly the task-selected tools."""
    definitions = []
    for name in names:
        try:
            func = _ZAPIER_TOOLS[name]
        except KeyError as error:
            raise ValueError(f"unknown AutomationBench tool {name!r}") from error
        signature = inspect.signature(func)
        hints = get_type_hints(func)
        fields: dict[str, tuple[Any, Any]] = {}
        for parameter_name, parameter in signature.parameters.items():
            if parameter_name == "world":
                continue
            default = ... if parameter.default is inspect.Parameter.empty else parameter.default
            fields[parameter_name] = (hints.get(parameter_name, Any), default)
        arguments = create_model(
            f"{name}_arguments",
            __config__=ConfigDict(extra="forbid"),
            **cast(Any, fields),
        )
        definitions.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": (inspect.getdoc(func) or "").strip(),
                    "parameters": arguments.model_json_schema(),
                },
            }
        )
    return enrich_tool_definitions(definitions)


class AutomationBenchLimitedToolsetConfig(vf.ToolsetConfig):
    allowed_tools: tuple[str, ...]


def _call_arguments(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """The call as the model made it, in the form the full toolsets capture.

    Models call tools by keyword, and the tool server fills every parameter the
    model left out with its ``None`` default. A keyword call is recorded as its
    keyword arguments without those ``None`` defaults, which is also what the
    dispatch receipt carries; manifest evidence reads this form. A positional
    call keeps both parts.
    """

    if args:
        return {"args": list(args), "kwargs": dict(kwargs)}
    return {key: value for key, value in kwargs.items() if value is not None}


class AutomationBenchLimitedToolset(
    vf.Toolset[AutomationBenchLimitedToolsetConfig, AutomationBenchState]
):
    """Expose only the concrete Zapier tools selected by an AutomationBench task."""

    TOOL_PREFIX = None

    def execution_capture_enabled(self) -> bool:
        return self.state.capture_actions

    def invoke(self, tool_name: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke one configured concrete tool and persist its world mutation."""

        called = _call_arguments(args, kwargs)
        if tool_name not in self.config.allowed_tools:
            error = ValueError(f"tool {tool_name!r} is not enabled for this task")
            capture_rejection(self.state, tool_name, called, error)
            raise error
        try:
            func = _ZAPIER_TOOLS[tool_name]
        except KeyError as error:
            rejection = ValueError(f"unknown AutomationBench tool {tool_name!r}")
            capture_rejection(self.state, tool_name, called, rejection)
            raise rejection from error
        json_parameters = _json_string_parameters(func)
        for name in _optional_string_parameters(func):
            if isinstance(kwargs.get(name), dict | list):
                kwargs[name] = _string_argument(kwargs[name], name in json_parameters)
        cleaned = {
            key: value
            for key, value in kwargs.items()
            if not (isinstance(value, dict) and not value)
        }

        def execute():
            with simulated_tool_call(self.state, tool_name, called):
                world = load_world(self.state.world)
                result = func(*args, world=world, **cleaned)
                self.state.world = dump_world(world)
            return result

        return capture_action(self.state, tool_name, called, execute)

    def _tool_wrapper(self, tool_name: str, func: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(func)
        widened = _optional_string_parameters(func)
        visible = [
            parameter.replace(annotation=_DECODED) if name in widened else parameter
            for name, parameter in signature.parameters.items()
            if name != "world"
        ]

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.invoke(tool_name, *args, **kwargs)

        wrapper.__signature__ = signature.replace(parameters=visible)  # type: ignore[attr-defined]
        wrapper.__annotations__ = {
            name: (_DECODED if name in widened else value)
            for name, value in get_type_hints(func).items()
            if name != "world"
        }
        return wrapper

    def register(self, mcp: Any) -> None:
        for name in self.config.allowed_tools:
            try:
                func = _ZAPIER_TOOLS[name]
            except KeyError as error:
                raise ValueError(f"unknown AutomationBench tool {name!r}") from error
            wrapped = self._tool_wrapper(name, func)
            mcp.add_tool(
                self._with_state(wrapped),
                name=name,
                description=(inspect.getdoc(func) or "").strip() or None,
            )

    def _register(self, mcp: Any) -> None:
        """Compatibility with the previously pinned native server API."""
        self.register(mcp)


if __name__ == "__main__":
    AutomationBenchLimitedToolset.run()


__all__ = [
    "AutomationBenchLimitedToolset",
    "AutomationBenchLimitedToolsetConfig",
    "selected_tool_definitions",
]
