# CarbonTeq Verifiers environments

This repository contains framework-neutral Verifiers v1 task environments maintained by CarbonTeq. Every package selects the same immutable revision of the [CarbonTeq Verifiers fork](https://github.com/carbonteq-ai/verifiers), whose ledger records the retained upstream base and generic runtime seams.

Each directory below is a standalone Python project with its own package metadata, dependency lock, tests, version, and wheel. There is no root runtime package and installing one environment does not install its siblings.

| Project | Distribution | Status |
| --- | --- | --- |
| `environments/gsm8k_v1` | `gsm8k-v1` | pinned Hub implementation; framework/live qualification complete |
| `environments/automationbench_v1` | `automationbench-v1` | v0.4 episode-only multidimensional judge candidate; immutable live qualification pending |
| `environments/mmlu_pro_v1` | `mmlu-pro-v1` | pinned Hub implementation; reference qualification complete |
| `environments/ifeval_v1` | `ifeval-v1` | deterministic checker implementation; reference qualification complete |
| `environments/reasoning_gym_v1` | `reasoning-gym-v1` | pinned procedural generator implementation; balanced qualification complete |
| `environments/math_python_v1` | `math-python-v1` | pinned MATH loader and bounded subprocess tool; live qualification complete |

GSM8K and MMLU-Pro load exact Hugging Face revisions and carry source row
digests in task data. IFEval uses a typed deterministic port of Google's
Apache-2.0 instruction checkers. Reasoning Gym delegates generation and native
scoring to its pinned upstream registry. Math Python loads the pinned MATH
revision, verifies boxed answers with `math-verify`, and exposes a bounded,
task-scoped child-interpreter tool. AutomationBench is the migrated native
adapter for CarbonTeq's pinned wheel and preserves its simulated world,
toolsets, and assertion scorer. The framework qualification uses the bounded
subprocess/tool path for Math Python; its published OCI image is an optional
artifact and is not required for the current release runtime.

AutomationBench v0.4 exposes one whole-episode judge contract. It reconstructs
material task requirements and independently scores five reasoning dimensions,
action quality, and answer quality. Its model-facing schema uses bounded integer
message indexes and normalizes them to stable native-trace message IDs before
the rewards are admitted; redundant valid citations are de-duplicated while
out-of-range citations remain invalid. The former combined turn/episode judge was removed:
mixing its turn rubric with the episode schema caused constrained decoders to
expand rubric instructions as fake task requirements and exhaust large output
budgets. Real captured-request replay on Spark-X2.5-4B is retained by the
Posttrain consumer as the live qualification evidence for this correction.

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
