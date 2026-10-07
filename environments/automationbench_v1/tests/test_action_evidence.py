"""Raw capture parity and local persistence; no reward or causality labels."""

import asyncio
import copy
import hashlib
import json
from datetime import UTC, datetime

import pytest
import verifiers.v1 as vf

from automationbench.schema.world import WorldState
from automationbench_v1.api_tools import AutomationBenchApiToolset
from automationbench_v1.capture import (
    SnapshotStore,
    capture_action,
    collect_local_evidence,
)
from automationbench_v1.limited_tools import (
    AutomationBenchLimitedToolset,
    AutomationBenchLimitedToolsetConfig,
)
from automationbench_v1.taskset import AutomationBenchConfig, AutomationBenchTaskset
from automationbench_v1.tools import AutomationBenchState, AutomationBenchToolset


def state(enabled=True):
    task = AutomationBenchTaskset(AutomationBenchConfig(domains=["simple"])).load()[0]
    return AutomationBenchState(
        world=copy.deepcopy(task.data.initial_state), capture_actions=enabled
    )


@pytest.mark.parametrize("mode", ["meta", "api", "limited"])
def test_capture_preserves_tool_result_and_committed_world(mode, monkeypatch):
    from automationbench import sim_runtime

    def now(tz=None):
        instant = datetime(2026, 1, 1, tzinfo=UTC)
        return instant if tz is not None else instant.replace(tzinfo=None)

    # The simulator reads its clock through sim_runtime.
    monkeypatch.setattr(sim_runtime, "now", now)
    initial = WorldState.model_validate(state(False).world).model_dump(mode="json")
    states = [
        AutomationBenchState(world=copy.deepcopy(initial), capture_actions=enabled)
        for enabled in (False, True)
    ]
    results = []
    sinks = []
    for item in states:
        sink_context = collect_local_evidence()
        sinks.append(sink_context.__enter__())
        if mode == "meta":
            tools = AutomationBenchToolset(vf.ToolsetConfig())
            tools._inert_state = item
            tools.search_tools("salesforce contact", top_k=2)
            result = tools.execute_tool(
                "salesforce_contact_update", '{"id":"003001","phone":"+1-555-0101"}'
            )
        elif mode == "api":
            tools = AutomationBenchApiToolset(vf.ToolsetConfig())
            tools._inert_state = item
            tools.api_search("salesforce contact", top_k=2)
            result = tools.api_fetch(
                "PATCH",
                "https://example.my.salesforce.com/services/data/v61.0/sobjects/Contact/003001",
                body='{"Phone":"+1-555-0101"}',
            )
        else:
            tools = AutomationBenchLimitedToolset(
                AutomationBenchLimitedToolsetConfig(allowed_tools=("salesforce_contact_update",))
            )
            tools._inert_state = item
            result = tools.invoke("salesforce_contact_update", id="003001", phone="+1-555-0101")
        sink_context.__exit__(None, None, None)
        results.append(result)
    assert results[0] == results[1]
    assert states[0].world == states[1].world
    assert sinks[0] == [] and states[0].action_count == 0
    captured, envelopes = states[1], sinks[1]
    actions = [envelope["action"] for envelope in envelopes]
    assert [action["occurrence_index"] for action in actions] == list(range(len(actions)))
    assert captured.action_count == len(actions)
    assert actions[-1]["before_digest"] != actions[-1]["after_digest"]
    result_json = actions[-1]["result_json"]
    assert result_json is not None
    assert json.loads(result_json) == results[1]
    store = SnapshotStore(envelopes)
    for envelope in envelopes:
        for digest, encoded in envelope["snapshots"].items():
            assert hashlib.sha256(encoded.encode()).hexdigest() == digest
    # Each distinct world is published once; the mutated world travels as a patch.
    published = [digest for e in envelopes for digest in (*e["snapshots"], *e.get("patches", {}))]
    assert len(published) == len(set(published)) == len(set(captured.action_published))
    assert envelopes[-1]["patches"] and actions[-1]["after_digest"] not in envelopes[-1]["snapshots"]
    assert json.loads(store.text(actions[-1]["after_digest"])) == captured.world
    restored = AutomationBenchState.model_validate_json(captured.model_dump_json())
    assert restored.action_count == captured.action_count
    assert restored.action_published == captured.action_published
    assert all(action["native_join_status"] == "unqualified" for action in actions)


def test_read_only_and_failures_deduplicate_world_without_committing_partial_effects(monkeypatch):
    from automationbench_v1 import limited_tools

    current = state()
    before = copy.deepcopy(current.world)
    sink_context = collect_local_evidence()
    envelopes = sink_context.__enter__()
    assert capture_action(current, "read", {"x": 1}, lambda: "unchanged") == "unchanged"
    assert len(current.action_published) == 1

    def failing(*, world, **kwargs):
        world.salesforce.contacts[0].phone = "partial-mutation"
        raise RuntimeError("upstream failed")

    monkeypatch.setitem(limited_tools._ZAPIER_TOOLS, "salesforce_contact_update", failing)
    tools = AutomationBenchLimitedToolset(
        AutomationBenchLimitedToolsetConfig(allowed_tools=("salesforce_contact_update",))
    )
    tools._inert_state = current
    with pytest.raises(RuntimeError, match="upstream failed"):
        tools.invoke("salesforce_contact_update", id="003001")
    assert current.world == before
    assert envelopes[-1]["action"]["status"] == "raised"
    error_json = envelopes[-1]["action"]["error_json"]
    assert error_json is not None
    assert json.loads(error_json)["type"] == "RuntimeError"
    assert len(current.action_published) == 1
    # The unchanged world was already published, so later envelopes carry no bytes.
    assert envelopes[-1]["snapshots"] == {} and "patches" not in envelopes[-1]
    with pytest.raises(ValueError, match="not enabled"):
        tools.invoke("forbidden", x="original")
    sink_context.__exit__(None, None, None)
    assert envelopes[-1]["action"]["status"] == "rejected"
    assert json.loads(envelopes[-1]["action"]["arguments_json"]) == {"x": "original"}
    assert (
        WorldState.model_validate(current.world).salesforce.contacts[0].phone != "partial-mutation"
    )


def test_capture_is_private_to_state_not_visible_tool_parameters():
    import inspect

    assert tuple(inspect.signature(AutomationBenchToolset.execute_tool).parameters) == (
        "self",
        "tool_name",
        "arguments",
    )
    assert tuple(inspect.signature(AutomationBenchApiToolset.api_fetch).parameters) == (
        "self",
        "method",
        "url",
        "params",
        "body",
    )


def test_native_state_boundary_failure_transport_remains_unqualified(monkeypatch):
    """Exercise actual native wrapper with an isolated fake state channel, not MCP qualification."""
    tools = AutomationBenchToolset(vf.ToolsetConfig())
    stored = state()

    async def pull():
        return stored.model_copy(deep=True)

    async def push(before):
        nonlocal stored
        stored = tools.state.model_copy(deep=True)

    monkeypatch.setattr(tools, "_pull_state", pull)
    monkeypatch.setattr(tools, "_push_state", push)
    # Isolate the existing state-only channel behavior even on the candidate runtime.
    monkeypatch.setattr(tools, "execution_capture_enabled", lambda: False)

    def failure():
        def operation():
            raise RuntimeError("failed action")

        return capture_action(tools.state, "failure", {}, operation)

    with pytest.raises(RuntimeError, match="failed action"):
        asyncio.run(tools._with_state(failure)())
    assert stored.action_count == 0  # Native wrapper does not push on failure.

    def success():
        return capture_action(tools.state, "read", {}, lambda: "result")

    assert asyncio.run(tools._with_state(success)()) == "result"
    assert stored.action_count == 1
    # No native invocation was active, so nothing counts as published.
    assert stored.action_published == ()


def test_candidate_native_buffer_retains_failed_action_snapshots(monkeypatch):
    """Candidate native wrapper plus environment publisher; receipt HTTP is a separate gate."""
    pytest.importorskip("verifiers.v1.mcp.execution")
    tools = AutomationBenchToolset(vf.ToolsetConfig())
    stored = state()
    receipts = []

    async def pull():
        return stored.model_copy(deep=True)

    async def push(before):
        pytest.fail("failed tool must not commit mutable world state")

    async def emit(receipt):
        receipts.append(receipt)

    monkeypatch.setattr(tools, "_pull_state", pull)
    monkeypatch.setattr(tools, "_push_state", push)
    monkeypatch.setattr(tools, "_emit_execution_receipt", emit)

    def failure():
        def operation():
            raise RuntimeError("domain fixture failed")

        return capture_action(tools.state, "failure", {"record": "original"}, operation)

    with pytest.raises(RuntimeError, match="domain fixture failed"):
        asyncio.run(tools._with_state(failure)())
    assert [receipt.phase for receipt in receipts] == ["dispatch", "raised"]
    assert stored.action_count == 0
    material = json.loads(receipts[1].evidence_json[0])
    assert material["kind"] == "automationbench_raw_action"
    assert material["action"]["status"] == "raised"
    assert json.loads(material["action"]["arguments_json"]) == {"record": "original"}
    for digest, encoded in material["snapshots"].items():
        assert hashlib.sha256(encoded.encode()).hexdigest() == digest


def test_limited_keyword_call_is_captured_as_the_model_made_it_and_qualifies_as_a_record_write():
    """The tool server fills omitted parameters with None; capture records the call itself."""
    from types import SimpleNamespace

    from automationbench_v1.contracts import evidence

    current = state()
    contact = WorldState.model_validate(current.world).salesforce.contacts[0]
    tools = AutomationBenchLimitedToolset(
        AutomationBenchLimitedToolsetConfig(allowed_tools=("salesforce_contact_update",))
    )
    tools._inert_state = current
    sink_context = collect_local_evidence()
    envelopes = sink_context.__enter__()
    tools.invoke("salesforce_contact_update", id=contact.id, phone="+1 555 0100", first_name=None, email=None)
    sink_context.__exit__(None, None, None)
    action = envelopes[-1]["action"]
    assert json.loads(action["arguments_json"]) == {"id": contact.id, "phone": "+1 555 0100"}
    selector = SimpleNamespace(object_type="Contact", record_id=contact.id)
    after = evidence.target_record(current.world, selector)
    requested = evidence.qualified_requested_fields(SimpleNamespace(**action), selector, after)
    assert requested is not None and "phone" in requested
