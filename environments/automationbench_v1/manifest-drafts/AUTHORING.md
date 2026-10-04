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
   Optional `"identity_paths": [["list_id"], ["id"]]` (list collections only,
   2–4 string fields) keys records by a composite identity when `id` repeats
   across a parent (Mailchimp gives a subscriber the same `id` in every
   list); `record_id` is then the canonical JSON list (e.g.
   `"[\"list_vip\",\"<md5>\"]"`), matching `initial.records@1`
   `identity_paths` identities. Without it, repeated ids stay unknown.

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

18. Sole values: `"sole": true` on an `amount`/`amount_reformatted`/
    `clock_time` term (in `mentions` or a `mentions_together` term) means the
    value must be the only value of its kind in the matching unit, so hedges
    such as "$25,000 / $7,500", "$8,325 to $8,326" or "0.55, 0.54, 0.56" fail
    without listing rivals:

        {"op": "mentions", "text": {"kind": "field", "path": ["effect", "body"], "domain": "string"},
         "value": {"kind": "field", "path": ["request", "Total"], "domain": "string"},
         "mode": "amount", "format": "usd_string", "sole": true}

    Kind rules. A number joined to the value by a range or alternative ("-",
    "–", "/", "~", "to", "or", "through") is always a second value. Otherwise
    numbers are classed as money (`$`), grouped ("8,420", "120k"), decimal,
    integer (>= 1000), count (< 1000), year (1900–2100) or percent (`%`);
    dates, clock times and reference codes are never amounts. Money targets
    (`usd_*` formats) fail on another money/grouped value and stay unknown on
    a bare decimal or large integer; decimal targets fail only on another
    decimal; integer targets (>= 1000) fail on money/grouped/integer; count
    targets stay unknown on other counts. Counts, years and percents never
    sink a money target. Clock times: any other readable time fails (both ends
    of a range count), a bare ambiguous hour is unknown. Repeating the value
    is fine. An undecidable rival (an ambiguous magnitude) keeps the unit
    unknown.

22. Any-channel harm guards: `effects.prohibited_when@1` takes
    `alternatives: [{alias, source, effect_match}]` like obligations
    (mechanism 10). Each listed effect source (Gmail/Slack/Sheets/record
    writes; not Gmail reads) is watched with its own `effect_match`; a match
    on any channel is a violation and is penalised on that effect. "No
    violation" needs every channel's inventory complete, so one unobserved
    channel keeps compliance unknown. Alternative matches cannot read
    `joined.*` (joins apply to the primary source). The same effect seen on
    two channels is one instance (any match wins, else unknown wins).

        "source": "sends", "effect_match": {"op": "mentions", "text": {"kind": "field", "path": ["effect", "body_text"], "domain": "string"}, "mode": "words", "value": {"kind": "field", "path": ["request", "Hire"], "domain": "string"}},
        "alternatives": [{"alias": "slack_dm", "source": "dms",
                          "effect_match": {"op": "mentions", "text": {"kind": "field", "path": ["effect", "text"], "domain": "string"}, "mode": "words", "value": {"kind": "field", "path": ["request", "Hire"], "domain": "string"}}}]

    Guards also accept `selections` exactly as obligations (mechanism 4),
    over Sheets or `initial.records@1` populations; `prohibited_when`,
    `effect_match` and alternatives read `selection.<alias>` /
    `selected.<alias>.*` (e.g. "the deal has an active conversation").

Engine corrections in the same round: amounts followed by a list comma
("$8,420, no") are read; k (and dollar-marked m/b) suffixes are read exactly
("$120k" = 120000) and only values they could be rounded from stay unknown;
24-hour ranges ("13:00-13:30") yield both ends; guards publish
`lookup.<alias>` (`matched`/`not_found`) like obligations.

Revise a task by overwriting its `tasks/<task_name>/` files and recording the
coverage change in `review.json`; do not add versioned copies (`-v2`, `-v3`).

## Slack reads and existential predicates (2026-10-04)

19. Slack read evidence: effect source `{"adapter": "slack.message_reads@1",
    "kind": "read_message"}` (`kind` may be omitted). One fact per message an
    acknowledged read call returned: `slack_find_message`,
    `slack_find_message_in_channel`, `slack_get_message`,
    `slack_get_message_reactions`, `slack_list_channel_messages`,
    `slack_get_channel_messages`, `slack_get_thread_replies`. Params:
    `native_record_id` (canonical `["<channel_id>", "<ts>"]`, equal to
    `candidate.native_record_id` of an `initial.records@1` Slack messages
    population with `identity_paths` `[["channel_id"], ["ts"]]`),
    `channel_id`, `message_ts`, `thread_ts` (or null), `text` and `user_id`
    when returned, `returned_fields`, `channel_name` and `is_deleted` (from
    the pre-call world, not returned), `operation`. Closure works like Gmail
    reads: the returned message must exist in the pre-call world with the same
    text/author/thread; failed, empty, user and channel-metadata reads return
    nothing; Slack writes (sends, edits, reactions, channel changes) are not
    reads; calls whose footprint excludes Slack and left it unchanged are
    skipped; `api_fetch` and unknown tools leave the inventory incomplete; a
    complete inventory needs every ACK and a public-initial/terminal Slack
    reconciliation. Usable as an obligation `source` (not a guard source) and
    as an `effect_joins` source in obligations and guards. "Read the pinned
    guidelines before posting":

        "sources": {"messages": {"adapter": "initial.records@1",
                      "path": ["task_evidence", "initial", "slack", "messages"],
                      "identity_paths": [["channel_id"], ["ts"]],
                      "fields": {"Channel": ["channel_id"], "Ts": ["ts"]},
                      "key_fields": ["Channel", "Ts"]},
                    "reads": {"adapter": "slack.message_reads@1"},
                    "posts": {"adapter": "slack.messages@1", "kind": "channel_message"}},
        "checks": [{"check_id": "post-after-guidelines", "operator": "effects.required_when@1",
          "semantics": "new_occurrence", "population": "messages", "source": "posts",
          "required_when": <Channel == "C_guidelines" and Ts == "<pinned ts>">,
          "effect_joins": [{"alias": "guide", "source": "reads", "timing": "before", "match": "any",
            "where": {"op": "eq", "left": {"kind": "field", "path": ["joined", "native_record_id"]},
                      "right": {"kind": "field", "path": ["candidate", "native_record_id"]}}}],
          "effect_match": {"op": "all", "args": [
            {"op": "eq", "left": {"kind": "field", "path": ["join", "guide"]},
             "right": {"kind": "literal", "value": "matched"}},
            {"op": "eq", "left": {"kind": "field", "path": ["effect", "channel_id"]},
             "right": {"kind": "literal", "value": "C_marketing"}}]}, ...}]

    Read-then-post is 1, post-then-read is 0 with `timing: "before"`, reading
    another channel is 0, a missing ACK is unknown. For "read the channel" use
    `joined.channel_id` instead of the message identity.
20. Existential predicate over a population:
    `{"op": "exists", "population": <source>, "where": <predicate>,
    "max_members": 4096}`. `where` reads `member.*` (the population row's
    declared fields) plus the enclosing context (`effect.*`, `request.*`,
    lookups, `joined.*`...). True when some member is proven; false when every
    member is decided false (an empty closed population is false); unknown
    when the population is not closed/enumerated, exceeds `max_members`, or
    no member is proven and some member is unknown. The population must be a
    declared initial `google_sheets.rows@1` or `initial.records@1` source; it
    joins the check's inputs and selector identity. Allowed in any predicate
    of `effects.required_when@1` and `effects.prohibited_when@1` checks
    (including join `where` and selection `where`); a lookup alias may not be
    `population`. Joins cannot express this: they range over effects, and
    selections/aggregates cannot read the effect. "The plan names at least one
    eligible backlog idea":

        "effect_match": {"op": "exists", "population": "ideas", "where": {"op": "all", "args": [
          {"op": "eq", "left": {"kind": "field", "path": ["member", "Status"], "domain": "string"},
           "right": {"kind": "literal", "value": "eligible"}},
          {"op": "mentions", "text": {"kind": "field", "path": ["effect", "text"], "domain": "string"},
           "value": {"kind": "field", "path": ["member", "Idea"], "domain": "string"}, "mode": "words"}]}}

    As a guard `effect_match` ("names a parked idea") use
    `match_cardinality: "per_candidate"` when the match does not depend on the
    candidate row (mechanism 16). Wrap in `not` for "names no ineligible
    idea"; unknown stays unknown.

## Calendar-date mentions (2026-10-04)

21. `mentions` / `mentions_together` term `mode: "date"`: does message text
    state calendar date D? `value` is an ISO date: a literal/field string
    `"2026-04-20"` or a `derived` calendar date (`iso_date`, `iso_timestamp`,
    `date_text`, `add_business_days`, `add_calendar_months`). Optional
    `assume_year` (integer) is the year of year-less prose dates.

    ```json
    {"op": "mentions", "text": {"kind": "field", "path": ["effect", "body_plain"], "domain": "string"},
     "mode": "date", "assume_year": 2026,
     "value": {"kind": "derived", "expression": {"kind": "add_business_days",
       "date": {"kind": "input", "format": "iso_date", "path": ["request", "Last Day"]},
       "days": {"kind": "input", "format": "number", "literal": -5}, "holidays": []}}}
    ```

    Rules (true / false / unknown per line, then the usual readable-line scan):
    - Recognised: `2026-04-20`, `2026/04/20`, ISO timestamps (date as
      written), `4/20/2026`, `20/4/2026`, `4.20.2026`, `April 20, 2026`,
      `Apr 20 2026`, `20 April 2026`, `the 20th of April`, `April 20th`,
      weekday prefixes (`Monday, April 20`), listed days (`Feb 3, 10 and 17`).
    - Numeric `a/b/YYYY` is read month-first and day-first: unknown when both
      readings are valid and differ and D is one of them (`03/05/2026`); exact
      when only one is valid (`25/03/2026`, `3/25/2026`) or a weekday picks one.
      A stated weekday that contradicts the date is unknown.
    - Year-less dates (`March 5`, `Mar 5th`, `3/5`) are true only with
      `assume_year` (the task's public current year). Without it they stay
      unknown when month/day (and any weekday) agree with D, false otherwise.
      Year-less ranges that wrap a year never take `assume_year`.
    - Ranges (`March 5–7, 2026`, `Mar 5 - Mar 7`, `between March 5 and 7`,
      `2026-03-05 to 2026-03-07`) state their endpoints (true); interior days
      are covered but not stated (unknown). `March 5 - 7pm` is a time.
    - Unknown, never false, when the token could be D: relative words
      (`today`, `tomorrow`, `next week`, `in 3 business days`), bare or
      relative weekdays matching D's weekday (`next Friday`), `on the 5th`,
      year-less `3/5`, lowercase `may`/`march` (verbs), quoted/fenced lines.
    - False: every date-like token clearly differs from D, or no date at all.
      A month with a year but no day (`March 2026`) names no day; reference
      codes (`PMT-2026-03-05`) and versions (`v1.3.26`) are not dates.

    `within` (on `mentions` only, instead of `value`): at least one readable
    stated date and every stated date (range endpoints included) in the
    inclusive interval → true; any readable date outside → false; no dates →
    false; a token that might lie outside (ambiguous numeric, relative word,
    year-less date without `assume_year` that could fall inside) → unknown.

    ```json
    {"op": "mentions", "text": {"kind": "field", "path": ["effect", "body_plain"], "domain": "string"},
     "mode": "date", "assume_year": 2026,
     "within": {"start": {"kind": "literal", "value": "2026-02-01"},
                "end": {"kind": "literal", "value": "2026-02-28"}}}
    ```

    Value format `date_text` (calendar date) reads stored human dates with
    an explicit year: `"February 3, 2026"`, `"Tue, Feb 3, 2026"`,
    `"3 February 2026"`, ISO, and `M/D/YYYY` only when unambiguous. Year-less,
    relative, weekday-contradicting or ambiguous text is unavailable:

    ```json
    {"kind": "derived", "expression": {"kind": "input", "format": "date_text", "path": ["record", "start_date"]}}
    ```

## Presence predicate (2026-10-04, round 6)

23. `{"op": "present", "value": {"kind": "field", "path": [...]}}`: true when
    the field resolves to a non-null value; false for an explicit null, or when
    the path is decidably absent inside a known effect record (`effect.*`,
    `joined.*`): a missing key, a missing list index (`["effect", "record",
    "signers", 1, "email"]` on a one-signer envelope) or a null container on
    the way; unknown when the root record is unavailable, when a key is missing
    from any other root (rows, lookups, `request.*` — unread, not absent), or
    when a scalar sits where a container is expected. Use it for "parameter was
    set" (Asana omits unset params) instead of `proven`, and wrap optional
    indexes as `{"op": "all", "args": [<present>, <comparison>]}` so a missing
    second signer is a decided false. Plain comparisons are unchanged: a
    missing path or index stays unknown there (an absent value is not "not
    equal"); decide absence explicitly with `present`.

## Engine corrections round 6 (2026-10-04)

- Sparse public state: a collection the public service omits (Slack `users`,
  `messages`; Zendesk `tickets`) is its schema default (empty); scope still
  closes only when public state reconciles with the native world. Slack
  messages nested under `channels[i].messages` are compared in the hoisted
  top-level layout the simulator uses. HubSpot and Jira keep their explicit
  membership rules (an omitted collection there stays unknown).
- Co-firing harms: two guards (or one guard on several rows) firing on one
  call with the same credit channel merge into one -1 penalty whose parents
  are every fired harm and whose signal is the earliest fired guard in
  contract order (transformation `merged_prohibited_effect_penalty@1`).
  Different channels keep separate penalties. Previously credit failed for
  the whole episode.
- Amounts: unspaced ranges/alternatives (`$2,790.00-$3,267.00`, `$89/$99`)
  yield both amounts, so `sole` hedges fail; a per-period unit after `/`
  (`$89/mo`, `$1,200/yr`) no longer hides the amount. Mention targets may
  carry a per-period suffix (`$299/mo`, `$89 per month`) or an exact
  magnitude (`$4.2M` = 4,200,000; `k` always, `m`/`b` only with `$`); the
  suffix is ignored when deciding "reformatted".
- Clock times: seconds (`14:00:00`, `2:00:00 PM`; text accepts `:00` only)
  and ISO timestamps (`2026-02-10T14:00:00Z`, `2026-02-10 14:00:00+00:00`,
  24-hour as written) are read in mentions and `clock_time` values; a word
  starting with am/pm (`America/Chicago`, `pmc`) is not a meridiem.
- `service.record_writes@1` accepts a single `identity_paths` field for
  collections without `id` (every Xero collection: `[["contact_id"]]`,
  `[["purchase_order_id"]]`); `record_id` is the canonical JSON list
  (`"[\"C-1\"]"`), equal to `initial.records@1` with the same identity_paths.
  `final.records@1` still requires `id`.
- Unpersisted calls: a call that raised before running (or returned with
  `not_attempted`/`unchanged` persistence) and has no write acknowledgement is
  outside every contract effect inventory; the other calls must still chain.
  An acknowledged failed sheet write that left every sheet unchanged
  (`google_sheets_update_row({})`) is skipped. A run with zero tool calls
  closes Sheets scope when public initial state matches the final world.
- Comparisons: a decimal or day-count derivation (`days_between`, arithmetic)
  compares with a plain number literal (`{"kind": "literal", "value": 30}`)
  instead of silently staying unknown; strings and calendar dates still never
  coerce.
- `initial.records@1` field paths may read one key of a string-keyed mapping
  as the last step (`["properties", "lifecyclestage"]` on HubSpot); a missing
  key is a missing field (unknown).
- `load_contract` rejects a contract whose canonical re-save fails validation
  (`contract_canonical_form_inadmissible`, usually the predicate budget once
  defaults are written out) instead of every check failing at scoring.
- Guard scoring computes digests once per cached evaluation (a 1,700-batch
  guard dropped from ~45 s to ~7 s); receipts are unchanged.
- Not changed: `unique_candidate` ambiguity still considers every population
  row (see the round-6 engine report).
