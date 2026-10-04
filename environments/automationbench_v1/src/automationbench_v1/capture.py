"""Opt-in raw action/world material, independent of assessment and reward labels."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


class CapturedAction(BaseModel):
    """One local tool observation; local index is not a native call/turn identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    occurrence_index: int = Field(ge=0, strict=True)
    tool_name: str
    arguments_json: str
    before_digest: str
    after_digest: str
    status: Literal["returned", "raised", "rejected"]
    result_json: str | None = None
    error_json: str | None = None
    ordering_scope: Literal["local_state_history"] = "local_state_history"
    native_join_status: Literal["unqualified"] = "unqualified"


def snapshot_world(state: Any) -> str:
    encoded = canonical_json(state.world)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    state.action_snapshots.setdefault(digest, encoded)
    if state.action_initial_digest is None:
        state.action_initial_digest = digest
    return digest


def _retain(
    state: Any,
    tool_name: str,
    arguments_json: str,
    before: str,
    *,
    status: Literal["returned", "raised", "rejected"],
    result: Any = None,
    error: Exception | None = None,
) -> None:
    after = snapshot_world(state)
    record = CapturedAction(
        occurrence_index=len(state.action_events),
        tool_name=tool_name,
        arguments_json=arguments_json,
        before_digest=before,
        after_digest=after,
        status=status,
        result_json=canonical_json(result) if error is None else None,
        error_json=canonical_json({"type": type(error).__name__, "message": str(error)})
        if error is not None
        else None,
    )
    state.action_events += (record,)
    # Publish independently of mutable MCP state when the candidate native runtime
    # supports it. Older pins retain local evidence with explicitly unqualified
    # transport; calibration readiness must reject those runtimes for collection.
    publish = getattr(vf, "record_execution_evidence", None)
    if publish is not None:
        publish(
            {
                "kind": "automationbench_raw_action",
                "action": record.model_dump(mode="json"),
                "snapshots": {
                    digest: state.action_snapshots[digest]
                    for digest in {record.before_digest, record.after_digest}
                },
            }
        )


def capture_action[T](state: Any, tool_name: str, arguments: Any, operation: Callable[[], T]) -> T:
    """Observe committed state; never persist a transient world after an exception."""
    if not state.capture_actions:
        return operation()
    args = canonical_json(arguments)
    before = snapshot_world(state)
    try:
        result = operation()
    except Exception as error:
        _retain(state, tool_name, args, before, status="raised", error=error)
        raise
    _retain(state, tool_name, args, before, status="returned", result=result)
    return result


def capture_rejection(state: Any, tool_name: str, arguments: Any, error: Exception) -> None:
    """Record known local pre-dispatch validation rejection without fabricating effects."""
    if state.capture_actions:
        _retain(
            state,
            tool_name,
            canonical_json(arguments),
            snapshot_world(state),
            status="rejected",
            error=error,
        )
