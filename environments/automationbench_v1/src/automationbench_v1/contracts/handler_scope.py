"""Static world-service footprint of installed simulator tool handlers.

Effect adapters may close their scope over an operation only when that
operation provably cannot touch their service. This module derives each
handler's possible footprint from the installed simulator source instead of a
hand-maintained allowlist: it follows the ``world`` parameter through the
handler and the package helpers it is passed to, and records every
``world.<service>`` field reached.

Anything not statically resolvable is unknown (``None``): ``world`` passed to
code outside ``automationbench``, aliased, used with ``getattr``/``setattr``,
or accessed through a non-field attribute. Unknown names (``api_fetch``,
forged or future tools) are also unknown. A footprint is a superset of what a
call may reach; it says nothing about what a particular call did. Service
models hold no back-reference to the world, so a service object passed onward
cannot reach another service.

The tool name comes from the authenticated native tool-server receipt; this
audit cannot authenticate caller-written handlers registered under a real name.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import textwrap
from collections.abc import Callable
from functools import cache
from types import MappingProxyType

from ..capture import canonical_json

SCOPE_REVISION = "static_world_fields@1"

# Top-level toolset operations that take no world at all.
_WORLDLESS = frozenset({"search_tools", "api_search", "base64_encode"})


def _fields() -> frozenset[str]:
    from automationbench.schema.world import WorldState

    return frozenset(WorldState.model_fields)


def _resolve(callee: ast.expr, namespace: dict) -> Callable | None:
    if isinstance(callee, ast.Name):
        target = namespace.get(callee.id)
    elif isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name):
        owner = namespace.get(callee.value.id)
        target = getattr(owner, callee.attr, None) if owner is not None else None
    else:
        return None
    if not inspect.isfunction(target) or not target.__module__.startswith("automationbench."):
        return None
    return target


def _footprint(func: Callable, params: frozenset[str], fields: frozenset[str], seen: dict):
    """Return the service set reached through ``params``, or None if unresolvable."""
    key = (func, params)
    if key in seen:
        # A binding still in progress is recursion: unknown, never a partial set.
        return seen[key]
    seen[key] = None
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    except (OSError, TypeError, SyntaxError):
        seen[key] = None
        return None
    root = tree.body[0]
    parents = {child: node for node in ast.walk(root) for child in ast.iter_child_nodes(node)}
    namespace = dict(func.__globals__)
    # Helpers imported inside the function body (simulator modules only).
    for node in ast.walk(root):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").startswith("automationbench."):
            module = importlib.import_module(node.module or "")
            for alias in node.names:
                namespace[alias.asname or alias.name] = getattr(module, alias.name, None)
    services: set[str] = set()
    for node in ast.walk(root):
        if not (isinstance(node, ast.Name) and node.id in params and isinstance(node.ctx, ast.Load)):
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Attribute) and parent.value is node:
            if parent.attr not in fields:
                seen[key] = None
                return None
            services.add(parent.attr)
            continue
        if isinstance(parent, ast.keyword):
            keyword, call = parent, parents.get(parent)
        else:
            keyword, call = None, parent
        if not isinstance(call, ast.Call) or call.func is node:
            seen[key] = None
            return None
        if keyword is None and node not in call.args:
            seen[key] = None
            return None
        target = _resolve(call.func, namespace)
        if target is None:
            seen[key] = None
            return None
        names = list(inspect.signature(target).parameters)
        if keyword is not None:
            if keyword.arg is None or keyword.arg not in names:
                seen[key] = None
                return None
            inner = frozenset({keyword.arg})
        else:
            index = call.args.index(node)
            if index >= len(names) or any(isinstance(arg, ast.Starred) for arg in call.args[: index + 1]):
                seen[key] = None
                return None
            inner = frozenset({names[index]})
        reached = _footprint(target, inner, fields, seen)
        if reached is None:
            seen[key] = None
            return None
        services |= reached
    seen[key] = frozenset(services)
    return seen[key]


@cache
def handler_footprints() -> MappingProxyType:
    """Tool name -> frozenset of reachable world services, or None if unknown."""
    from automationbench.tools import ALL_TOOLS

    fields, seen, result = _fields(), {}, {}
    for func in ALL_TOOLS:
        parameters = inspect.signature(func).parameters
        name = func.__name__
        if name in result:
            result[name] = None  # duplicate registration: ambiguous
            continue
        result[name] = (
            _footprint(func, frozenset({"world"}), fields, seen)
            if "world" in parameters
            else frozenset()
        )
    for name in _WORLDLESS:
        result.setdefault(name, frozenset())
    return MappingProxyType(result)


def cannot_touch(name: object, service: str) -> bool:
    """True only when the named handler's static footprint excludes ``service``."""
    if type(name) is not str:
        return False
    footprint = handler_footprints().get(name)
    return footprint is not None and service not in footprint


def outside_service(name: object, service: str, before, after) -> bool:
    """An occurrence that cannot touch ``service`` and was observed not to.

    Both are required: the footprint rules out mutate-then-revert inside the
    call, and the observed snapshots rule out a handler that contradicts its
    installed source (e.g. a caller-registered function under a real name).
    """
    if not cannot_touch(name, service):
        return False
    try:
        return canonical_json(_plain(before.get(service))) == canonical_json(_plain(after.get(service)))
    except (AttributeError, TypeError, ValueError):
        return False


def _plain(value):
    if hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value
