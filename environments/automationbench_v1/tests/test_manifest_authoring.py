"""Public-input authoring must not leak answers or quietly change the frozen tasks."""

import hashlib
import json

import pytest

from automationbench_v1.calibration.manifest_authoring import (
    build_authoring_batches,
    build_public_authoring_batches,
)


def selection(tmp_path, count=12):
    entries = []
    for index in range(count):
        domain = ("finance", "hr", "support")[index % 3]
        name = f"{domain}.task{index}"
        data = {
            "task_name": name, "domain": domain, "prompt": [{"role": "user", "content": "Public request"}],
            "initial_state": {"gmail": {"messages": []}}, "zapier_tools": ["gmail_send_email"],
            "assertions": [{"private": "HIDDEN_ASSERTION"}], "answer": "HIDDEN_ANSWER",
            "artifacts": {"private": "HIDDEN_ARTIFACT"},
        }
        path = tmp_path / f"{index}.json"
        path.write_text(json.dumps({"traces": [{"id": f"trace{index}", "task": {"data": data}}]}))
        entries.append({
            "task_name": name, "domain": domain, "family": "fixture", "split": "development",
            "source_episode_path": str(path), "source_episode_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    return {"tasks": entries}


def test_batches_cover_once_balance_categories_and_exclude_hidden_material(tmp_path):
    chosen = selection(tmp_path)
    batches = build_authoring_batches(chosen)
    assert [len(batch["tasks"]) for batch in batches] == [10, 2]
    assert set(batches[0]["domain_counts"]) == {"finance", "hr", "support"}
    names = [task["task_name"] for batch in batches for task in batch["tasks"]]
    assert len(names) == len(set(names)) == 12
    assert all(batch["accepted_manifest_count"] == 0 for batch in batches)
    payload = json.dumps(batches)
    assert "HIDDEN" not in payload and '"assertions"' not in payload and '"answer"' not in payload
    assert build_authoring_batches(chosen) == batches


@pytest.mark.parametrize("mutation", ["hash", "reserved", "duplicate", "identity"])
def test_changed_or_disallowed_source_cannot_enter_review_batch(tmp_path, mutation):
    chosen = selection(tmp_path, 2)
    if mutation == "hash":
        chosen["tasks"][0]["source_episode_sha256"] = "0" * 64
    elif mutation == "reserved":
        chosen["tasks"][0]["split"] = "reserved"
    elif mutation == "duplicate":
        chosen["tasks"].append(chosen["tasks"][0])
    else:
        chosen["tasks"][0]["domain"] = "wrong"
    with pytest.raises(ValueError):
        build_authoring_batches(chosen)


@pytest.mark.parametrize("limit", [True, 0, 101, 10.0])
def test_batch_limit_is_strict_and_bounded(tmp_path, limit):
    with pytest.raises(ValueError, match="bounded_integer"):
        build_authoring_batches(selection(tmp_path, 1), batch_size=limit)


def public_selection():
    return {"tasks": [{"task_name": "support.fixture", "domain": "support", "family": "fixture", "split": "reserved",
        "public_input": {"task_name": "support.fixture", "domain": "support",
            "prompt": [{"role": "user", "content": "Public request"}],
            "initial_state": {"gmail": {"messages": []}}, "zapier_tools": ["gmail_send_email"]}}]}


def test_public_only_reserved_authoring_preserves_split_without_trace_or_eligibility():
    selection = public_selection()
    batches = build_public_authoring_batches(selection)
    task = batches[0]["tasks"][0]
    assert task["split"] == "reserved" and task["training_eligibility"] == "not_granted"
    assert task["replay_status"] == "unavailable_no_recorded_reference"
    assert "qualification_source" not in task and "episode_path" not in json.dumps(batches)
    assert build_public_authoring_batches(selection) == batches
    selection["tasks"][0]["public_input"]["initial_state"]["gmail"]["messages"].append({"id": "later"})
    assert task["public_input"]["initial_state"]["gmail"]["messages"] == []


@pytest.mark.parametrize("where,key", [("entry", "source_episode_path"), ("entry", "official_rewards"),
    ("public", "assertions"), ("public", "answer"), ("public", "artifacts")])
def test_public_only_authoring_rejects_reference_and_hidden_material(where, key):
    selection = public_selection()
    entry = selection["tasks"][0]
    (entry if where == "entry" else entry["public_input"])[key] = "HIDDEN"
    with pytest.raises(ValueError, match="only_public_fields"):
        build_public_authoring_batches(selection)


@pytest.mark.parametrize("mutation", ["duplicate", "split", "identity", "tools"])
def test_public_only_authoring_rejects_invalid_identity_split_or_tools(mutation):
    selection = public_selection()
    entry = selection["tasks"][0]
    if mutation == "duplicate":
        selection["tasks"].append(entry)
    elif mutation == "split":
        entry["split"] = "training"
    elif mutation == "identity":
        entry["public_input"]["task_name"] = "wrong"
    else:
        entry["public_input"]["zapier_tools"] = [None]
    with pytest.raises((ValueError, TypeError)):
        build_public_authoring_batches(selection)


@pytest.mark.parametrize("limit", [True, 0, 101, 10.0])
def test_public_only_batch_limit_remains_strict(limit):
    with pytest.raises(ValueError, match="bounded_integer"):
        build_public_authoring_batches(public_selection(), batch_size=limit)


def test_public_only_batches_preserve_exact_ownership_order_and_split():
    entries = []
    for index in range(12):
        entry = public_selection()["tasks"][0]
        domain = "support" if index % 2 else "simple"
        name = f"{domain}.fixture{index}"
        entry.update(task_name=name, domain=domain, split="development" if index % 2 else "reserved")
        entry["public_input"].update(task_name=name, domain=domain)
        entries.append(entry)
    batches = build_public_authoring_batches({"tasks": entries})
    assert [len(batch["tasks"]) for batch in batches] == [10, 2]
    tasks = [task for batch in batches for task in batch["tasks"]]
    assert len({task["task_name"] for task in tasks}) == 12
    assert [task["task_name"] for task in tasks] == [entry["task_name"] for entry in entries]
    assert all(task["split"] == ("reserved" if task["domain"] == "simple" else "development") for task in tasks)
