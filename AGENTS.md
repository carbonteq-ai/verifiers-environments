# Agent guide

This repository owns framework-neutral Verifiers v1 environment packages. Every environment must remain usable without posttrain.

## Package boundary

- Each directory under `environments/` is a standalone uv project with its own `pyproject.toml`, `uv.lock`, tests, version, and wheel.
- Do not add a root uv workspace or root runtime package.
- Do not import sibling environment modules.
- Do not import posttrain, Trackio, W&B, TRL, vLLM, dstack, or an application package.
- Pin Verifiers and Git dependencies by full commit. Use compatible registry dependency ranges in metadata and exact resolutions in each package lock.
- Hugging Face data used by a taskset belongs to that environment. Record repository, full revision, configuration, split, stable row identity, and row digest.
- Native Verifiers traces are the replay authority.

## Validation

From a package directory:

    uv lock --check
    uv sync --locked --python 3.12
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest
    uv build --wheel

From the repository root:

    uvx --from ruff==0.16.1 ruff check scripts
    uvx --from ruff==0.16.1 ruff format --check scripts
    uv run --python 3.12 python scripts/check_boundaries.py

Build and install all six wheels together before publishing a repository commit consumed by a composed evaluation plan. A single posttrain job cannot select multiple revisions of this repository.

Do not commit, tag, or publish without explicit user authorization.
