"""Explicit, resumable signed-in SDK reference collection for AutomationBench.

Run with ``python -m automationbench_v1.calibration.cli``. Task names are required;
the command never defaults to collecting the whole benchmark.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import cast

import verifiers.v1 as vf
from verifiers.v1.envs.single_agent.env import SingleAgentEnvConfig
from verifiers.v1.utils.loaders import resolve_env_config

from ..taskset import AutomationBenchConfig
from .collector import _write_native
from .inventory import TaskInventory, content_digest, freeze_inventory
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


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--task", action="append", required=True, dest="tasks")
    result.add_argument("--directory", type=Path, required=True)
    result.add_argument("--auth-file", type=Path, required=True)
    result.add_argument("--concurrency", type=int, required=True)
    result.add_argument("--output-budget", type=int, required=True)
    result.add_argument("--sdk-timeout", type=float, required=True)
    result.add_argument("--attempt-timeout", type=float, required=True)
    result.add_argument("--total-timeout", type=float, required=True)
    result.add_argument("--resume", action="store_true")
    result.add_argument(
        "--world-time-context",
        action="store_true",
        help="Expose the fixture's declared world time in the public task context",
    )
    return result


def configuration(args: argparse.Namespace) -> SingleAgentEnvConfig:
    if len(args.tasks) != len(set(args.tasks)):
        raise ValueError("duplicate task names")
    if not 1 <= args.concurrency <= len(args.tasks):
        raise ValueError("concurrency must be bounded by the explicit task selection")
    if args.output_budget != 16384:
        raise ValueError("qualified SDK route requires an output threshold of 16384")
    if not 0 < args.sdk_timeout < args.attempt_timeout <= args.total_timeout:
        raise ValueError("require SDK timeout < attempt timeout <= total timeout")
    auth = args.auth_file.expanduser().resolve()
    if not auth.is_file():
        raise ValueError("protected signed-in auth file is missing")
    return cast(
        SingleAgentEnvConfig,
        resolve_env_config(
            {
                "interception": {"type": "server"},
                "max_concurrent_agents": 1,
                "retries": {"max_retries": 0},
                "taskset": {
                    "id": "automationbench-v1",
                    "domains": list(dict.fromkeys(name.partition(".")[0] for name in args.tasks)),
                    "task_names": args.tasks,
                    "task": {
                        "capture_actions": True,
                        "turn_budget": None,
                        "world_time_context": args.world_time_context,
                        "tools": {"colocated": False, "runtime": {"type": "subprocess"}},
                    },
                },
                "agent": {
                    "max_turns": 1,
                    "max_output_tokens": args.output_budget,
                    "retries": {"max_retries": 0},
                    "runtime": {"type": "subprocess"},
                    "timeout": {"setup": 300, "rollout": args.sdk_timeout, "scoring": 60},
                    "harness": {
                        "id": "codex-sdk",
                        "auth_file": str(auth),
                        "timeout": args.sdk_timeout,
                        "output_budget": args.output_budget,
                        "approved_mcp_tools": {"": ["execute_tool", "search_tools"]},
                    },
                },
            }
        ),
    )


async def run(args: argparse.Namespace) -> dict:
    config = configuration(args)
    client, sampling = sdk_client_config(), vf.Sampling.model_validate({})
    directory = args.directory.expanduser().resolve()
    limits = CollectionLimits(
        max_concurrent=args.concurrency,
        max_attempts_per_task=1,
        max_total_attempts=len(args.tasks),
        max_infrastructure_retries=0,
        max_elapsed_seconds=args.total_timeout,
        attempt_timeout_seconds=args.attempt_timeout,
        max_turns=1,
        max_output_tokens=args.output_budget,
        cost_measurement="unavailable",
    )
    if args.resume:
        inventory = TaskInventory.model_validate_json((directory / "inventory.json").read_bytes())
        manifest = CalibrationManifest.model_validate_json(
            (directory / "manifest.json").read_bytes()
        )
        if [task.task_name for task in manifest.tasks] != args.tasks or manifest.limits != limits:
            raise ValueError("resume task selection or limits differ from frozen manifest")
        if native_binding(config, client, sampling) != manifest.native_config:
            raise ValueError("resume native configuration differs from frozen manifest")
        if manifest.scorer_revision != scorer_fingerprint():
            raise ValueError("resume scorer identity changed")
        current = await asyncio.to_thread(source_identity)
        if current != inventory.source_identity:
            raise ValueError("resume loaded source identity changed")
    else:
        if directory.exists():
            raise ValueError("fresh collection requires a new directory; use explicit --resume")
        current = await asyncio.to_thread(source_identity)
        inventory = freeze_inventory(
            cast(AutomationBenchConfig, config.taskset), source_identity=current
        )
        # Exact names, including factory failures/missing names, are checked before dispatch.
        tasks = {task.task_name: task for task in inventory.tasks}
        if set(tasks) != set(args.tasks):
            raise ValueError("resolved task selection differs from requested task names")
        manifest = plan_collection(
            inventory,
            selections=tuple(
                TaskSelection(
                    task_name=name, task_digest=tasks[name].digest, family=name, split="development"
                )
                for name in args.tasks
            ),
            route_identity=SIGNED_IN_ROUTE_IDENTITY,
            native_config=native_binding(config, client, sampling),
            scorer_revision=scorer_fingerprint(),
            limits=limits,
        )
        validate_sdk_binding(inventory, manifest, config, client, sampling)
        captured = await asyncio.to_thread(source_identity, directory / "source-snapshot.zip")
        if captured != current:
            raise ValueError("source changed during preparation; no attempts dispatched")
        # Persist the frozen bank before starting a service or recording any attempt.
        _write_native(directory / "inventory.json", inventory.model_dump(mode="json"))
        _write_native(directory / "manifest.json", manifest.model_dump(mode="json"))
    events = await run_collection_sdk(
        inventory,
        manifest,
        config,
        client,
        sampling,
        directory,
        attempts_per_task=1,
        stop_on_execution_error=True,
    )
    tasks = {task.task_name: task for task in inventory.tasks}
    results = []
    for event in events:
        item = {"attempt": event.model_dump(mode="json"), "verification": None}
        if event.episode_path:
            try:
                item["verification"] = verify_retained(
                    Path(event.episode_path), tasks[event.task_name], event, manifest
                )
            except Exception as error:  # noqa: BLE001 -- failed verification is retained evidence
                item["verification"] = {
                    "current_outcome_verified": False,
                    "error_type": type(error).__name__,
                    "reason": str(error),
                }
        results.append(item)
    summary = {
        "manifest_digest": manifest.digest,
        "inventory_digest": inventory.digest,
        "attempts": results,
        "scope": "reference collection; reward and budget qualification pending",
    }
    summary_path = directory / "collection-summary.json"
    if summary_path.exists():
        if content_digest(json.loads(summary_path.read_bytes())) != content_digest(summary):
            _write_native(directory / f"collection-summary-{content_digest(summary)}.json", summary)
    else:
        _write_native(summary_path, summary)
    return summary


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    summary = asyncio.run(run(args))
    print(
        json.dumps(
            {
                "directory": str(args.directory.resolve()),
                "manifest_digest": summary["manifest_digest"],
                "attempts": len(summary["attempts"]),
            }
        )
    )


if __name__ == "__main__":
    main()
