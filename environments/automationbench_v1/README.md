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
  --harness.id null \
  --taskset.domains simple \
  --model Qwen/Qwen3.5-2B \
  --client.base-url http://127.0.0.1:8000/v1 \
  --client.api-key-var LOCAL_INFERENCE_API_KEY \
  --num-tasks 1 --num-rollouts 1 --max-concurrent 1 \
  --sampling.max-tokens 2048 --sampling.temperature 0 \
  --max-turns 50 --max-total-tokens 8192 \
  --rich false --push false --output-dir /tmp/automationbench-v1
```

Native Verifiers traces remain the replay authority. A framework composition
may consume this wheel, but the environment itself has no framework or
tracking dependency.
