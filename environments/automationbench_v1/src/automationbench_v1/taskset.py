"""AutomationBench datasets and deterministic world-state evaluation on Verifiers v1."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

import verifiers.v1 as vf
from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from automationbench.domains import get_available_domains, get_domain_dataset
from automationbench.rubric.registry import AssertionRegistry
from automationbench.schema.world import WorldState

from .api_tools import AutomationBenchApiToolset
from .limited_tools import (
    AutomationBenchLimitedToolset,
    AutomationBenchLimitedToolsetConfig,
)
from .scoring import ScoreSnapshot, score_world
from .tool_mistakes import (
    EMPTY_RESULT,
    MISTAKES,
    AutomationBenchMistakePenaltyConfig,
    classify_tool_result,
    is_mistake,
)
from .tools import AutomationBenchState, AutomationBenchToolset
from .turn_rewards import (
    PROGRESS_KEY,
    TURN_EVIDENCE_KEY,
    AutomationBenchTurnRewardConfig,
    record_progress,
    turn_evidence,
)

type Domain = Literal["simple", "sales", "marketing", "operations", "support", "finance", "hr"]


def _strip_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_strip_none(item) for item in value if item is not None]
    return value


SPREADSHEET_DISCOVERY_TOOL = "google_drive_find_multiple_files"


def _with_spreadsheet_discovery(
    tools: tuple[str, ...], prompt: Any, initial_state: dict[str, Any]
) -> tuple[str, ...]:
    """Give limited_zapier tasks a way to find the spreadsheets their Sheets tools need.

    The upstream tool lists for every HR task and a few marketing tasks offer only
    Sheets tools that take a spreadsheet ID, while the prompt never names that ID
    and no tool can list spreadsheets, so the policy can only guess IDs. Drive file
    search returns spreadsheets (all of them when the query matches none) and does
    not change any scored state, so adding it makes those tasks solvable without
    touching the benchmark data.
    """

    if not any(tool.startswith("google_sheets_") for tool in tools):
        return tools
    if any(tool.startswith("google_drive_find") for tool in tools):
        return tools
    spreadsheets = initial_state.get("google_sheets", {}).get("spreadsheets", [])
    ids = [str(sheet["id"]) for sheet in spreadsheets if sheet.get("id")]
    text = str(prompt)
    if not ids or all(sheet_id in text for sheet_id in ids):
        return tools
    return (*tools, SPREADSHEET_DISCOVERY_TOOL)


UPSTREAM_TURN_BUDGET_SENTENCE = "You have a budget of ~50 tool-using turns — favor parallel tool calls and avoid duplicate searches. "


def _with_turn_budget(prompt: Any, turn_budget: int) -> Any:
    """Replace the upstream "~50 turns" system sentence with the budget the harness enforces.

    Every upstream domain prompt carries the same sentence, while training harnesses
    stop episodes much earlier. Stating the real budget, and asking for brief thinking,
    keeps the policy from planning for turns or reply length it will never get.
    """

    replacement = (
        f"You have a budget of {turn_budget} tool-using turns — favor parallel tool calls, avoid duplicate "
        "searches, keep your thinking brief, and act as soon as you have enough information. "
    )
    if not isinstance(prompt, list) or not prompt or not isinstance(prompt[0], dict):
        raise ValueError("AutomationBench turn budget requires a message-list prompt")
    system = prompt[0]
    content = system.get("content")
    if (
        system.get("role") != "system"
        or not isinstance(content, str)
        or UPSTREAM_TURN_BUDGET_SENTENCE not in content
    ):
        raise ValueError(
            "AutomationBench system prompt does not contain the upstream turn-budget sentence"
        )
    return [
        {**system, "content": content.replace(UPSTREAM_TURN_BUDGET_SENTENCE, replacement)},
        *prompt[1:],
    ]


def _with_world_time(prompt: Any, declared_time: Any) -> Any:
    """Expose only the explicit simulated clock, never a host-time fallback.

    Preserve the declared timestamp and its precision. Legacy worlds sometimes
    omit an offset; disclose that absence instead of assigning them a timezone.
    This changes public task context and therefore the frozen task digest.
    """
    if not isinstance(declared_time, str) or "T" not in declared_time:
        raise ValueError("world time context requires an explicit ISO datetime")
    try:
        instant = datetime.fromisoformat(declared_time)
    except ValueError as exc:
        raise ValueError("world time context requires an explicit ISO datetime") from exc
    if not isinstance(prompt, list) or not prompt or not isinstance(prompt[0], dict):
        raise ValueError("world time context requires a message-list prompt")
    system = prompt[0]
    content = system.get("content")
    if system.get("role") != "system" or not isinstance(content, str):
        raise ValueError("world time context requires an initial system message")
    precision = (
        "The timestamp's timezone is unspecified; do not infer one or treat it as a globally defined instant. "
        if instant.utcoffset() is None
        else ""
    )
    context = (
        "\n\nSimulation context: For this task, the world time is "
        f"{declared_time}. {precision}"
        "Use this simulated clock for relative dates and deadlines; the host clock "
        "does not define task time. This clock does not specify a business-day "
        "calendar or holidays; use the task's available procedures for those rules."
    )
    return [{**system, "content": content + context}, *prompt[1:]]


def _service_for_name(name: str) -> str | None:
    fields = sorted(
        (str(field) for field in WorldState.model_fields if field != "meta"),
        key=len,
        reverse=True,
    )
    return next((field for field in fields if name == field or name.startswith(field + "_")), None)


def _allowed_services(
    initial_state: dict, assertions: tuple[dict, ...], tools: tuple[str, ...]
) -> list[str]:
    allowed = {key for key in initial_state if key != "meta" and key in WorldState.model_fields}
    for assertion in assertions:
        if service := _service_for_name(str(assertion.get("type", ""))):
            allowed.add(service)
    for tool in tools:
        if service := _service_for_name(tool):
            allowed.add(service)
    return sorted(allowed)


class AutomationBenchData(vf.TaskData):
    domain: Domain
    task_name: str
    initial_state: dict[str, Any]
    assertions: tuple[dict[str, Any], ...]
    zapier_tools: tuple[str, ...]
    # Host-side declared facets. Empty values with not_reviewed status mean unknown.
    workflow: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    guard_patterns: list[str] = Field(default_factory=list)
    task_metadata_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    task_metadata_status: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_metadata_identity(self):
        if self.task_metadata_digest is None and (
            self.workflow or self.capabilities or self.guard_patterns or self.task_metadata_status
        ):
            raise ValueError("task classifications require a bound metadata digest")
        return self

    @model_serializer(mode="wrap")
    def serialize_metadata(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if self.task_metadata_digest is None:
            # Preserve historical task content/hash when this opt-in is unused.
            for name in (
                "workflow",
                "capabilities",
                "guard_patterns",
                "task_metadata_digest",
                "task_metadata_status",
            ):
                data.pop(name, None)
        return data


class AutomationBenchTaskConfig(vf.TaskConfig):
    tools: vf.ToolsetConfig = Field(default_factory=vf.ToolsetConfig)
    toolset: Literal["zapier", "limited_zapier", "api"] = "zapier"
    search_top_k: int = 20
    allowed_tools: tuple[str, ...] = ()
    # None keeps the upstream "~50 turns" system prompt.
    turn_budget: int | None = Field(default=None, gt=0)
    # Explicit, versioned public context; False preserves upstream prompts.
    world_time_context: bool = False
    # Host-side raw material for calibration; never exposed as a tool argument.
    capture_actions: bool = False
    # Offline development candidate; independent native findings, official score unchanged.
    reviewed_hr_assessments: bool = False
    reviewed_simple_assessments: bool = False
    reviewed_suppression_assessments: bool = False
    reviewed_cash_flow_assessments: bool = False
    reviewed_renewal_assessments: bool = False
    reviewed_record_update_assessments: bool = False
    reviewed_access_assessments: bool = False
    manifest_assessments: bool = False
    # None records no per-turn rewards; SAMPO selects them explicitly.
    turn_rewards: AutomationBenchTurnRewardConfig | None = None
    # None adds no penalty; training selects one to discourage tool mistakes.
    mistake_penalty: AutomationBenchMistakePenaltyConfig | None = None


class AutomationBenchTask(
    vf.Task[AutomationBenchData, AutomationBenchState, AutomationBenchTaskConfig]
):
    tools: ClassVar[tuple[type[vf.Toolset], ...]] = cast(
        tuple[type[vf.Toolset], ...], (AutomationBenchToolset,)
    )

    @property
    def key(self) -> str:
        """Use the dataset task name as identity across fresh world instances.

        Some AutomationBench state factories assign new internal record IDs each
        time the taskset is loaded. Those IDs belong in the content hash for
        provenance, but they must not split repeated evaluations of the same
        dataset task into different logical task identities.
        """

        return self.data.task_name

    def tool_servers(self) -> list[vf.Toolset]:
        """Legacy runtime entry point retained during the native API migration."""
        return self.toolsets(
            AutomationBenchTaskConfig.model_validate(
                {
                    **self.config.model_dump(),
                    "allowed_tools": self.data.zapier_tools,
                }
            )
        )

    @classmethod
    def toolsets(cls, task_config: AutomationBenchTaskConfig) -> list[vf.Toolset]:
        if task_config.toolset == "api":
            return cast(list[vf.Toolset], [AutomationBenchApiToolset(task_config.tools)])
        if task_config.toolset == "limited_zapier":
            limited_config = AutomationBenchLimitedToolsetConfig.model_validate(
                {
                    **task_config.tools.model_dump(mode="python"),
                    "allowed_tools": task_config.allowed_tools,
                }
            )
            return cast(list[vf.Toolset], [AutomationBenchLimitedToolset(limited_config)])
        return cast(list[vf.Toolset], [AutomationBenchToolset(task_config.tools)])

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        del runtime
        world = WorldState.model_validate(self.data.initial_state)
        world.meta.allowed_services = _allowed_services(
            self.data.initial_state,
            self.data.assertions,
            self.data.zapier_tools,
        )
        state = cast(AutomationBenchState, trace.state)
        state.world = world.model_dump(mode="json")
        state.initial_state = self.data.initial_state
        state.assertions = self.data.assertions
        state.search_top_k = cast(AutomationBenchTaskConfig, self.config).search_top_k
        state.capture_actions = cast(AutomationBenchTaskConfig, self.config).capture_actions
        if state.capture_actions:
            from .capture import snapshot_world

            snapshot_world(state)

    def _snapshot(self, trace: vf.Trace) -> ScoreSnapshot:
        state = cast(AutomationBenchState, trace.state)
        return score_world(
            world=state.world,
            initial_state=state.initial_state,
            assertions=state.assertions,
        )

    @vf.stop
    async def record_turn_progress(self, trace: vf.Trace) -> bool:
        """Score the live world before each model call; never ends the rollout.

        Every tool call of the previous turn has already updated the world here,
        so the entry after ``trace.num_turns`` turns is that turn's outcome.
        """

        if cast(AutomationBenchTaskConfig, self.config).turn_rewards is not None:
            record_progress(
                trace.info, trace.num_turns, lambda: self._snapshot(trace).partial_credit
            )
        return False

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        del runtime
        state = cast(AutomationBenchState, trace.state)
        if state.capture_actions:
            trace.info["automationbench_capture"] = {
                "schema_version": 1,
                "initial_digest": state.action_initial_digest,
                "snapshots": dict(state.action_snapshots),
                "events": [event.model_dump(mode="json") for event in state.action_events],
                "coverage": {
                    "scope": "successfully synchronized tool state",
                    "failed_mcp_retention": "unqualified",
                    "concurrent_mcp_retention": "unqualified",
                    "native_call_alignment": "unavailable",
                },
            }
        snapshot = self._snapshot(trace)
        trace.info["automationbench"] = {
            "domain": self.data.domain,
            "task_name": self.data.task_name,
            "assertions": list(snapshot.assertion_results),
            "end_state": snapshot.end_state,
        }
        turn_rewards = cast(AutomationBenchTaskConfig, self.config).turn_rewards
        if turn_rewards is not None:
            # A final text-only reply or a turn/token limit sends no further model
            # request, so the last turn's outcome is recorded here.
            record_progress(trace.info, trace.num_turns, lambda: snapshot.partial_credit)
            self._attach_turn_evidence(trace, turn_rewards)

    def _attach_turn_evidence(
        self, trace: vf.Trace, config: AutomationBenchTurnRewardConfig
    ) -> None:
        branches = trace.branches
        if len(branches) != 1:
            return  # Posttrain trains one branch; compacted episodes carry no turn rewards
        nodes = branches[0].nodes
        turns = [
            node.message for node in nodes if node.sampled and node.message.role == "assistant"
        ]
        if not turns:
            return
        tool_results = {
            node.message.tool_call_id: node.message.content
            for node in nodes
            if node.message.role == "tool"
        }
        trace.info[TURN_EVIDENCE_KEY] = turn_evidence(
            trace_id=trace.id,
            turns=turns,
            tool_results=tool_results,
            progress=trace.info[PROGRESS_KEY],
            config=config,
        )
        digests = dict(trace.info.get("posttrain_scorer_digests") or {})
        digests[TURN_EVIDENCE_KEY] = config.scorer_digest
        trace.info["posttrain_scorer_digests"] = digests

    @vf.reward(weight=1.0)
    async def partial_credit(self, trace: vf.Trace) -> float:
        return self._snapshot(trace).partial_credit

    def hooks(self, attr: str):
        """Register the mistake penalty only when a penalty is selected, so tasks
        scored without one keep exactly the official reward set."""
        fns = super().hooks(attr)
        if attr == "reward" and cast(AutomationBenchTaskConfig, self.config).mistake_penalty is None:
            fns = [fn for fn in fns if fn.__name__ != "tool_mistake_penalty"]
        return fns

    @vf.reward(weight=1.0)
    async def tool_mistake_penalty(self, trace: vf.Trace) -> float:
        """Minus the capped mistake penalty when one is selected; zero otherwise."""

        config = cast(AutomationBenchTaskConfig, self.config).mistake_penalty
        if config is None:
            return 0.0
        return -config.penalty(
            sum(count for kind, count in _tool_outcomes(trace).items() if is_mistake(kind))
        )

    @vf.metric
    async def tool_outcome_metrics(self, trace: vf.Trace) -> dict[str, float]:
        outcomes = _tool_outcomes(trace)
        return {
            "tool_mistakes": float(
                sum(count for kind, count in outcomes.items() if is_mistake(kind))
            ),
            "tool_empty_results": float(outcomes.get(EMPTY_RESULT, 0)),
            **{f"tool_{kind}": float(outcomes.get(kind, 0)) for kind in sorted(MISTAKES)},
        }

    @vf.metric
    async def outcome_metrics(self, trace: vf.Trace) -> dict[str, float]:
        snapshot = self._snapshot(trace)
        return {
            "task_completed_correctly": snapshot.task_completed_correctly,
            "assertions_passed": float(snapshot.assertions_passed),
            "assertions_scored": float(snapshot.assertions_scored),
            "assertions_excluded": float(snapshot.assertions_excluded),
        }

    async def validate(self, runtime: vf.Runtime) -> bool:
        del runtime
        world = WorldState.model_validate(self.data.initial_state)
        for assertion in self.data.assertions:
            AssertionRegistry.check(world, dict(assertion))
        return True


def _tool_outcomes(trace: vf.Trace) -> Counter[str]:
    """Count each kind of failed tool result across the episode's sampled branch."""

    outcomes: Counter[str] = Counter()
    for branch in trace.branches[:1]:
        names: dict[str, str | None] = {}
        for node in branch.nodes:
            message = node.message
            if message.role == "assistant":
                for call in getattr(message, "tool_calls", None) or []:
                    names[call.id] = getattr(call, "name", None)
            elif message.role == "tool":
                call_id = getattr(message, "tool_call_id", None)
                kind = classify_tool_result(names.get(call_id or ""), message.content)
                if kind is not None:
                    outcomes[kind] += 1
    return outcomes


class AutomationBenchConfig(vf.TasksetConfig):
    domains: list[Domain] = Field(default_factory=lambda: ["simple"])
    task_names: list[str] = Field(default_factory=list)
    task: AutomationBenchTaskConfig = Field(default_factory=AutomationBenchTaskConfig)
    task_metadata_path: Path | None = None
    task_metadata_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def check_metadata_selection(self):
        if (self.task_metadata_path is None) != (self.task_metadata_digest is None):
            raise ValueError("task metadata requires both path and expected digest")
        return self


class AutomationBenchTaskset(vf.Taskset[AutomationBenchTask, AutomationBenchConfig]):  # pyright: ignore[reportInvalidTypeArguments]
    def load(self) -> list[AutomationBenchTask]:
        available = set(get_available_domains())
        unknown = set(self.config.domains) - available
        if unknown:
            raise ValueError(f"unknown AutomationBench domains: {', '.join(sorted(unknown))}")
        requested_names = self.config.task_names
        if len(requested_names) != len(set(requested_names)):
            raise ValueError("AutomationBench task_names must be unique")
        requested = set(requested_names)
        tasks: list[AutomationBenchTask] = []
        index = 0
        for domain in self.config.domains:
            rows = cast(Iterable[dict[str, Any]], get_domain_dataset(domain))
            for raw in rows:
                task_name = str(raw.get("task") or f"{domain}-{index}")
                if requested and task_name not in requested:
                    index += 1
                    continue
                info = raw.get("info", {})
                if isinstance(info, str):
                    info = json.loads(info)
                info = _strip_none(info)
                prompt = raw.get("prompt")
                if self.config.task.turn_budget is not None:
                    prompt = _with_turn_budget(prompt, self.config.task.turn_budget)
                initial_state = _strip_none(info.get("initial_state", {}))
                if self.config.task.world_time_context:
                    prompt = _with_world_time(
                        prompt, initial_state.get("meta", {}).get("current_time")
                    )
                assertions = tuple(_strip_none(item) for item in info.get("assertions", []))
                zapier_tools = tuple(str(item) for item in info.get("zapier_tools", []))
                if self.config.task.toolset == "limited_zapier":
                    zapier_tools = _with_spreadsheet_discovery(zapier_tools, prompt, initial_state)
                task_type = AutomationBenchTask
                if self.config.task.reviewed_hr_assessments:
                    from .hr_assessments import ReviewedHrTask

                    task_type = ReviewedHrTask
                if self.config.task.reviewed_simple_assessments:
                    from .simple_assessments import ReviewedSimpleTask
                    from .simple_evidence import SUPPORTED

                    if task_name in SUPPORTED:
                        task_type = ReviewedSimpleTask
                if self.config.task.reviewed_suppression_assessments:
                    from .marketing_assessments import ReviewedSuppressionTask
                    from .marketing_evidence import TASK

                    if task_name == TASK:
                        task_type = ReviewedSuppressionTask
                if self.config.task.reviewed_cash_flow_assessments:
                    from .finance_assessments import ReviewedCashFlowTask
                    from .finance_evidence import TASK as CASH_FLOW_TASK

                    if task_name == CASH_FLOW_TASK:
                        task_type = ReviewedCashFlowTask
                if self.config.task.reviewed_renewal_assessments:
                    from .operations_assessments import RENEWAL_TASK, ReviewedRenewalTask

                    if task_name == RENEWAL_TASK:
                        task_type = ReviewedRenewalTask
                if self.config.task.reviewed_record_update_assessments:
                    from .record_assessments import ReviewedRecordUpdateTask
                    from .simple_record_contracts import SUPPORTED as RECORD_UPDATE_TASKS

                    if task_name in RECORD_UPDATE_TASKS:
                        task_type = ReviewedRecordUpdateTask
                if self.config.task.reviewed_access_assessments:
                    from .operations_assessments import ACCESS_TASK, ReviewedAccessTask

                    if task_name == ACCESS_TASK:
                        task_type = ReviewedAccessTask
                if self.config.task.manifest_assessments:
                    from .contracts.loader import supported_tasks
                    from .manifest_assessments import ManifestAssessmentTask

                    if task_name in supported_tasks():
                        task_type = ManifestAssessmentTask
                tasks.append(
                    task_type(
                        AutomationBenchData(
                            idx=index,
                            name=task_name,
                            prompt=prompt,
                            domain=domain,
                            task_name=task_name,
                            initial_state=initial_state,
                            assertions=assertions,
                            zapier_tools=zapier_tools,
                        ),
                        self.config.task.model_copy(update={"allowed_tools": zapier_tools}),
                    )
                )
                index += 1
        found = {task.data.task_name for task in tasks}
        missing = requested - found
        if missing:
            raise ValueError(f"unknown AutomationBench task_names: {', '.join(sorted(missing))}")
        if self.config.task_metadata_path is not None:
            from .task_metadata import attach_task_metadata, load_task_metadata

            metadata = load_task_metadata(
                self.config.task_metadata_path,
                expected_digest=cast(str, self.config.task_metadata_digest),
            )
            for task in tasks:
                task.data = attach_task_metadata(task.data, metadata)
        return tasks


__all__ = ["AutomationBenchTaskset"]
