from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import verifiers.v1 as vf
from verifiers.v1.utils.loaders import load_environment, load_judge, resolve_env_config

from automationbench_v1.judge import AutomationBenchTurnJudge, TurnQualityConfig
from automationbench_v1.taskset import AutomationBenchConfig, AutomationBenchTaskset
from automationbench_v1.tools import AutomationBenchState

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_distribution_metadata_is_standalone_and_pinned() -> None:
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((PACKAGE_ROOT / "uv.lock").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "automationbench-v1"
    assert pyproject["project"]["requires-python"] == ">=3.12,<3.14"
    assert not any("posttrain" in item for item in pyproject["project"]["dependencies"])
    assert not any(
        "carbonteq-automation-bench" in item for item in pyproject["project"]["dependencies"]
    )
    assert (PACKAGE_ROOT / "src/automationbench/schema/world.py").is_file()
    assert (PACKAGE_ROOT / "src/automationbench/tools/zapier/meta.py").is_file()
    assert not any(package["name"] == "carbonteq-automation-bench" for package in lock["package"])
    verifiers = next(package for package in lock["package"] if package["name"] == "verifiers")
    assert verifiers["source"]["git"].endswith(
        "?rev=1f6793f7d46e8a650a54b2a585193b4010578fa6#1f6793f7d46e8a650a54b2a585193b4010578fa6"
    )


def test_declarative_env_config_discovers_loads_and_scores_real_task() -> None:
    config = resolve_env_config(
        {
            "taskset": {"id": "automationbench-v1", "domains": ["simple"]},
            "agent": {"harness": {"id": "null"}, "runtime": {"type": "subprocess"}},
        }
    )
    environment = load_environment(config)
    assert isinstance(environment.taskset, AutomationBenchTaskset)
    assert isinstance(environment.taskset.config, AutomationBenchConfig)

    task = next(iter(environment.taskset.load()))
    assert task.data.name == "simple.email_sf_contact_phone_update"

    trace = vf.Trace(
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        task=vf.TraceTask(type=type(task).__name__, data=task.data),
        state=AutomationBenchState(),
    )
    asyncio.run(task.setup(trace, None))  # type: ignore[arg-type]
    asyncio.run(task.score(trace))
    assert trace.reward == 0.0
    assert trace.rewards["partial_credit"] is not None
    assert trace.rewards["partial_credit"].score == 0.0
    assert trace.rewards["partial_credit"].weight == 1.0
    assert trace.metrics["task_completed_correctly"] == 0.0


def _dimensions(score: float) -> dict[str, float]:
    return {
        "understanding_planning": score,
        "logical_correctness": score,
        "evidence_state_grounding": score,
        "verification_self_correction": score,
        "progress_efficiency": score,
    }


def test_native_turn_judge_is_discovered_and_keeps_task_reward_separate(monkeypatch):
    config = TurnQualityConfig(
        id="automationbench-v1",
        code_revision="a" * 40,
        model_revision="b" * 40,
        input_budget_tokens=22_528,
        model="hosted-judge",
        base_url="http://127.0.0.1:1/v1",
    )
    judge: Any = load_judge(config)
    assert isinstance(judge, AutomationBenchTurnJudge)
    trace = SimpleNamespace(
        id="trace",
        info={},
        branches=[
            SimpleNamespace(
                nodes=[
                    SimpleNamespace(
                        message=vf.AssistantMessage(content="Act."), sampled=True, mask=[True]
                    ),
                    SimpleNamespace(
                        message=vf.AssistantMessage(content="Verify."), sampled=True, mask=[True]
                    ),
                ]
            )
        ],
    )
    outputs = [
        "not JSON",
        json.dumps(
            {
                "turns": [
                    {
                        "turn_id": "assistant-1",
                        "dimensions": _dimensions(0.75),
                        "erroneous": False,
                        "reason": "Verified.",
                    },
                    {
                        "turn_id": "assistant-0",
                        "dimensions": _dimensions(0.25),
                        "erroneous": True,
                        "reason": "Wrong action.",
                    },
                ]
            }
        ),
    ]

    async def complete(*args, **kwargs):
        return vf.JudgeResponse(text=outputs.pop(0))

    monkeypatch.setattr(judge, "complete", complete)
    assert asyncio.run(cast(Any, judge).score(None, trace)) == {}
    evidence = trace.info["posttrain_turn_rewards"]
    assert [item["components"][0]["value"] for item in evidence["assessments"]] == [0.25, 0.75]
    assert evidence["erroneous_turn_ids"] == ["assistant-0"]
    assert [item["status"] for item in trace.info["posttrain_turn_rewards_attempts"]] == [
        "invalid_output",
        "valid",
    ]
    changed: Any = AutomationBenchTurnJudge(
        config.model_copy(update={"rubric": "different rubric"})
    )
    assert changed.scorer_digest != judge.scorer_digest
    with pytest.raises(ValueError, match="another scorer"):
        asyncio.run(changed.score(None, trace))

    second: Any = AutomationBenchTurnJudge(
        config.model_copy(update={"annotation_key": "second", "model": "another-model"})
    )
    outputs.append(
        json.dumps(
            {
                "turns": [
                    {
                        "turn_id": name,
                        "dimensions": _dimensions(0.5),
                        "erroneous": False,
                        "reason": "Independent judgment.",
                    }
                    for name in ("assistant-0", "assistant-1")
                ]
            }
        )
    )
    monkeypatch.setattr(second, "complete", complete)
    assert asyncio.run(second.score(None, trace)) == {}
    assert trace.info["posttrain_scorer_digests"] == {
        "posttrain_turn_rewards": judge.scorer_digest,
        "second": second.scorer_digest,
    }
    assert trace.info["posttrain_turn_rewards"] == evidence
    with pytest.raises(ValueError, match="already exist"):
        asyncio.run(cast(Any, judge).score(None, trace))
