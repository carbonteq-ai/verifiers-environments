"""Whether a captured tool action is the call a native dispatch receipt records.

The dispatch receipt carries the arguments the model sent. The tool server binds
every parameter the model left out to its default before the tool runs, so the
captured action can name extra parameters at their defaults (``None`` or not), and
a model may also send a parameter at its default value explicitly. Two argument
sets denote the same call when they agree once both are bound to the tool's
signature defaults; parameters bound to ``None`` carry no value and are dropped.
Tools outside the benchmark's concrete tool list are compared exactly.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from functools import cache
from typing import Any

from ..capture import canonical_json


@cache
def _defaults(tool_name: str) -> Mapping[str, Any] | None:
    from automationbench.tools import ALL_TOOLS

    for tool in ALL_TOOLS:
        if tool.__name__ == tool_name:
            return {
                name: parameter.default
                for name, parameter in inspect.signature(tool).parameters.items()
                if name != "world" and parameter.default is not inspect.Parameter.empty
            }
    return None


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def bound_call(tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Keyword arguments bound to the tool's defaults, without parameters bound to None."""

    defaults = _defaults(tool_name)
    merged = dict(arguments) if defaults is None else {**defaults, **arguments}
    return {key: _plain(value) for key, value in merged.items() if value is not None}


def same_call(tool_name: str, dispatched: Any, captured: Any) -> bool:
    """Whether dispatched and captured keyword arguments denote one call of ``tool_name``."""

    if not isinstance(dispatched, Mapping) or not isinstance(captured, Mapping):
        return False
    if _defaults(tool_name) is None:
        return canonical_json(_plain(dispatched)) == canonical_json(_plain(captured))
    return canonical_json(bound_call(tool_name, dispatched)) == canonical_json(bound_call(tool_name, captured))


__all__ = ["bound_call", "same_call"]
