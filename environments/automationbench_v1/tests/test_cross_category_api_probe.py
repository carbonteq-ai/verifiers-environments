"""Actual recorded native API transport across 15 tasks in each of seven domains.

These probes establish source, trace, execution and assessment transport only.
An unregistered manifest is an explicit reward-coverage gap, not a failed native
transport probe. Official assertions are used only to replay the unchanged
scalar scorer, never to author reward rules. No tokenizer or tool-call ordinal
is used to invent token masks for tokenless SDK traces.
"""

import asyncio
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from verifiers.v1.assessment_source import capture_trace_source

from automationbench_v1.contracts import supported_tasks
from automationbench_v1.manifest_assessments import ManifestAssessmentTask
from automationbench_v1.taskset import (
    AutomationBenchData,
    AutomationBenchTask,
    AutomationBenchTaskConfig,
)
from automationbench_v1.tools import AutomationBenchState

SELECTION = Path(
    "/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/"
    "reward-candidate/cross-category-selection.json"
)


def selected_cases():
    if not SELECTION.exists():
        return [
            pytest.param(
                None, marks=pytest.mark.skip(reason="cross-category source selection unavailable")
            )
        ]
    selection = json.loads(SELECTION.read_bytes())
    entries = selection["tasks"]
    assert len(entries) == 105
    assert set(Counter(item["domain"] for item in entries).values()) == {15}
    assert len({item["domain"] for item in entries}) == 7
    assert len({item["task_name"] for item in entries}) == 105
    return [pytest.param(item, id=item["task_name"]) for item in entries]


def restore_state(trace, data):
    retained = trace.info.get("automationbench", {})
    assert isinstance(retained.get("end_state"), dict), "recorded final world unavailable"
    artifacts = dict(trace.state.artifacts)
    trace.state = AutomationBenchState(
        world=retained["end_state"],
        initial_state=data.initial_state,
        assertions=data.assertions,
        artifacts=artifacts,
    )


def probe_capabilities(trace, source, registered):
    tokens = sum(len(node.token_ids) for node in trace.nodes)
    return {
        "trace_id": trace.id,
        "snapshot_id": source.snapshot_id,
        "native_executions": len(source.executions),
        "native_nodes": len(source.nodes),
        "recorded_token_ids": tokens,
        "token_capture": "tokenless" if tokens == 0 else "recorded",
        "execution_to_token_projection": "unavailable_not_qualified_by_this_probe",
        "reward_manifest_coverage": "registered_bounded_manifest"
        if registered
        else "unavailable_manifest_unregistered",
        "whole_task_reward_qualification": "unavailable_not_qualified_by_transport",
    }


@pytest.mark.parametrize("entry", selected_cases())
def test_actual_cross_category_native_api_transport(entry, record_property):
    assert entry is not None
    path = Path(entry["source_episode_path"])
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["source_episode_sha256"]
    episode = vf.WireEpisode.model_validate_json(raw)
    assert episode.traces
    assert [trace.id for trace in episode.traces] == entry["trace_ids"]
    registered = entry["task_name"] in supported_tasks()
    capabilities = []
    for retained_trace in episode.traces:
        trace = cast(Any, retained_trace)
        data = AutomationBenchData.model_validate(trace.task.data.model_dump(mode="json"))
        assert data.task_name == entry["task_name"] and data.domain == entry["domain"]
        restore_state(trace, data)
        config = AutomationBenchTaskConfig(capture_actions=True)
        baseline = AutomationBenchTask(data, config)
        task = ManifestAssessmentTask(data, config)
        original_identity = (trace.id, trace.episode_id)
        evidence = task.assessment_source(trace)
        source = capture_trace_source(trace, task_evidence=evidence)
        assert source.trace_ids == (trace.id,) and source.episode_id == trace.episode_id
        assert all(node.trace_id == trace.id for node in source.nodes)
        assert len(source.nodes) == len(trace.nodes)
        assert all(
            item.trace_id == trace.id and item.episode_id == trace.episode_id
            for item in source.executions
        )
        assert len({item.occurrence_id for item in source.executions}) == len(source.executions)
        native_occurrences = {
            (
                event.source,
                event.model_dump(mode="json").get("invocation_id")
                or event.model_dump(mode="json").get("execution_id"),
            )
            for event in trace.tool_execution_events
        }
        assert {
            (item.origin, item.invocation_id) for item in source.executions
        } == native_occurrences
        assert vf.SourceSnapshot.model_validate_json(source.model_dump_json()) == source
        asyncio.run(baseline.score(trace))
        scalar_rewards = copy.deepcopy(trace.rewards)
        scalar_metrics = copy.deepcopy(trace.metrics)
        assert capture_trace_source(trace, task_evidence=task.assessment_source(trace)) == source
        if registered:
            asyncio.run(task.score(trace))
            assert not trace.assessment_errors and not trace.credit_errors
            assert trace.assessment_batches
            assert trace.rewards == scalar_rewards and trace.metrics == scalar_metrics
            assert (
                capture_trace_source(trace, task_evidence=task.assessment_source(trace)) == source
            )
        assert (trace.id, trace.episode_id) == original_identity
        capabilities.append(probe_capabilities(trace, source, registered))
    restored = vf.WireEpisode.model_validate_json(episode.model_dump_json())
    assert [trace.id for trace in restored.traces] == [trace.id for trace in episode.traces]
    for before, after in zip(episode.traces, restored.traces, strict=True):
        old, new = cast(Any, before), cast(Any, after)
        data = AutomationBenchData.model_validate(new.task.data.model_dump(mode="json"))
        restore_state(new, data)
        task = ManifestAssessmentTask(data, AutomationBenchTaskConfig(capture_actions=True))
        old_source = capture_trace_source(old, task_evidence=task.assessment_source(old))
        assert capture_trace_source(new, task_evidence=task.assessment_source(new)) == old_source
        assert new.assessment_batches == old.assessment_batches
        assert new.credit_assignments == old.credit_assignments
        if registered:
            credits = tuple(new.credit_assignments)
            rewards = copy.deepcopy(new.rewards)
            asyncio.run(task.score(new))
            assert not new.assessment_errors and not new.credit_errors
            assert tuple(new.credit_assignments) == credits and new.rewards == rewards
            assert (
                capture_trace_source(new, task_evidence=task.assessment_source(new)) == old_source
            )
    record_property("native_api_capabilities", canonical_capabilities(capabilities))
    assert path.read_bytes() == raw, "probe modified original recorded source"


def canonical_capabilities(capabilities):
    return json.dumps(capabilities, sort_keys=True, separators=(",", ":"), allow_nan=False)
