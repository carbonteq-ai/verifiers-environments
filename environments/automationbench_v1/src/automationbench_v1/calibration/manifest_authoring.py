"""Prepare bounded public-input review batches; never infer or accept reward rules."""

import hashlib
import json
from collections import Counter, deque
from pathlib import Path

from ..capture import canonical_json


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def build_authoring_batches(selection: dict, *, batch_size: int = 10) -> tuple[dict, ...]:
    """Round-robin categories, preserving frozen within-category selection order.

    Public prompt/world/tools form the authoring input. Hidden assertions,
    answers and scorer outputs never enter it. Recorded episode references stay
    separate so later qualification can inspect both successes and failures.
    This prepares proposals, not installed manifests or task eligibility.
    """
    if type(batch_size) is not int or not 1 <= batch_size <= 100:
        raise ValueError("authoring_batch_size_requires_bounded_integer")
    entries = selection.get("tasks")
    if not isinstance(entries, list) or not entries:
        raise ValueError("authoring_selection_requires_tasks")
    identities, queues = set(), {}
    for entry in entries:
        if entry.get("split") != "development":
            raise ValueError("authoring_reserved_task_rejected")
        name, domain = entry.get("task_name"), entry.get("domain")
        if type(name) is not str or not name or type(domain) is not str or not domain:
            raise ValueError("authoring_task_identity_invalid")
        if name in identities:
            raise ValueError("authoring_duplicate_task")
        identities.add(name)
        raw = Path(entry["source_episode_path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["source_episode_sha256"]:
            raise ValueError("authoring_episode_hash_mismatch")
        episode = json.loads(raw)
        traces = episode.get("traces")
        if not isinstance(traces, list) or not traces:
            raise ValueError("authoring_episode_requires_trace")
        inputs = []
        for trace in traces:
            data = trace["task"]["data"]
            if (data.get("task_name"), data.get("domain")) != (name, domain):
                raise ValueError("authoring_episode_task_mismatch")
            public = {key: data[key] for key in ("task_name", "domain", "prompt", "initial_state", "zapier_tools")}
            if not isinstance(public["initial_state"], dict) or not isinstance(public["prompt"], list):
                raise TypeError("authoring_public_inputs_invalid")
            inputs.append(public)
        if any(canonical_json(public) != canonical_json(inputs[0]) for public in inputs[1:]):
            raise ValueError("authoring_public_inputs_conflict")
        task = {
            "task_name": name, "domain": domain, "family": entry["family"],
            "public_input": inputs[0], "public_input_sha256": digest(inputs[0]),
            "qualification_source": {
                "episode_path": entry["source_episode_path"],
                "episode_sha256": entry["source_episode_sha256"],
                "trace_ids": [trace["id"] for trace in traces],
            },
            "status": "awaiting_public_policy_review",
        }
        queues.setdefault(domain, deque()).append(task)
    ordered = []
    while any(queues.values()):
        for domain in sorted(queues):
            if queues[domain]:
                ordered.append(queues[domain].popleft())
    batches = []
    for offset in range(0, len(ordered), batch_size):
        tasks = ordered[offset:offset + batch_size]
        batches.append({
            "schema_version": 1, "batch_number": len(batches) + 1,
            "selection_sha256": digest(selection), "batch_size_limit": batch_size,
            "tasks": tasks, "domain_counts": dict(Counter(task["domain"] for task in tasks)),
            "stage": "proposal_only", "accepted_manifest_count": 0,
        })
    return tuple(batches)
