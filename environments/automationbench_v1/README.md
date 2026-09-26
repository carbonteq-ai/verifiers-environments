# AutomationBench v1 environment

CarbonTeq's standalone Verifiers v1 adapter for Zapier AutomationBench 1.0.5.
The adapter preserves the existing task, tool, state, scoring, and trace
contracts from the former in-repository package while moving its release
lifecycle to `carbonteq-ai/verifiers-environments`.

The upstream-compatible distribution is pinned as
`carbonteq-automation-bench==1.0.5.post1`, published from CarbonTeq
AutomationBench commit `908db2abd4a868acc37ab0850474bff653bea25c`. That fork
maintains the compatibility delta from upstream Zapier commit
`a321764ace3cfbe42289e6a13abef2f0f4f56fad` (maintained fork lineage commit
`d54dbebabdba6c6eda201694aee8ddcf36ccfc51`). The package's lock records the
exact Verifiers commit and resolved dependency graph.

The wheel vendors the CarbonTeq AutomationBench fork at commit
`908db2abd4a868acc37ab0850474bff653bea25c`. Vendoring keeps this standalone
Verifiers environment installable without a second VCS dependency and lets
posttrain job packaging produce one hash-locked runtime closure. The vendored
source remains under the fork's original `automationbench` import namespace;
the v1 adapter is the only public environment namespace.

The adapter owns only the v1 boundary:

- typed task data and per-rollout world state;
- the canonical Zapier meta-tool interface (`search_tools` and
  `execute_tool`);
- an optional API-mode toolset (`api_search`, `api_fetch`, and
  `base64_encode`);
- a task-filtered `limited_zapier` toolset for smaller-policy curricula;
- deterministic final-state assertion scoring with dense
  `partial_credit` and strict `task_completed_correctly` metrics; and
- trace metadata containing assertion results and the final world state; and
- optional per-turn rewards for step-level training (see below).

The dependency is the public CarbonTeq AutomationBench fork at immutable merge
commit `908db2abd4a868acc37ab0850474bff653bea25c`; no private package index or
credential is required to build this environment library. The package is
independent of posttrain, Trackio, trainers, serving systems, and the other
environment packages.

## Per-turn rewards

Setting `task.turn_rewards` (for example `{tool_failure_penalty: 0.05}`) makes
each rollout record how its tool calls change the task's partial credit. Before
every model call the task scores the live world and appends the result to
`trace.info["automationbench_turn_progress"]`; `finalize` adds the final state.
The measurement has to be live: record IDs are generated with `uuid4`, so
replaying a finished episode's tool calls would not rebuild its world.

`finalize` then writes `trace.info["posttrain_turn_rewards"]`, Posttrain's turn
evidence for projection `assistant-turns@1`: one assessment per sampled
assistant turn (`assistant-0`, `assistant-1`, ...) with `turn_reward` = the change
in partial credit the turn caused minus `tool_failure_penalty` for each of its
tool calls whose result reports a failure (an `error` key, `"success": false`, a
raised tool, or a harness `error:` message), plus the `assertion_progress` and
`tool_failures` components. Over an episode the rewards sum to the final
partial credit minus the untouched world's credit, minus the penalties. A turn
whose world cannot be scored keeps the last scored credit. The scorer digest in
`trace.info["posttrain_scorer_digests"]["posttrain_turn_rewards"]` changes with
the penalty. Unset, nothing is recorded and scoring is unchanged. The last
turn of an episode stopped by the turn limit has no committed tool results, so
its failures are not counted.

## Validate and run

### Native v0.3.2 development runtime and episode-judge release candidate

Version 0.4.0 uses CarbonTeq's maintained Verifiers v0.3.2 development fork at
`1f6793f7d46e8a650a54b2a585193b4010578fa6`, based on current upstream main.
The fork adds host-owned policy-client injection while preserving upstream
client resolution by default. Do not publish or claim the candidate as fully
qualified until live managed qualification passes from the immutable release
commit.

The optional exported `AutomationBenchEpisodeJudge` is discovered through
native `taskset.task.judges` with id `automationbench-v1`. Its
`EpisodeQualityConfig` requires immutable `code_revision` and
`model_revision`, plus the composition host's `model`, `base_url`,
`api_key_var`, and sampling configuration. It has bounded attempts and a
per-attempt timeout, always assesses the complete trajectory, and preserves raw
judge outputs and input/scorer digests in trace info. It never loads a model or
chooses a device.

There is one versioned rubric and one output contract. The judge reconstructs
material task requirements, then emits seven independent episode components:
five reasoning-quality dimensions, action quality, and answer quality. Those
components are stored under `info.episode_reward/*` for an explicit consumer
projection; they are not averaged inside the environment and do not implicitly
change AutomationBench's native `partial_credit` reward. The model-facing wire
schema uses bounded integer message indexes, which are validated and normalized
to stable native-trace message IDs before admission. Repeated valid indexes are
collapsed in first-seen order because duplicate citations add no meaning;
negative or out-of-range indexes remain invalid and cannot become rewards.

The former turn-level rubric, turn annotations, prefix/retrospective switch,
and dual turn/episode schema are not part of the v0.4 public API. Invalid,
timed-out, or structurally inconsistent assessments exhaust a bounded retry and
never become a manufactured zero. Twenty-one candidate tests cover these
contracts. The all-six-wheel compatibility gate passes locally; live managed
qualification from the immutable release commit remains open.

```bash
uv lock --check
uv sync --locked --python 3.12
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
uv build --wheel
```

The endpoint-based Verifiers CLI can run a single deterministic task once an
OpenAI-compatible endpoint is available:

```bash
LOCAL_INFERENCE_API_KEY=EMPTY \
uv run eval automationbench-v1 \
  --agent.harness.id null --agent.runtime.type subprocess \
  --taskset.domains simple \
  --model Qwen/Qwen3.5-2B \
  --client.base-url http://127.0.0.1:8000/v1 \
  --client.api-key-var LOCAL_INFERENCE_API_KEY \
  --num-tasks 1 --num-rollouts 1 --max-concurrent 1 \
  --sampling.max-tokens 2048 --sampling.temperature 0 \
  --agent.max-turns 50 --agent.max-total-tokens 8192 \
  --rich false --push false --output-dir /tmp/automationbench-v1
```

Native Verifiers traces remain the replay authority. A framework composition
may consume this wheel, but the environment itself has no framework or
tracking dependency.
