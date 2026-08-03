"""Pinned procedural Reasoning Gym taskset for Verifiers v1."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any, Literal, cast

import reasoning_gym
import verifiers.v1 as vf
from pydantic import Field, field_validator

REASONING_GYM_COMMIT = "49b07130b3fcd12f2d064bba7c43869543a0e7e7"
DEFAULT_GENERATORS = (
    "leg_counting",
    "products",
    "letter_counting",
    "number_sorting",
    "knights_knaves",
    "syllogism",
    "shortest_path",
    "graph_color",
    "countdown",
    "zebra_puzzles",
)


class ReasoningGymData(vf.TaskData):
    """Wire-stable procedural row with enough data to replay native scoring."""

    generator: str
    seed: int
    ordinal: int
    answer: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_commit: str = REASONING_GYM_COMMIT
    row_digest: str


class ReasoningGymTaskConfig(vf.TaskConfig):
    generator: str
    generator_config: dict[str, Any] = Field(default_factory=dict)
    source_commit: str = REASONING_GYM_COMMIT


class ReasoningGymTask(vf.Task[ReasoningGymData, vf.State, vf.TaskConfig]):
    def _dataset(self):
        task_config = cast(ReasoningGymTaskConfig, self.config)
        config = dict(task_config.generator_config)
        config["seed"] = self.data.seed
        config.setdefault("size", self.data.ordinal + 1)
        return reasoning_gym.create_dataset(task_config.generator, **config)

    def _score(self, trace: vf.Trace) -> float:
        dataset = self._dataset()
        entry = {"answer": self.data.answer, "metadata": self.data.metadata}
        return float(dataset.score_answer_cascade(trace.last_reply, entry))

    @vf.metric
    async def native_score(self, trace: vf.Trace) -> float:
        return self._score(trace)

    @vf.reward
    async def native_reward(self, trace: vf.Trace) -> float:
        return self._score(trace)


class ReasoningGymConfig(vf.TasksetConfig):
    """Deterministic balanced generator selection with disjoint seed namespaces."""

    split: Literal["train", "eval"] = "eval"
    generators: tuple[str, ...] = DEFAULT_GENERATORS
    examples_per_generator: int = Field(100, ge=1, le=100_000)
    train_seed_start: int = Field(default=0, ge=0, le=2**32 - 1)
    eval_seed_start: int = Field(default=1_000_000, ge=0, le=2**32 - 1)
    difficulty: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("generators")
    @classmethod
    def _validate_generators(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("generators must contain at least one generator")
        unknown = sorted(set(values) - set(DEFAULT_GENERATORS))
        if unknown:
            raise ValueError(f"unsupported generators: {unknown}")
        if len(set(values)) != len(values):
            raise ValueError("generators must not contain duplicates")
        return values

    @property
    def seed_start(self) -> int:
        return self.train_seed_start if self.split == "train" else self.eval_seed_start


class ReasoningGymTaskset(vf.Taskset[ReasoningGymTask, ReasoningGymConfig]):
    def _dataset(self, generator: str):
        config = dict(self.config.difficulty.get(generator, {}))
        config["size"] = self.config.examples_per_generator
        config["seed"] = self.config.seed_start
        return reasoning_gym.create_dataset(generator, **config)

    def load(self) -> Iterable[ReasoningGymTask]:
        datasets = {name: self._dataset(name) for name in self.config.generators}
        for ordinal in range(self.config.examples_per_generator * len(self.config.generators)):
            generator = self.config.generators[ordinal % len(self.config.generators)]
            generator_index = ordinal // len(self.config.generators)
            source = datasets[generator][generator_index]
            prompt = str(source["question"])
            answer = source.get("answer")
            answer_text = None if answer is None else str(answer)
            metadata = source.get("metadata", {})
            digest_payload = {
                "generator": generator,
                "seed": self.config.seed_start,
                "ordinal": generator_index,
                "question": prompt,
                "answer": answer_text,
                "metadata": metadata,
                "source_commit": REASONING_GYM_COMMIT,
            }
            row_digest = hashlib.sha256(
                json.dumps(
                    digest_payload, sort_keys=True, separators=(",", ":"), default=str
                ).encode()
            ).hexdigest()
            data = ReasoningGymData(
                idx=ordinal,
                name=f"{self.config.split}:{generator}:{generator_index}",
                prompt=prompt,
                generator=generator,
                seed=self.config.seed_start,
                ordinal=generator_index,
                answer=answer_text,
                metadata=metadata,
                row_digest=row_digest,
            )
            task_config = ReasoningGymTaskConfig(
                generator=generator,
                generator_config=self.config.difficulty.get(generator, {}),
            )
            yield ReasoningGymTask(data, task_config)


__all__ = [
    "DEFAULT_GENERATORS",
    "REASONING_GYM_COMMIT",
    "ReasoningGymConfig",
    "ReasoningGymData",
    "ReasoningGymTask",
    "ReasoningGymTaskConfig",
    "ReasoningGymTaskset",
]
