"""Public-input authoring must not leak answers or quietly change the frozen tasks."""

import hashlib
import json

import pytest

from automationbench_v1.calibration.manifest_authoring import build_authoring_batches


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
