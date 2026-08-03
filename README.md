# CarbonTeq Verifiers environments

This repository contains framework-neutral [Verifiers](https://github.com/PrimeIntellect-ai/verifiers) v1 task environments maintained by CarbonTeq.

Each directory below is a standalone Python project with its own package metadata, dependency lock, tests, version, and wheel. There is no root runtime package and installing one environment does not install its siblings.

| Project | Distribution | Status |
| --- | --- | --- |
| `environments/gsm8k_v1` | `gsm8k-v1` | pinned Hub implementation; framework/live qualification pending |
| `environments/automationbench_v1` | `automationbench-v1` | native adapter migrated; live parity qualification pending |
| `environments/mmlu_pro_v1` | `mmlu-pro-v1` | pinned Hub implementation; reference qualification pending |
| `environments/ifeval_v1` | `ifeval-v1` | deterministic checker implementation; reference qualification pending |
| `environments/reasoning_gym_v1` | `reasoning-gym-v1` | pinned procedural generator implementation; balanced qualification pending |
| `environments/math_python_v1` | `math-python-v1` | pinned MATH loader and bounded Python tool; CarbonTeq OCI image published, lifecycle gate pending |

GSM8K and MMLU-Pro load exact Hugging Face revisions and carry source row
digests in task data. IFEval uses a typed deterministic port of Google's
Apache-2.0 instruction checkers. Reasoning Gym delegates generation and native
scoring to its pinned upstream registry. Math Python loads the pinned MATH
revision, verifies boxed answers with `math-verify`, and exposes a bounded,
task-scoped child-interpreter tool. AutomationBench is the migrated native
adapter for CarbonTeq's pinned wheel and preserves its simulated world,
toolsets, and assertion scorer. None of these local implementation slices is a
release capability claim until the later parity, image, framework, and live
qualification gates pass.

## Install one environment

Use a full repository commit and the selected package subdirectory:

```bash
REVISION=0000000000000000000000000000000000000000
uv add "gsm8k-v1 @ git+https://github.com/carbonteq-ai/verifiers-environments.git@${REVISION}#subdirectory=environments/gsm8k_v1"
```

Replace the zero revision with a published 40-character commit. A posttrain project records the same repository, revision, subdirectory, distribution, and declarative taskset activation in its environment binding.

## Validate

Each package is validated independently:

```bash
cd environments/gsm8k_v1
uv sync --locked --python 3.12
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
uv build --wheel
```

Run `uv run --python 3.12 python scripts/check_boundaries.py` from the repository root to verify package independence. Because the root has no `pyproject.toml`, uv supplies only the requested interpreter and creates no root environment. CI also builds all six wheels, installs them together in a disposable environment, and runs `scripts/verify_combined_install.py` to detect dependency or plugin-discovery conflicts without forcing network-backed task loading.

## Ownership boundary

Environment packages own generic task construction, interaction, tool behavior, verification, reward semantics, and native Verifiers trace data. They must not import posttrain, tracking products, trainers, serving engines, or sibling environments.

The posttrain framework owns catalog selection, task and rollout budgets, immutable wheel packaging, provider execution, and cross-run evidence presentation. Hugging Face task rows remain environment-owned task data rather than posttrain `DatasetSelection` values.
