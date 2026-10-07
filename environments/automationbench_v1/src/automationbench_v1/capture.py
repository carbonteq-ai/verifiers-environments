"""Opt-in raw action/world material, independent of assessment and reward labels.

Each tool call publishes one ``automationbench_raw_action`` envelope as tool-server
execution evidence. Envelopes name worlds by the SHA-256 of their canonical JSON.
A world's bytes are published once per rollout: either in full (``snapshots``) or
as a structural patch against another published world (``patches``), whose
reconstruction is verified against the digest before use. Earlier releases put
both full worlds in every envelope and kept every distinct world in the synced
rollout state, so state transfer, receipts, and the assessment material derived
from them grew with every call. Readers resolve both forms through
``SnapshotStore``.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any, Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

RAW_ACTION_KIND = "automationbench_raw_action"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


# --------------------------------------------------------------------------------------
# Structural world patches. Operations: {"=": value} replaces a value; {"{}": {key: op},
# "-": [keys]} edits an object; {"+": [items]} appends to a list; {"[]": {"index": op}}
# edits list items in place. A patch is only published after its reconstruction was
# checked byte-for-byte against the canonical target, so lossy cases (for example a
# value whose canonical form changes without changing Python equality) fall back to
# the full world.
# --------------------------------------------------------------------------------------
def world_patch(before: Any, after: Any) -> dict[str, Any] | None:
    """Operations turning ``before`` into ``after``; None when they compare equal."""
    if type(before) is not type(after):
        return {"=": after}
    if before == after:
        return None
    if isinstance(before, dict):
        edits = {}
        for key, value in after.items():
            if key not in before:
                edits[key] = {"=": value}
            else:
                op = world_patch(before[key], value)
                if op is not None:
                    edits[key] = op
        removed = [key for key in before if key not in after]
        op: dict[str, Any] = {"{}": edits}
        if removed:
            op["-"] = removed
        return op
    if isinstance(before, list):
        if len(after) >= len(before) and after[: len(before)] == before:
            return {"+": after[len(before) :]}
        if len(after) == len(before):
            return {
                "[]": {
                    str(index): op
                    for index, (old, new) in enumerate(zip(before, after, strict=True))
                    if (op := world_patch(old, new)) is not None
                }
            }
    return {"=": after}


def apply_world_patch(value: Any, op: Mapping[str, Any]) -> Any:
    """Apply ``world_patch`` operations; ``value`` may be modified in place."""
    if "=" in op:
        return op["="]
    if "{}" in op:
        if not isinstance(value, dict):
            raise ValueError("world_patch_base_mismatch")
        for key in op.get("-", ()):
            value.pop(key)
        for key, child in op["{}"].items():
            value[key] = apply_world_patch(value.get(key), child)
        return value
    if "+" in op:
        if not isinstance(value, list):
            raise ValueError("world_patch_base_mismatch")
        value.extend(op["+"])
        return value
    if "[]" in op:
        if not isinstance(value, list):
            raise ValueError("world_patch_base_mismatch")
        for index, child in op["[]"].items():
            value[int(index)] = apply_world_patch(value[int(index)], child)
        return value
    raise ValueError("world_patch_unknown_operation")


class SnapshotStore:
    """World bytes published by one rollout's raw-action envelopes, by digest.

    Accepts both envelope forms in any order. Every returned text was verified
    against its digest; a world whose bytes or patch base no retained envelope
    carries is unavailable (``None``), never guessed.
    """

    def __init__(self, envelopes: Iterable[Mapping[str, Any]] = ()) -> None:
        self._texts: dict[str, str] = {}
        self._patches: dict[str, Mapping[str, Any]] = {}
        for envelope in envelopes:
            self.add(envelope)

    def add(self, envelope: Mapping[str, Any]) -> None:
        for digest, text in (envelope.get("snapshots") or {}).items():
            if not isinstance(text, str) or _digest(text) != digest:
                raise ValueError("snapshot_digest_mismatch")
            self._texts.setdefault(digest, text)
        for digest, patch in (envelope.get("patches") or {}).items():
            if not isinstance(patch, Mapping) or not isinstance(patch.get("base"), str):
                raise ValueError("snapshot_patch_malformed")  # noqa: TRY004
            self._patches.setdefault(digest, patch)

    def text(self, digest: str) -> str | None:
        chain = []
        current = digest
        while current not in self._texts:
            patch = self._patches.get(current)
            if patch is None or current in chain:
                return None
            chain.append(current)
            current = patch["base"]
        text = self._texts[current]
        for target in reversed(chain):
            patch = self._patches[target]
            text = canonical_json(apply_world_patch(json.loads(text), patch["ops"]))
            if _digest(text) != target:
                raise ValueError("snapshot_digest_mismatch")
            self._texts[target] = text
        return text


def raw_action_envelopes(receipts: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Raw-action envelopes carried by decoded tool-server receipts, in order."""
    envelopes = []
    for receipt in receipts:
        for encoded in receipt.get("evidence_json") or ():
            envelope = json.loads(encoded)
            if isinstance(envelope, dict) and envelope.get("kind") == RAW_ACTION_KIND:
                envelopes.append(envelope)
    return envelopes


def trace_snapshot_store(events: Iterable[Any]) -> SnapshotStore:
    """Store over a trace's retained tool-server events (models or JSON dicts)."""
    receipts = []
    for event in events:
        record = event if isinstance(event, Mapping) else event.model_dump(mode="json")
        if record.get("source") == "tool_server":
            receipts.append(json.loads(record["receipt_json"]))
    return SnapshotStore(raw_action_envelopes(receipts))


# --------------------------------------------------------------------------------------
# Capture inside the tool server.
# --------------------------------------------------------------------------------------
_local_sink: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "automationbench_local_evidence", default=None
)


@contextlib.contextmanager
def collect_local_evidence() -> Iterator[list[dict[str, Any]]]:
    """Retain envelopes of tool calls made outside a native invocation (fixtures, offline use)."""
    sink: list[dict[str, Any]] = []
    token = _local_sink.set(sink)
    try:
        yield sink
    finally:
        _local_sink.reset(token)


def snapshot_world(state: Any) -> tuple[str, str]:
    """Digest and canonical bytes of the current world; records the initial digest."""
    encoded = canonical_json(state.world)
    digest = _digest(encoded)
    if state.action_initial_digest is None:
        state.action_initial_digest = digest
    return digest, encoded


def _retain(
    state: Any,
    tool_name: str,
    arguments_json: str,
    before: tuple[str, str],
    before_world: Any,
    *,
    status: Literal["returned", "raised", "rejected"],
    result: Any = None,
    error: Exception | None = None,
) -> None:
    before_digest, before_text = before
    after_digest, after_text = snapshot_world(state)
    record = CapturedAction(
        occurrence_index=state.action_count,
        tool_name=tool_name,
        arguments_json=arguments_json,
        before_digest=before_digest,
        after_digest=after_digest,
        status=status,
        result_json=canonical_json(result) if error is None else None,
        error_json=canonical_json({"type": type(error).__name__, "message": str(error)})
        if error is not None
        else None,
    )
    state.action_count += 1
    published = set(state.action_published)
    snapshots: dict[str, str] = {}
    patches: dict[str, dict[str, Any]] = {}
    if before_digest not in published:
        snapshots[before_digest] = before_text
    if after_digest != before_digest and after_digest not in published:
        ops = world_patch(before_world, state.world)
        if ops is not None and len(canonical_json(ops)) < len(after_text):
            try:
                rebuilt = canonical_json(apply_world_patch(json.loads(before_text), ops))
            except (ValueError, KeyError, IndexError, TypeError):
                rebuilt = None
            if rebuilt == after_text:
                patches[after_digest] = {"base": before_digest, "ops": ops}
        if after_digest not in patches:
            snapshots[after_digest] = after_text
    envelope: dict[str, Any] = {
        "kind": RAW_ACTION_KIND,
        "action": record.model_dump(mode="json"),
        "snapshots": snapshots,
    }
    if patches:
        envelope["patches"] = patches
    # Publish independently of mutable MCP state when the native runtime supports
    # it. A world counts as published only once an envelope carrying it was handed
    # to the active invocation; the mark travels with the committed state, so a
    # failed or uncommitted call conservatively republishes later.
    publish = getattr(vf, "record_execution_evidence", None)
    sink = _local_sink.get()
    if sink is not None:
        sink.append(envelope)
        retained = True
    else:
        retained = publish is not None and bool(publish(envelope))
    if retained:
        new = [digest for digest in (*snapshots, *patches) if digest not in published]
        if new:
            state.action_published = (*state.action_published, *new)


def capture_action[T](state: Any, tool_name: str, arguments: Any, operation: Callable[[], T]) -> T:
    """Observe committed state; never persist a transient world after an exception."""
    if not state.capture_actions:
        return operation()
    args = canonical_json(arguments)
    before_world = state.world
    before = snapshot_world(state)
    try:
        result = operation()
    except Exception as error:
        _retain(state, tool_name, args, before, before_world, status="raised", error=error)
        raise
    _retain(state, tool_name, args, before, before_world, status="returned", result=result)
    return result


def capture_rejection(state: Any, tool_name: str, arguments: Any, error: Exception) -> None:
    """Record known local pre-dispatch validation rejection without fabricating effects."""
    if state.capture_actions:
        _retain(
            state,
            tool_name,
            canonical_json(arguments),
            snapshot_world(state),
            state.world,
            status="rejected",
            error=error,
        )
