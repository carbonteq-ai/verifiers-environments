"""Installed candidate manifests for the mix-v2 training tasks.

These drafts are installed for training evidence; independent qualification
review remains separate (tests/test_qualified_manifests.py). Each packaged
file must equal its draft, load through the catalog, and keep every public
binding valid against the training-config task (turn budget 16,
limited_zapier) with the public starting state manifests read.
"""

import hashlib
import json
from functools import cache
from importlib.resources import files
from pathlib import Path

import pytest

from automationbench_v1.contracts import load_task_contract
from automationbench_v1.contracts.engine import binding_reason
from automationbench_v1.public_state import public_initial_state
from automationbench_v1.taskset import AutomationBenchConfig, AutomationBenchTaskset

INSTALLED = json.loads(Path(__file__).with_name("installed_candidate_manifests.json").read_text())
DRAFTS = Path(__file__).resolve().parents[1] / "manifest-drafts" / "tasks"


@cache
def training_tasks():
    config = AutomationBenchConfig(
        domains=["simple", "sales", "marketing", "operations", "support", "finance", "hr"],
        task={"toolset": "limited_zapier", "search_top_k": 20, "turn_budget": 16},
    )
    return {task.data.task_name: task for task in AutomationBenchTaskset(config).load()}


@pytest.mark.parametrize("task_name", sorted(INSTALLED))
def test_installed_candidate_is_the_draft_and_binds_the_training_task(task_name):
    slug, sha = INSTALLED[task_name]
    raw = files("automationbench_v1.contracts").joinpath("tasks", f"{slug}.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == sha
    assert (DRAFTS / task_name / "draft.json").read_bytes() == raw
    contract = load_task_contract(task_name)
    task = training_tasks()[task_name]
    evidence = {"task_evidence": {"prompt": task.data.model_dump(mode="json")["prompt"],
                                  "initial": public_initial_state(task.data.initial_state)}}
    assert binding_reason(evidence, contract) is None
