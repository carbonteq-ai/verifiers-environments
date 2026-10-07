"""Prepare and execute explicit reference tranches using native collection journals.

Preparation is entirely offline. A reviewed family/split file is mandatory;
the benchmark does not supply an authoritative related-variant grouping.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

import verifiers.v1 as vf

from ..taskset import AutomationBenchConfig, _with_world_time
from .cli import configuration
from .collector import _write_native, validate_episode
from .inventory import FrozenTask, TaskInventory, content_digest, freeze_inventory
from .models import CalibrationManifest, CollectionLimits, TaskSelection, plan_collection
from .runner import native_binding
from .sdk_runner import (
    SIGNED_IN_ROUTE_IDENTITY,
    run_collection_sdk,
    sdk_client_config,
    validate_sdk_binding,
)
from .source import source_identity
from .verify import scorer_fingerprint, verify_retained

DOMAINS = ("simple", "sales", "marketing", "operations", "support", "finance", "hr")


def partition_inventory(inventory: TaskInventory) -> tuple[TaskInventory, dict[str, list[str]]]:
    """Use only explicit valid world clocks; preserve missing-clock prompts exactly."""
    partitions: dict[str, list[str]] = {"timed": [], "untimed": []}
    tasks = []
    for task in inventory.tasks:
        declared = task.data["initial_state"].get("meta", {}).get("current_time")
        if declared is None:
            partitions["untimed"].append(task.task_name)
            tasks.append(task.model_dump(mode="json"))
            continue
        if not isinstance(declared, str) or "T" not in declared:
            raise ValueError(f"invalid declared clock: {task.task_name}")
        datetime.fromisoformat(declared)
        data = {**task.data, "prompt": _with_world_time(task.data["prompt"], declared)}
        config = {**task.config, "world_time_context": True}
        tasks.append(
            FrozenTask(
                task_name=task.task_name,
                domain=task.domain,
                data=data,
                config=config,
                digest=content_digest({"data": data, "config": config}),
                initial_score=task.initial_score,
            ).model_dump(mode="json")
        )
        partitions["timed"].append(task.task_name)
    body = inventory.model_dump(mode="json", exclude={"digest"})
    body["tasks"] = tasks
    body["loader_config"] = {**body["loader_config"], "campaign_world_time": "declared_valid_only"}
    result = TaskInventory.model_validate({**body, "digest": content_digest(body)})
    return result, partitions


def split_selections(inventory: TaskInventory, assignment: dict) -> tuple[TaskSelection, ...]:
    """Require exhaustive reviewed membership and keep each family in one split."""
    if set(assignment) != {"schema_version", "reviewed", "method", "tasks"} or (
        assignment["schema_version"] != 1
        or assignment["reviewed"] is not True
        or not isinstance(assignment["method"], str)
        or not assignment["method"].strip()
    ):
        raise ValueError("family/split assignment requires explicit reviewed provenance")
    rows = assignment["tasks"]
    if not isinstance(rows, dict) or set(rows) != {task.task_name for task in inventory.tasks}:
        raise ValueError("family/split assignment must cover exactly the frozen inventory")
    selections = []
    families: dict[str, str] = {}
    for task in inventory.tasks:
        row = rows[task.task_name]
        if not isinstance(row, dict) or set(row) != {"family", "split"}:
            raise ValueError("invalid family/split assignment row")
        selection = TaskSelection(task_name=task.task_name, task_digest=task.digest, **row)
        if families.setdefault(selection.family, selection.split) != selection.split:
            raise ValueError("related task family crosses splits")
        selections.append(selection)
    return tuple(selections)


def _arguments(
    names: list[str], directory: Path, auth_file: Path, timed: bool
) -> argparse.Namespace:
    return argparse.Namespace(
        tasks=names,
        directory=directory,
        auth_file=auth_file,
        concurrency=min(10, len(names)),
        output_budget=16_384,
        sdk_timeout=600.0,
        attempt_timeout=660.0,
        total_timeout=86_400.0,
        world_time_context=timed,
        resume=False,
    )


def _body(record: dict) -> dict:
    return {**record, "digest": content_digest(record)}


def prepare(directory: Path, auth_file: Path, assignments: Path, *, tranche_size: int = 20) -> dict:
    """Freeze all generated tasks once; never start a tool service or model."""
    directory = directory.resolve()
    if directory.exists():
        raise ValueError("campaign preparation requires a fresh directory")
    if not 2 <= tranche_size <= 64:
        raise ValueError("tranche size must be between 2 and 64")
    initial = configuration(
        _arguments(["simple.email_sf_contact_email_update"], directory, auth_file, False)
    )
    task_config = initial.taskset.model_dump(mode="json")
    task_config["domains"] = list(DOMAINS)
    task_config["task_names"] = []
    source = source_identity()
    raw = freeze_inventory(
        AutomationBenchConfig.model_validate(task_config), source_identity=source
    )
    if len(raw.tasks) != 800 or {task.domain for task in raw.tasks} != set(DOMAINS):
        raise ValueError("current campaign requires exhaustive 800-task seven-domain inventory")
    inventory, partitions = partition_inventory(raw)
    assignment = json.loads(assignments.read_bytes())
    selections = split_selections(inventory, assignment)
    selected = {selection.task_name: selection for selection in selections}
    client, sampling = sdk_client_config(), vf.Sampling.model_validate({})
    revision = scorer_fingerprint()
    tranches = []
    # Sequential tranches preserve aggregate concurrency ten across both partitions.
    for partition, names in partitions.items():
        for offset in range(0, len(names), tranche_size):
            tranche_names = names[offset : offset + tranche_size]
            tranche_id = f"{len(tranches):03d}-{partition}"
            config = configuration(
                _arguments(tranche_names, directory / tranche_id, auth_file, partition == "timed")
            )
            limits = CollectionLimits(
                max_concurrent=min(10, len(tranche_names)),
                max_attempts_per_task=1,
                max_total_attempts=len(tranche_names),
                max_infrastructure_retries=0,
                max_elapsed_seconds=86_400,
                attempt_timeout_seconds=660,
                max_turns=1,
                max_output_tokens=16_384,
                cost_measurement="unavailable",
            )
            manifest = plan_collection(
                inventory,
                selections=tuple(selected[name] for name in tranche_names),
                route_identity=SIGNED_IN_ROUTE_IDENTITY,
                native_config=native_binding(config, client, sampling),
                scorer_revision=revision,
                limits=limits,
            )
            validate_sdk_binding(inventory, manifest, config, client, sampling)
            tranches.append(
                {
                    "id": tranche_id,
                    "partition": partition,
                    "manifest": manifest.model_dump(mode="json"),
                    "env_config": config.model_dump(mode="json"),
                }
            )
    campaign = _body(
        {
            "schema_version": 1,
            "inventory_digest": inventory.digest,
            "source_identity": source,
            "scorer_revision": revision,
            "family_assignment": assignment,
            "partitions": partitions,
            "tranches": tranches,
            "max_total_attempts": 800,
            "max_concurrent": 10,
            "max_elapsed_seconds": 86_400,
            "stop_on_execution_error": True,
            "automatic_retries": False,
        }
    )
    captured = source_identity(directory / "source-snapshot.zip")
    if captured != source:
        raise ValueError("source changed during offline preparation; no attempts dispatched")
    _write_native(directory / "inventory.json", inventory.model_dump(mode="json"))
    _write_native(directory / "campaign.json", campaign)
    return campaign


def load(directory: Path) -> tuple[dict, TaskInventory]:
    campaign = json.loads((directory / "campaign.json").read_bytes())
    body = {key: value for key, value in campaign.items() if key != "digest"}
    if campaign.get("digest") != content_digest(body):
        raise ValueError("campaign content digest mismatch")
    inventory = TaskInventory.model_validate_json((directory / "inventory.json").read_bytes())
    if (
        campaign["inventory_digest"] != inventory.digest
        or campaign["source_identity"] != inventory.source_identity
    ):
        raise ValueError("campaign inventory/source identity differs")
    selections = split_selections(inventory, campaign["family_assignment"])
    expected = {s.task_name: s.model_dump(mode="json") for s in selections}
    actual = {}
    for tranche in campaign["tranches"]:
        manifest = CalibrationManifest.model_validate(tranche["manifest"])
        manifest.validate_inventory(inventory)
        for selection in manifest.tasks:
            if selection.task_name in actual:
                raise ValueError("campaign repeats a task across tranches")
            actual[selection.task_name] = selection.model_dump(mode="json")
    if actual != expected:
        raise ValueError("campaign tranches do not cover exact family/split selections")
    return campaign, inventory


def _events(directory: Path) -> list[dict]:
    # These are existing journal records, never a second scheduling authority.
    path = directory / "attempts.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _latest(events: list[dict]) -> dict[str, dict]:
    return {event["attempt_id"]: event for event in events}


def execution_issue(episode: vf.WireEpisode) -> bool:
    return (
        bool(episode.errors)
        or not episode.traces
        or any(
            trace.errors
            or (not trace.ok and trace.stop_condition not in {"max_output_tokens", "max_turns"})
            for trace in episode.traces
        )
    )


async def run(directory: Path) -> dict:
    """Resume missing starts only; drain in-flight work and halt on infrastructure issues."""
    from verifiers.v1.envs.single_agent.env import SingleAgentEnvConfig

    directory = directory.resolve()
    campaign, inventory = load(directory)
    if (
        source_identity() != campaign["source_identity"]
        or scorer_fingerprint() != campaign["scorer_revision"]
    ):
        raise ValueError(
            "campaign loaded source/scorer changed; start a separately frozen campaign"
        )
    tasks = {task.task_name: task for task in inventory.tasks}
    all_events = [
        event for tranche in campaign["tranches"] for event in _events(directory / tranche["id"])
    ]
    deadline = (
        min((event["recorded_at_unix"] for event in all_events), default=time.time())
        + campaign["max_elapsed_seconds"]
    )
    summary: dict = {"campaign_digest": campaign["digest"], "tranches": [], "stop_reason": None}
    client, sampling = sdk_client_config(), vf.Sampling.model_validate({})
    for tranche in campaign["tranches"]:
        target = directory / tranche["id"]
        manifest = CalibrationManifest.model_validate(tranche["manifest"])
        config = SingleAgentEnvConfig.model_validate(tranche["env_config"])
        remaining = deadline - time.time()
        if remaining <= 0:
            summary["stop_reason"] = "campaign_deadline_reached"
            break
        # A prior failed/interrupted start is consumed and requires diagnosis;
        # neither explicit resume nor a new process silently retries it.
        previous = tuple(_latest(_events(target)).values())
        blocked = any(event["status"] in {"failed", "interrupted", "started"} for event in previous)
        for event in previous:
            if event.get("episode_path"):
                episode, _ = validate_episode(
                    Path(event["episode_path"]), tasks[event["task_name"]]
                )
                blocked = blocked or execution_issue(episode)
        if blocked:
            summary["stop_reason"] = "prior_execution_issue_requires_review"
            break
        try:
            async with asyncio.timeout(remaining):
                events = await run_collection_sdk(
                    inventory,
                    manifest,
                    config,
                    client,
                    sampling,
                    target,
                    attempts_per_task=1,
                    stop_on_execution_error=True,
                )
        except TimeoutError:
            summary["stop_reason"] = "campaign_deadline_reached"
            break
        results = []
        halted = False
        for event in events:
            verification = None
            if event.episode_path:
                episode, _ = validate_episode(
                    Path(event.episode_path), tasks[event.task_name], event
                )
                halted = halted or execution_issue(episode)
                try:
                    verification = verify_retained(
                        Path(event.episode_path), tasks[event.task_name], event, manifest
                    )
                except Exception as error:  # noqa: BLE001 -- preserve unavailable verification and halt
                    verification = {
                        "current_outcome_verified": False,
                        "reason": "verification_failed",
                        "error_type": type(error).__name__,
                    }
                # A valid zero/partial score is ordinary model evidence. Missing
                # finalization, corrupt artifacts or failed scoring are not.
                halted = halted or verification.get("reason") not in {
                    None,
                    "assertions_not_fully_satisfied",
                    "trace_failed_or_stopped",
                }
            halted = halted or event.status != "retained"
            results.append({"attempt": event.model_dump(mode="json"), "verification": verification})
        report = {"manifest_digest": manifest.digest, "attempts": results}
        path = target / "tranche-verification.json"
        if not path.exists():
            _write_native(path, report)
        elif content_digest(json.loads(path.read_bytes())) != content_digest(report):
            raise ValueError("retained tranche verification changed")
        summary["tranches"].append({"id": tranche["id"], "attempts": len(results)})
        if halted or len(results) != len(manifest.tasks):
            summary["stop_reason"] = "execution_issue_requires_review"
            break
    status = directory / f"status-{content_digest(summary)}.json"
    if not status.exists():
        _write_native(status, summary)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("prepare")
    preflight.add_argument("--directory", type=Path, required=True)
    preflight.add_argument("--auth-file", type=Path, required=True)
    preflight.add_argument("--family-splits", type=Path, required=True)
    preflight.add_argument("--tranche-size", type=int, default=20)
    execute = commands.add_parser("run")
    execute.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        campaign = prepare(
            args.directory, args.auth_file, args.family_splits, tranche_size=args.tranche_size
        )
        print(
            json.dumps(
                {
                    "campaign_digest": campaign["digest"],
                    "tasks": 800,
                    "tranches": len(campaign["tranches"]),
                }
            )
        )
    else:
        print(json.dumps(asyncio.run(run(args.directory))))


if __name__ == "__main__":
    main()
