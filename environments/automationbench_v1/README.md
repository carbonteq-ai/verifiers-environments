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
- trace metadata containing assertion results and the final world state.

The dependency is the public CarbonTeq AutomationBench fork at immutable merge
commit `908db2abd4a868acc37ab0850474bff653bea25c`; no private package index or
credential is required to build this environment library. The package is
independent of posttrain, Trackio, trainers, serving systems, and the other
environment packages.

## Validate and run

### Native v0.3.1 runtime and turn-judge release candidate

Version 0.3.0 migrates native `Task.toolsets(config)` and `Toolset.register`,
pins the package and lock to CarbonTeq's maintained Verifiers v0.3.1 fork at
`36eac9d5e04ef29b584b6fa4f027af00cd76ea19`, based on current upstream main,
and adds the optional public
turn-quality judge described below. The fork adds host-owned policy-client
injection while preserving upstream client resolution by default. Do not
publish or claim the candidate as qualified until the all-six-wheel
compatibility gate and live managed qualification have passed from the
immutable release commit.

The optional exported `AutomationBenchTurnJudge` is discovered through native
`taskset.task.judges` with id `automationbench-v1`. Its
`TurnQualityConfig` requires immutable `code_revision` and `model_revision`,
plus the composition host's `model`, `base_url`, `api_key_var` and sampling.
It has bounded attempts and a per-attempt timeout, uses retrospective trajectory
context, and preserves raw judge outputs and input/scorer digests in trace info.
It never loads a model or chooses a device. The configurable rubric combines
five reasoning-quality dimensions internally; none becomes a trainer field.
Episode scope instead emits seven independent whole-trajectory components for
explicit consumer projection; it does not average them into one environment
reward.

Outputs are generic `quality` assessments and explicit `erroneous_turn_ids`
under `info.posttrain_turn_rewards`. These do not add to the native
`partial_credit` reward. Consumers explicitly choose turn rewards, a mean/sum
trajectory reduction, or error-turn projection. Error labels are independent
from quality ratings. Invalid or timed-out assessments fail after bounded retry,
never become valid zero. Native structured outputs constrain verdict syntax;
coverage and score validity are still checked locally. Explicit abstention and
inapplicability retain distinct statuses and do not retry or invent a reward.

`context_scope="retrospective"` rates turns with the full trajectory;
`context_scope="prefix"` makes a separate bounded assessment per turn using only
the prefix through that turn. This setting changes the scorer identity. Multiple
plugins use distinct `annotation_key` values and namespaced scorer digests.
There is no mutable score cache: reassessment requires a new namespace or trace,
and existing assessments cannot be overwritten. Twenty-seven candidate tests
cover these contracts. The all-six-wheel compatibility gate passes locally;
live managed qualification from the immutable release commit remains open.

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
