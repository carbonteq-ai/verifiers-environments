"""Offline deterministic reassessment through the native task scoring path.

Composition supplies the trusted task class and its accepted source digest. This
adapter never imports a producer named in an artifact or invokes a model client.
It establishes reproducibility, not completeness of a task's reward contract.
"""

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import verifiers.v1 as vf

from ..hr_assessments import ReviewedHrTask
from ..taskset import AutomationBenchData, AutomationBenchTaskConfig
from ..tools import AutomationBenchState
from .eligibility import ReassessmentReplay, TaskRewardContract
from .inventory import FrozenTask


class TaskScoreReassessmentVerifier:
    """Replay a trusted deterministic task on detached native material.

    The synchronous eligibility interface may run inside an asyncio collector.
    In that case a bounded one-worker bridge owns the offline scoring event loop;
    it does not introduce concurrent inference or automatic retries. Composition
    should cache accepted replays under a freshly checked full source closure.
    """

    def __init__(self, task_class: type[ReviewedHrTask], *, source_digest: str):
        if not re.fullmatch(r"[0-9a-f]{64}", source_digest):
            raise ValueError("reassessment_source_digest_invalid")
        self.task_class = task_class
        self.source_digest = source_digest
        self.producer_id = task_class.producer_id
        self.producer_revision = task_class.producer_revision
        self.rubric_revision = task_class.policy_revision

    async def replay_async(
        self,
        *,
        episode: vf.WireEpisode,
        task: FrozenTask,
        contract: TaskRewardContract,
        request: vf.AssessmentRun,
    ) -> ReassessmentReplay:
        frozen = FrozenTask.model_validate_json(task.model_dump_json())
        if (contract.task_name, contract.task_digest) != (frozen.task_name, frozen.digest):
            raise ValueError("reassessment_task_contract_mismatch")
        if (request.producer_id, request.producer_revision, request.rubric_revision) != (
            self.producer_id,
            self.producer_revision,
            self.rubric_revision,
        ):
            raise ValueError("reassessment_producer_revision_mismatch")
        detached = vf.WireEpisode.model_validate_json(episode.model_dump_json())
        if detached.task.data.model_dump(mode="json") != frozen.data:
            raise ValueError("reassessment_original_task_mismatch")
        if len(detached.traces) != 1:
            raise ValueError("reassessment_requires_one_original_trace")
        trace = cast(vf.Trace, detached.traces[0])
        if trace.episode_id != detached.id or trace.task != detached.task:
            raise ValueError("reassessment_original_trace_lineage_mismatch")
        retained = trace.info.get("automationbench", {})
        if "end_state" not in retained:
            raise ValueError("reassessment_final_world_unavailable")
        data = AutomationBenchData.model_validate(frozen.data)
        scored = self.task_class(data, AutomationBenchTaskConfig.model_validate(frozen.config))
        trace.state = AutomationBenchState(
            world=retained["end_state"],
            initial_state=data.initial_state,
            assertions=data.assertions,
            artifacts=dict(episode.traces[0].state.artifacts),
        )
        # Reproduce the producer, rather than trusting retained assessment output.
        trace.assessment_batches = []
        trace.credit_assignments = []
        trace.assessment_errors = []
        trace.credit_errors = []
        await scored.score(trace)
        if trace.assessment_errors or trace.credit_errors:
            raise ValueError("reassessment_native_scoring_failed")
        batches = [
            batch
            for batch in trace.assessment_batches
            if batch.run.status == "complete" and batch.run.producer_id == self.producer_id
        ]
        if len(batches) != 1:
            raise ValueError("reassessment_completed_batch_unresolved")
        terminal = {}
        for assignment in trace.credit_assignments:
            terminal[assignment.request.attempt_id] = assignment
        if any(assignment.status != "complete" for assignment in terminal.values()):
            raise ValueError("reassessment_credit_finalization_incomplete")
        return ReassessmentReplay(
            batch=batches[0],
            credit_assignments=tuple(assignment for assignment in terminal.values()),
        )

    def replay(self, *, episode, task, contract, request) -> ReassessmentReplay:
        def score():
            return asyncio.run(
                self.replay_async(
                    episode=episode,
                    task=task,
                    contract=contract,
                    request=request,
                )
            )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return score()
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="vf-reassessment") as executor:
            return executor.submit(score).result()
