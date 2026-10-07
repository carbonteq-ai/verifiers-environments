"""Metadata stays source-bound, optional, and outside policy prompts."""

import json
from pathlib import Path

import pytest
import verifiers.v1 as vf
from pydantic import ValidationError

from automationbench_v1.calibration.inventory import freeze_inventory, save_inventory
from automationbench_v1.calibration.models import CollectionLimits, TaskSelection, plan_collection
from automationbench_v1.task_metadata import (
    Artifact,
    Classification,
    TaskMetadataExport,
    attach_task_metadata,
    build_reference_metadata,
    digest,
    load_task_metadata,
    save_task_metadata,
)
from automationbench_v1.taskset import AutomationBenchConfig, AutomationBenchTaskset


@pytest.fixture
def source(tmp_path: Path):
    inventory = freeze_inventory(AutomationBenchConfig(), source_identity={"fixture": "metadata"})
    frozen = inventory.tasks[0]
    manifest = plan_collection(
        inventory,
        selections=(
            TaskSelection(
                task_name=frozen.task_name,
                task_digest=frozen.digest,
                family="fixture-family",
                split="development",
            ),
        ),
        route_identity="offline-fixture",
        native_config={"fixture": True},
        scorer_revision="original-fixture-scorer",
        limits=CollectionLimits(
            max_concurrent=1,
            max_total_attempts=1,
            max_elapsed_seconds=60,
            attempt_timeout_seconds=20,
            max_turns=4,
            max_output_tokens=100,
            cost_measurement="unavailable",
        ),
    )
    save_inventory(inventory, tmp_path / "inventory.json")
    (tmp_path / "manifest.json").write_text(manifest.model_dump_json())
    task = frozen.instantiate()
    episode = vf.Episode(
        task=vf.TraceTask(type="AutomationBenchTask", data=task.data),
        group=vf.GroupInfo(id="fixture-attempt"),
        run=vf.EvalRunInfo(id=manifest.digest, repetition_index=0),
        ok=True,
    )
    trace = vf.Trace(
        task=episode.task,
        episode_id=episode.id,
        agent=vf.AgentInfo(config=vf.AgentConfig(model="gpt-6-luna")),
        ok=True,
        is_completed=True,
        stop_condition="agent_completed",
    )
    trace.record_reward("partial_credit", 1.0)
    episode.traces.append(trace)
    directory = tmp_path / "fixture-attempt"
    directory.mkdir()
    path = directory / "episode.json"
    path.write_text(episode.model_dump_json())
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "task_name": task.key,
                        "split": "development",
                        "attempt_id": "fixture-attempt",
                        "source_episode_path": str(path),
                        "source_episode_sha256": Artifact.capture(path).sha256,
                        "family": "deliberately-not-a-workflow",
                        "selection_score": 999,
                    }
                ]
            }
        )
    )
    return index, frozen, path


def rebind_episode(index: Path, path: Path, episode: dict) -> None:
    path.write_text(json.dumps(episode))
    data = json.loads(index.read_text())
    data["entries"][0]["source_episode_sha256"] = Artifact.capture(path).sha256
    index.write_text(json.dumps(data))


def with_classification(export, evidence):
    body = export.model_dump(mode="json", exclude={"digest"})
    body["tasks"][0]["classifications"]["capabilities"] = Classification(
        status="reviewed",
        labels=("arithmetic", "policy_retrieval"),
        definition_revision="fixture-review-v1",
        evidence=(evidence,),
    ).model_dump(mode="json")
    return TaskMetadataExport.model_validate({**body, "digest": digest(body)})


def test_export_is_deterministic_and_keeps_observation_separate_from_qualification(source):
    index, _, _ = source
    first = build_reference_metadata(index)
    assert first == build_reference_metadata(index)
    task = first.tasks[0]
    assert all(
        value.status == "not_reviewed" and not value.labels
        for value in task.classifications.values()
    )
    observed = task.references[0]
    assert observed.recorded_reward == 1.0  # Read from native reward, not index's 999.
    assert observed.redesigned_guard_qualification == "unassessed"
    assert observed.efficiency_budget_status == "observation_only"
    assert observed.reference_family == "fixture-family"
    assert observed.scorer_revision == "original-fixture-scorer"
    assert observed.sampled_output_tokens.status == "unavailable"
    assert observed.tool_calls.status == "unavailable"


def test_attach_preserves_prompt_and_changes_native_identity_only_when_selected(source, tmp_path):
    index, frozen, _ = source
    task = frozen.instantiate()
    old_hash, old_prompt = task.hash, task.data.prompt
    assert "capabilities" not in task.data.model_dump()
    export = with_classification(build_reference_metadata(index), Artifact.capture(index))
    path = tmp_path / "metadata.json"
    save_task_metadata(export, path)
    loaded = load_task_metadata(path, expected_digest=export.digest)
    task.data = attach_task_metadata(task.data, loaded)
    assert task.data.prompt == old_prompt
    assert task.hash != old_hash
    assert task.data.capabilities == ["arithmetic", "policy_retrieval"]
    assert task.data.task_metadata_status["guard_patterns"] == "not_reviewed"
    assert task.data.model_dump()["task_metadata_digest"] == export.digest
    assert vf.WireTaskData.model_validate(task.data.model_dump()).model_dump()["capabilities"] == [
        "arithmetic",
        "policy_retrieval",
    ]


def test_taskset_opt_in_loads_same_facets_without_changing_prompt(source, tmp_path):
    index, frozen, _ = source
    export = with_classification(build_reference_metadata(index), Artifact.capture(index))
    path = tmp_path / "metadata.json"
    save_task_metadata(export, path)
    config = AutomationBenchConfig(
        task_names=[frozen.task_name], task_metadata_path=path, task_metadata_digest=export.digest
    )
    tasks = AutomationBenchTaskset(config).load()
    assert len(tasks) == 1
    assert tasks[0].data.capabilities == ["arithmetic", "policy_retrieval"]
    assert tasks[0].data.prompt == frozen.instantiate().data.prompt
    with pytest.raises(ValidationError, match="both path and expected digest"):
        AutomationBenchConfig(task_metadata_path=path)


@pytest.mark.parametrize("tamper", ["episode_bytes", "source_bytes", "task_data", "run"])
def test_export_rejects_changed_sources_and_wrong_identity(source, tamper):
    index, _, path = source
    if tamper == "episode_bytes":
        path.write_text(path.read_text() + " ")
    elif tamper == "source_bytes":
        manifest_path = path.parent.parent / "manifest.json"
        value = json.loads(manifest_path.read_text())
        value["scorer_revision"] = "changed-without-rebinding"
        manifest_path.write_text(json.dumps(value))
    else:
        episode = json.loads(path.read_text())
        if tamper == "task_data":
            episode["task"]["data"]["prompt"] = "changed prompt"
        else:
            episode["run"]["id"] = "wrong-run"
        rebind_episode(index, path, episode)
    with pytest.raises(ValueError):
        build_reference_metadata(index)


def test_load_checks_selected_digest_and_source_bytes_and_attach_checks_content(source, tmp_path):
    index, frozen, path = source
    export = build_reference_metadata(index)
    output = tmp_path / "metadata.json"
    save_task_metadata(export, output)
    with pytest.raises(ValueError, match="selection digest mismatch"):
        load_task_metadata(output, expected_digest="0" * 64)
    data = frozen.instantiate().data.model_copy(update={"prompt": "new prompt"})
    with pytest.raises(ValueError, match="task content hash mismatch"):
        attach_task_metadata(data, export)
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="source artifact hash mismatch"):
        load_task_metadata(output, expected_digest=export.digest)


def test_sdk_summary_is_not_exact_sampled_tokens_or_unconditionally_qualified_usage(source):
    index, _, path = source
    episode = json.loads(path.read_text())
    trace = episode["traces"][0]
    trace["info"]["codex_sdk"] = {"events": []}
    trace["info"]["automationbench_output_budget"] = {
        "status": "observed",
        "reported_counts": {"outputTokens": 1234},
    }
    rebind_episode(index, path, episode)
    observed = build_reference_metadata(index).tasks[0].references[0]
    assert observed.reported_output_tokens.status == "unavailable"
    assert observed.sampled_output_tokens.status == "unavailable"
    assert observed.truncation == "unknown"


def test_classification_requires_explicit_support_and_unreviewed_is_not_empty_review(source):
    with pytest.raises(ValidationError):
        Classification(labels=("policy_retrieval",))
    with pytest.raises(ValidationError):
        Classification(status="reviewed", labels=("policy_retrieval",))
    index, _, _ = source
    reviewed_empty = Classification(
        status="reviewed", definition_revision="fixture-v1", evidence=(Artifact.capture(index),)
    )
    assert reviewed_empty.status != Classification().status
