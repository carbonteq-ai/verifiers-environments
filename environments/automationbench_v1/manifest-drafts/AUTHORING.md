# Manifest authoring guide

2026-10-04. Ten-task batch across six non-Simple domains. Its purpose is to
author declarations with **existing** capabilities and to expose concrete,
reusable gaps. It is not a promise that all ten become whole-task qualified.

## Authority rules

- Correctness comes only from public inputs: the task prompt and public initial
  state (policy emails, Slack messages, sheets, records). Hidden benchmark
  assertions, answers and artifacts never define a requirement.
- The Luna episode is a verified reference execution, not an imitation target.
  Its chosen path cannot invent requirements; alternative correct paths must
  remain acceptable. Use it to replay drafts and to find real counterexamples.
- Unknown must stay unknown. Never turn missing evidence into a pass or a zero.
- Task-specific parameters belong in manifest data. Do not add named-task
  Python evaluators.

## Repositories and boundaries

- Environment package (dirty, uncommitted candidate):
  `/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1`.
  **Read only.** Do not edit `src/`, `tests/`, the catalog or installed
  manifests. Shared mechanisms are implemented separately by the coordinator.
- Native Verifiers candidate (read only): `/home/hammad/projects/verifiers-credit-candidate-20261003`.
- Write outputs only to `manifest-drafts/tasks/<task_name>/` in the environment package;
  keep throwaway scripts in a session scratch folder, not in either repository.
- No commits, no network, no model calls, no GPU.

Run Python from the package directory with:

    PYTHONPATH=/home/hammad/projects/verifiers-credit-candidate-20261003:src:tests .venv/bin/python <script>

## Inputs per task

- Public pack: `/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/manifest-authoring-105/batch-NN.json`
  → `tasks[i]` with `task_name`, `public_input` (`prompt`, `initial_state`) and its linked retained episode.
- Earlier review: `/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate/manifest-authoring-batch-NN-review.json` → `tasks[i]`
  (goals, prohibitions, constraints, authority, ambiguities). Its gap labels are
  historical; check current code before calling something a gap.
- Capability matrix entry: `/home/hammad/projects/rl/docs/research/verifiers-assessment-qualification/reward-candidate/capability-opportunities-105.json` → `tasks[]`.
- Luna episode: `tests/test_batch01_manifests.py::recorded(task_name)` loads and
  SHA-checks it (selection file `docs/research/verifiers-assessment-qualification/reward-candidate/cross-category-selection.json` in the framework repo).

## Existing manifest vocabulary (read `src/automationbench_v1/contracts/models.py`)

Check operators: `effects.required_when@1` (occurrence obligations, now with
optional `aggregates` aliases readable only in `effect_match`),
`effects.prohibited_when@1` (guards), `sheets.retained_when@1`,
`records.retained_when@1`, `objects.created_and_retained@1`,
`record.fields_equal@1`/`record.coverage@1`, `summary_exclusions@1`,
`no_clarification@1|2`, plus `population.aggregate@1` specs inside obligations.

Sources: `initial.records@1`, `google_sheets.rows@1`, `public.request@1`,
`final.records@1`, `salesforce.record@1`, effect adapters
`gmail.messages@1` (send), `gmail.message_reads@1`, `google_sheets.row_writes@1`,
`slack.messages@1`, `asana.actions@1`, `jira.issues@1`, `hubspot.objects@1`,
`zendesk.ticket_updates@1`, `assistant.outputs@1`, `external.outputs@1`.

Predicates (`contracts/predicates.py`): `eq/ne/lt/lte/gt/gte/in`, `all/any/not`,
`line_number_eq`; operands literal/field/text/derived. Values
(`contracts/values.py`): exact decimal/USD/date inputs, add/sub/mul/div,
explicit rounding, `days_between`, `within_interval`, `add_calendar_months`.

Worked examples: every file in `src/automationbench_v1/contracts/tasks/`,
especially `finance-prepaid-schedule-and-guard.json` (schedule, guard,
aggregate report line) and `simple-customer-recipient-delivery.json` (Gmail
send obligation). Tests showing native replay: `tests/test_prepaid_report_total_manifest.py`,
`tests/test_prepaid_schedule_manifest.py`.

Installed manifests require public bindings: each `bindings[]` entry is
`{"path": [...], "canonical_sha256": digest(value)}` with
`digest` from `automationbench_v1.manifest_guard_assessments` over the exact
public value at that path (prompt, and each initial policy source relied on).

## Gap categories (priority shared mechanisms)

Classify every obligation you cannot express with one of:

- `cross_system_reconciliation` — join or compare records across two services
  (e.g. payments vs invoices), including two-sided absence and duplicates.
- `eligibility_first_ranking` — choose top/least/nearest among eligible members
  with explicit ties and capacity.
- `generated_object_relationships` — a later action must reference an ID the
  agent created earlier (meeting link, ticket, row).
- `required_read_ordering` — public policy requires reading/checking before an
  action; needs authoritative read completion before dispatch.
- `report_fact_coverage` — a message must contain specific facts/entities
  (names, amounts, lines), beyond one numeric line.
- `other:<short-name>` — anything else; say why the five do not fit.

A gap claim must name the exact public anchor text, show why current operators
cannot express it (cite the code), and sketch the smallest shared mechanism.
Name the other batch tasks that would reuse it.

## Required outputs per task

1. `tasks/<task_name>/draft.json` — full contract (bindings, sources, checks,
   credit) containing **only** obligations expressible today. Use outcome-only
   checks (no credit rule) unless an existing credit policy clearly fits.
   It must pass `load_contract`.
2. `tasks/<task_name>/review.json` with:
   - `task_name`, `public_pack` path/index, `episode_sha256`;
   - `obligations[]`: `id`, `public_anchor` (quoted text + source path),
     `kind` (goal|guard|constraint|report), `status` (`expressed` | `gap` |
     `out_of_scope`), `check_id` when expressed, `gap_category` and
     `mechanism_sketch` when a gap, `reused_by` (other task names);
   - `luna_replay`: per expressed check, status/value/reason from native
     scoring of the actual episode, plus whether scalar rewards and episode
     bytes stayed unchanged and rescore/reload repeated the result;
   - `alternatives_tested`: genuine-simulator alternative executions (correct
     variant, harmful variant, missing-ACK) if you ran them;
   - `limitations` and `whole_task_status` (`not_qualified` unless every
     public obligation is expressed and verified).
3. A short `tasks/<task_name>/review.md` (≤ 40 lines) explaining the same in plain words.

Scope decision (2026-10-04): the two shared system-prompt rules (do not ask
clarifying questions; list only items acted on) are `out_of_scope` for
whole-task qualification. Mark them so; they are reported separately and never
block `whole_task_status`.

Report counts honestly and separately: obligations reviewed, expressed,
gaps by category. A passing component is not a qualified task.

## Mechanisms added after the first drafts (2026-10-04)

Redrafts may use these (all in the environment candidate):

1. Effect scope closes over calls whose static handler footprint excludes the
   service and leaves it unchanged; sparse public Gmail/Slack/service state
   reconciles. `SheetEffectSource.alternative_services` keeps scope open when
   the same effect could happen through another service.
2. `{"op": "mentions", "text": <string field>, "value": <operand>,
   "mode": "words"|"verbatim"|"amount", "format": <usd_string|decimal_string
   for amount>, "excluding": [longer names]}` and
   `"match_cardinality": "per_candidate"` on obligations (no once-only credit).
3. Decided lookup outcomes: `{"kind": "field", "path": ["lookup", <alias>]}`
   is `matched` or `not_found`; ambiguous/unavailable stay unknown.
4. Obligation `selections`: `{alias, population, where (member.*, request.*,
   lookups, selected.*), order_by: [{value, direction}]}` publishing
   `selection.<alias>` (`selected`|`none`) and `selected.<alias>.<field>`;
   ties/unknowns stay unknown.
5. Effect source `{"adapter": "service.record_writes@1", "service": <world
   service>, "collection": [<list field>] | ["actions", <action_key>],
   "kind": "create"|"update"|"delete"}`; effect params `record`, `before`,
   `changed_fields`, `record_id`, `operation`.

## Mechanisms added after round 2 (2026-10-04)

6. Value formats (`ValueInput.format`): `clock_time` (minutes since midnight;
   "2:30 PM", "2pm", "14:30"; meridiem-less one-digit hours are unknown),
   `duration_text` (minutes; "15 minutes", "1 hour 30 min"; bare numbers
   unknown), `duration_clock` (seconds; "m:ss", "h:mm:ss"), `iso_instant`
   (exact UTC epoch seconds; requires an offset or Z). All are decimals, so
   arithmetic and ordering work (e.g. start + duration ≤ meeting start).
7. `mentions` mode `clock_time`, and `{"op": "mentions_together", "text": ...,
   "terms": [<MentionTerm>, ...]}`: every term on one readable line (an amount
   beside its item, a hire beside their buddy). Terms take the same fields as
   `mentions` (`value`, `mode`, `format`, `excluding`).
8. Obligation `effect_joins`: `[{alias, source: <effect source>, where,
   timing: "before"|"not_after"}]`. `where` reads `effect.*`, `joined.*` and
   the candidate context; effect_match reads `join.<alias>` (`matched`/`none`)
   and `joined.<alias>.*`. Use for "the update must target the item the agent
   created" (e.g. `effect.record.params.item_id == joined.record_id`).

## Scope decision: deterministic checks only (2026-10-04)

Do not author wording or judgement checks: no word or phrase lists for
"covers the topic", "acknowledges", "explains", "summarizes", tone or
paraphrasable content. Mark such obligations `out_of_scope` with reason
`requires_judgement`. Keep exact-fact content checks (named entities,
amounts, IDs, dates/times, recipients, a line or value the prompt requires
verbatim). Tasks with judgement-dependent parts remain in scope: check their
deterministic parts (partial credit is expected) and mark only the wording
parts `out_of_scope`. Coverage counts exclude out-of-scope obligations.

## Mechanisms added after round 3 (2026-10-04)

9. Guards over any population: `initial.records@1` and `public.request@1`
   populations (not only Sheets rows), plus guard `effect_joins` readable by
   `effect_match` (e.g. "status set on an item the agent did not create",
   "acted without a prior read" as separate harm signals).
10. Obligation `alternatives`: `[{alias, source, effect_match}]` — another
    channel can witness the obligation (Gmail or Slack DM); a known zero needs
    every listed inventory complete.
11. Joins: `match: "any"` (one proven earlier effect suffices, earliest
    exposed) and `timing: "any"` (either direction).
12. Gmail reads: sends/drafts/labels/read-marks are not reads and no longer
    break read evidence; acknowledged failed searches return nothing;
    `gmail_list_emails` is an audited read for send scope.
13. Clock values: meridiem-less 10:00–12:59 is ambiguous for `clock_time`;
    `clock_24h` reads declared 24-hour data; ranges like "1:00–1:15 PM" share
    the meridiem; "noon"/"midnight". Value expression `add_business_days`
    with a required explicit `holidays` list.
14. `mentions` additions: `amount_reformatted` mode (right amount, not
    verbatim — use in guards), `mentions_together` `scope: "block"`
    (blank-line paragraphs), amount format `usd_marked` (dollar sign
    required), numeric values in `verbatim`, possessives ("Hal's") mention the
    name. Predicate `{"op": "proven", "arg": ...}`: unknown counts as false —
    only for declared eligibility of unreadable data rows.
15. `initial.records@1` `identity_paths` for composite identities (Slack
    messages: `[["channel_id"], ["ts"]]`; identity equals Slack effect ids).
16. Authoring trap: a guard whose effect match does not depend on the row must
    use `match_cardinality: "per_candidate"`.

## Mechanisms added after round 4 (2026-10-04)

17. Absent from the same scope: `mentions_together` takes
    `excluding_values` (up to 16 terms, same fields as `terms`). A unit (line,
    `block`, or `scope: "text"` = the whole text, e.g. one record's
    `values_text`) matches only if every term is present **and** no excluded
    value appears in it; an excluded value whose presence is unknown (an
    unresolved field, an ambiguous form, or only in a quoted line of the unit)
    keeps the unit unknown. With exclusions a single term is allowed. Use it to
    stop "list every candidate amount on one line" from passing:

        {"op": "mentions_together", "text": {"kind": "field", "path": ["effect", "body"], "domain": "string"},
         "terms": [{"value": {"kind": "field", "path": ["request", "Department"], "domain": "string"}, "mode": "words"},
                   {"value": {"kind": "field", "path": ["request", "Share"], "domain": "string"},
                    "mode": "amount", "format": "usd_string"}],
         "excluding_values": [{"value": {"kind": "field", "path": ["request", "Other Share"], "domain": "string"},
                               "mode": "amount", "format": "usd_string"}]}

    For a record write: `"text": {"kind": "field", "path": ["effect", "values_text"], "domain": "string"},
    "scope": "text"`. Excluded terms are matched like terms (amounts in any
    accepted form, including "$1.5k"), so list only values that must not
    appear; a legitimate "was $900" beside the right amount also fails.

Engine corrections in the same round: amounts followed by a list comma
("$8,420, no") are read; k (and dollar-marked m/b) suffixes are read exactly
("$120k" = 120000) and only values they could be rounded from stay unknown;
24-hour ranges ("13:00-13:30") yield both ends; guards publish
`lookup.<alias>` (`matched`/`not_found`) like obligations.

Revise a task by overwriting its `tasks/<task_name>/` files and recording the
coverage change in `review.json`; do not add versioned copies (`-v2`, `-v3`).
