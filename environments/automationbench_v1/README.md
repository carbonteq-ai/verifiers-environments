# AutomationBench v1 environment

The local `summary_exclusions@1` check binds public policy to retained assistant
and external output facts. Composition supplies an optional semantic backend
with caller-owned messages and parsing; raw exchanges are journaled before
parsing. Known violations survive unrelated gaps, while compliance requires
closed output/action capture and complete decisions. Its 78-case controlled
transport gate does not qualify model prose accuracy or whole-task coverage.

Local assessment candidate, 2026-10-04 (unpublished): manifest data describes
source-bound record goals, conditional action guards, new-occurrence obligations
and supported retained schedule goals. `public.request@1` supplies one reviewed
authored obligation with exact public-source receipts, without pretending an
object existed initially. Missing authority preserves an unavailable member.
Native findings and domain credit retain source evidence and original execution
identities; the existing scalar scorer is preserved. Recorded Luna traces are
reassessed without overwriting their original files.

`gmail.message_reads@1` supplies authenticated returned fields from supported
Gmail reads. ID-only and metadata-only results never inherit a backend body.
The Contact assistant declaration checks the returned original introduction
and both requested assistant fields, with separate once-only contributions.
It proves successful tool retrieval, not comprehension or exact token exposure.
Conditional summary compliance and whole-task acceptance remain open.

`external.outputs@1` supplies a separately qualified factual inventory for
audited discovery/read handlers and Contact assistant fields. The saved SDK
example reconciles all seven calls using exact controller-bound server and
request/result evidence, and retains both field values as authored record text.
Known fields survive unrelated capture gaps; native-only model coverage and
summary interpretation remain unavailable pending separate qualification.

Consumed manifest credit freezes one canonical manifest revision per episode
ledger across the six current policy families. Changed reward designs use a
separate replay ledger; failure or cancellation cannot erase valid partial
credit. `assistant.outputs@1` separately extracts authored assistant text from
sampled native messages or exact retained SDK artifacts. Known text and complete
capture are different facts. This source neither judges summary wording nor
closes externally sent messages or record text. These changes remain local
candidate work, with qualification recorded in the framework plan.

Local manifests also support fresh retained Jira issues through
`objects.created_and_retained@1`, with completion credit selected separately.
Initial identity membership, final retention and acknowledged action evidence
are distinct; historical action logs cannot invent retained objects. The Sheets
evidence adapter recognizes the installed append alias and preserves its native
argument precedence. The retired-content guard is installed after actual
negative-action replay and whole policy-inventory binding checks. Whole workflow
eligibility and release qualification remain open.

The prepaid declaration now includes schedule completion-action credit and
ineligible-recognition harm, with complete relevant policy inventories bound.
Journal content, aggregate totals and whole-task coverage remain open. Local
Contact state-goal declarations and other bounded components do not qualify the
full library. Older revision/distribution sections below describe historical
published or candidate revisions, not this unpublished source tree.

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
uv run pytest -n 6
uv build --wheel
```

`pytest-xdist` is a dev dependency. `-n 6` runs six worker processes and the
package config distributes by file (`--dist=loadfile`), because several files
share mutable module-scoped recorded-episode fixtures. Plain `uv run pytest`
still runs serially. Keep the worker count well below the machine's core count.

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

The unpublished manifest candidate also supports `records.retained_when@1`:
declare an `initial.records@1` population and a `final.records@1` projection of
the same typed collection. Each outcome follows the original native ID and
requires explicit terminal finalization. Missing evidence abstains; a fully
observed terminal inventory without the original record fails retention.
Already-correct state can satisfy the outcome without action credit. This
operator has a separately qualified `records_retained_completion_once@1` policy
for observed Zendesk status completion. It requires explicit earliest selection,
an effects source, known initially false goal and current retained success; noops
and initially correct records receive no action contribution. Manifest predicates must name declared canonical
schema fields, and terminal projections preserve raw values without coercion
or generated defaults. Candidate source and tests are under qualification;
this does not describe a published release or complete task coverage. The public
Zendesk ticket update is qualified while resolution-email purpose remains open.
