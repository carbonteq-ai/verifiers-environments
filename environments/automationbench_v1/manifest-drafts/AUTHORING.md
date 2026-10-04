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
## Google Sheets reads (2026-10-04)

24. Sheets read evidence: effect source `{"adapter": "google_sheets.reads@1",
    "spreadsheet_id": <id>, "worksheet_id": <id>}` (`kind` is `read_sheet`
    and may be omitted; omit `worksheet_id` to accept any worksheet of the
    spreadsheet). Use it for "check the guidelines/policy/legal-hold sheet
    before acting". One fact per acknowledged successful read call per
    returned worksheet: `google_sheets_get_many_rows`,
    `google_sheets_find_many_rows`, `google_sheets_lookup_row`,
    `google_sheets_get_row_by_id`, `google_sheets_find_worksheet`,
    `google_sheets_get_spreadsheet_by_id` (one fact per worksheet it lists).
    Params: `spreadsheet_id`, `worksheet_id`, `worksheet_title` (pre-call
    world), `row_ids` and `native_row_ids` (returned rows, in order; the
    native ids equal `candidate.native_record_id` of a `google_sheets.rows@1`
    population of the same worksheet), `row_count`, `returned_fields`
    (columns whose values came back), `cell_values_returned` (true when some
    returned row carried cell values), `all_rows_returned` (every row of the
    worksheet came back), `operation`.
    Closure works like Slack/Gmail reads (mechanisms 12, 19): the target is
    resolved with the simulator's own ID/title resolution over the pre-call
    world; every returned row must exist in that worksheet with the same cell
    values and returned worksheet metadata must match, so a rewritten result
    cannot invent a read. Failed reads (unknown sheet/tab/row, errors) return
    nothing; a successful search that matched no row, `find_worksheet`, and
    `get_spreadsheet_by_id` without grid data still read the worksheet but
    with `row_count` 0 and `cell_values_returned` false — require
    `cell_values_returned` (or row membership) when the content matters.
    Reads of another spreadsheet/worksheet are not facts for this selector.
    Sheets writes (add/append/update/delete row, create spreadsheet or
    worksheet) are not reads; Drive file search returns nothing; calls whose
    footprint excludes Sheets and left it unchanged are skipped; `api_fetch`
    (including the v4 `values` endpoints) and unknown tools leave the
    inventory incomplete; a complete inventory needs every ACK and a
    public-initial/terminal Sheets reconciliation. Usable as an obligation
    `source` (not a guard source) and as an `effect_joins` source in
    obligations and guards. "Read ws_legal_hold before purging":

    ```json
    "sources": {"holds": {"adapter": "google_sheets.rows@1",
                  "path": ["task_evidence", "initial", "google_sheets"],
                  "spreadsheet_id": "ss_gdpr", "worksheet_id": "ws_legal_hold", "key_fields": ["Email"]},
                "hold_reads": {"adapter": "google_sheets.reads@1",
                  "spreadsheet_id": "ss_gdpr", "worksheet_id": "ws_legal_hold"},
                "purges": <the purge effect source>},
    "checks": [{"check_id": "purge-after-legal-hold-read", "operator": "effects.required_when@1",
      "semantics": "new_occurrence", "population": <requests>, "source": "purges",
      "effect_joins": [{"alias": "hold_read", "source": "hold_reads", "timing": "before", "match": "any",
        "where": {"op": "eq", "left": {"kind": "field", "path": ["joined", "cell_values_returned"], "domain": "boolean"},
                  "right": {"kind": "literal", "value": true}}}],
      "effect_match": {"op": "all", "args": [
        {"op": "eq", "left": {"kind": "field", "path": ["join", "hold_read"]},
         "right": {"kind": "literal", "value": "matched"}},
        <the purge targets this request>]}, ...}]
    ```

    To require that a specific row was returned, use membership:
    `{"op": "in", "left": {"kind": "field", "path": ["candidate", "native_record_id"]},
    "right": {"kind": "field", "path": ["joined", "native_row_ids"], "domain": "sequence"}}`
    (as an obligation source, read `effect.native_row_ids`). Read-then-act is
    1, act-then-read is 0 with `timing: "before"`, reading another worksheet
    or another row is 0, a write-only call is not a read, a missing ACK is
    unknown. When the effect match does not depend on the candidate row, set
    `match_cardinality: "per_candidate"` (mechanism 16).

## Shared verification capabilities, round 7c (2026-10-05)

Mechanisms 25–27 belong to the concurrent engine round r7
(`any_item`/`all_items`, LinkedIn reads, the `prefix` mention mode). These
are new:

28. Execution-order joins: `effect_joins[].order` is
    `"returned_before_dispatch"` or `"overlapping"` and requires
    `timing: "any"` (state-revision order and receipt order are never mixed).
    They read the authenticated native receipt sequence (`receipt_seq`, one
    `dispatch` and one terminal event per tool-server invocation):
    - `returned_before_dispatch`: the joined call's `returned` event precedes
      the evaluated call's `dispatch` (a raised/interrupted or later return is
      a decided no). "Read the config before acting" is then a server-boundary
      fact, not merely "acted on later state".
    - `overlapping`: both calls ended and each was dispatched before the other
      ended. A serialising server makes calls emitted in one model turn
      disjoint, so "fetch in parallel" is usually a known 0 in these traces.
    Missing, malformed or contradictory order evidence (or a pending call for
    `overlapping`) is unknown. Neither relation says the model used the
    response; returned content is still the read adapter's `joined.*`
    (`cell_values_returned`, `native_row_ids`, ...); model conditioning is not
    evidenced by receipts. Join existing reads/effects with:

        "effect_joins": [{"alias": "config_read", "source": "config_reads", "timing": "any",
          "match": "any", "order": "returned_before_dispatch",
          "where": {"op": "eq", "left": {"kind": "field", "path": ["joined", "cell_values_returned"], "domain": "boolean"},
                    "right": {"kind": "literal", "value": true}}}],
        "effect_match": {"op": "eq", "left": {"kind": "field", "path": ["join", "config_read"]},
                         "right": {"kind": "literal", "value": "matched"}}

    For "the three reads ran in parallel" use a read source with a join to
    another read source and `order: "overlapping"`.
29. Generic fresh-object outcomes: `objects.created_and_retained@1` accepts
    the source `{"adapter": "final.created_records@1", "service": <service>,
    "collection": <top-level list with string id>, "references": {<alias>:
    {"field": <string field>, "collection": <same-service list>}}}` (up to 4
    references). `retained.id`, `retained.record.*` (raw terminal record) and
    `retained.<alias>.*` (the unique terminal record whose `id` equals the
    reference field) are readable. Fresh = id absent from the public initial
    collection; identities are complete only when every public record has an
    explicit string id and an omitted collection hydrates empty. A missing or
    ambiguous reference publishes nothing (unknown). Outcome only:
    `created_retained_completion_once@1` credit is rejected for it. Gmail
    draft retained with its content:

        "drafts": {"adapter": "final.created_records@1", "service": "gmail", "collection": "drafts",
                   "references": {"message": {"field": "message_id", "collection": "messages"}}}
        "retained_when": {"op": "all", "args": [
          {"op": "in", "left": {"kind": "field", "path": ["request", "recipient"], "domain": "string"},
           "right": {"kind": "field", "path": ["retained", "message", "to"], "domain": "sequence"}},
          {"op": "in", "left": {"kind": "literal", "value": "DRAFT"},
           "right": {"kind": "field", "path": ["retained", "message", "label_ids"], "domain": "sequence"}}]}

    Authoring diagnosis for created drafts (not a new adapter): a Gmail
    `drafts` record is only `{id, message_id}`, so a `service.record_writes@1`
    `drafts` check reading `effect.record.to` is unknown and abstains with
    `obligation_effect_scope_unavailable` (that reason also covers an unknown
    match over a complete inventory). The same `gmail_create_draft` call also
    creates a `messages` record carrying `to`, `subject`, `body_plain` and
    `label_ids: ["DRAFT"]`: use `service.record_writes@1` `collection:
    ["messages"]`, `kind: "create"`, and (to bind it to the draft object) a
    join to the `drafts` create with `timing: "not_after"` and `where`
    `joined.record.message_id == effect.record_id`.
30. Typed report fields: `{"op": "labeled_value", "text": <string field>,
    "label": <operand>, "format": usd_string|usd_marked|decimal_string,
    "value": <operand, optional>, "precision": <mechanism 31, optional>,
    "entity": <words term, optional>, "scope": "line"|"block",
    "excluding": [longer label names]}`. A label (case/hyphen insensitive:
    "Cost-per-applicant" = "cost per applicant") states values only as
    `<label><connector><values>` (connectors `:`, `=`, dashes, `(`, `is`,
    `was`, `are`, `were`, `of`, `at`, `equals`, `total`), `<values> [:|-|in|of|for]
    <label>` at a segment start, or `<label>: <calculation> = <values>` (only
    the values after the last `=`/`->`/`→`). `<values>` is a run joined by
    `,`, `-`, `/`, `~`, `to`, `or`, `and`, `through`, `vs` or `(or`, so a hedge
    states every alternative. Segments end at `;`, `|`, tab, `•` or a sentence
    end. A later explanation after other words ("$40,000 (80% of $50,000)")
    is not stated; a label whose segment has numbers only after other words
    ("cost per applicant for the quarter is $100") is unknown; percents and
    years are never values. With `value`: true when some value is stated and
    all stated values equal it; false on any differing readable value
    (hedge, conflicting repeat) or none stated; unknown when undecidable or
    quoted/fenced only. Without `value`: true when any value is stated (an
    excluded entity entered with an amount). With `entity`, only units naming
    the entity count; in `block` scope one block must describe one entity
    (use `line` when a block lists several). HR cost-per-applicant (spend and
    other labels on nearby lines no longer interfere; "$100 or $175" fails):

        {"op": "labeled_value", "text": {"kind": "field", "path": ["effect", "body_text"], "domain": "string"},
         "scope": "block", "format": "usd_string", "label": {"kind": "literal", "value": "Cost-per-applicant"},
         "entity": {"value": {"kind": "field", "path": ["request", "Role"], "domain": "string"}, "mode": "words"},
         "value": {"kind": "derived", "expression": {"kind": "decimal", "op": "div",
           "left": {"kind": "input", "format": "usd_string", "path": ["request", "Spend"]},
           "right": {"kind": "input", "format": "decimal_string", "path": ["request", "Total Applicants"]}}}}

    Excluded row entered with an amount (guard `effect_match`, with
    `match_cardinality: "per_candidate"`): `{"op": "labeled_value", "text":
    ..., "format": "usd_string", "label": {"kind": "field", "path":
    ["request", "Customer"], "domain": "string"}}` — "Dispute Holdings —
    $1,000" fires; "Dispute Holdings was excluded from the calculation." does
    not. Whether a stated `$0` is a prohibited entry is the author's policy
    call; the predicate reports it as stated.
31. Declared numeric precision: `"precision": {"min_places": <0-20>,
    "max_places": <optional>, "ties": "half_up"|"half_even"|"either"}` on an
    `amount` term (`mentions`, `mentions_together` terms) or on
    `labeled_value`, only when `value` is a `derived` arithmetic expression
    (`kind: "decimal"`); a literal, a bare input (a verbatim source value) or
    a `round` expression is rejected. A written number with `p` decimal places
    matches when it equals the exact value, or when `min_places <= p <=
    max_places` and it equals the exact value rounded to `p` places. A
    truncation ("46666.66" for 140000/3), a wrong extra digit ("46666.670")
    or a coarser rounding than `min_places` is false. Without `precision` a
    repeating quotient stays unknown (as before). Justify `min_places` from
    public inputs in the review (e.g. currency cents → 2); do not choose it to
    reproduce one episode's formatting. `decimal_string` rejects digit
    grouping ("46,666.67"); `usd_string` accepts it.
32. Initial-state reconciliation (engine correction): fields public state
    omits are now compared with their deterministic hydrated defaults (an
    omitted Gmail `body_html` is null, `label_ids`/`cc` are empty), and a
    free-form mapping (HubSpot `properties`) must not gain keys. Only
    generated values are tolerated: defaults produced by an id/clock
    factory, and values that differ between two hydrations of the same public
    state. Values a validator derives from public input (Gmail
    `internal_date` from `date`, HubSpot `status` stored as
    `hs_pipeline_stage`) are compared. Across the 120 Luna episodes all 335
    public-service/initial-snapshot comparisons still reconcile. Eight
    public-initial-versus-terminal comparisons now correctly differ where the
    old rule certified "unchanged": the agent wrote HubSpot
    `properties.payment_retry_count`, or created Asana/Jira/Monday/Notion
    records (new keys in a service's `actions` mapping). Adapters use that
    comparison only when no call touched the service.
## Engine corrections round 7 (2026-10-04)

- Schema aliases in record paths: `initial.records@1` and `final.records@1`
  field paths may name a canonical schema field or one of its plain-string
  schema aliases, at any step. Either spelling reads the field under whichever
  key the raw record carries: public initial state is raw JSON written with
  aliases (HubSpot `lifecycle_stage`), terminal snapshots use canonical names
  (`lifecyclestage`). `["lifecycle_stage"]` and `["lifecyclestage"]` are
  equivalent; the path is kept as written, so selector digests do not change.
  A record carrying both keys with different values leaves the field unread
  (unknown); an omitted field is unread, never the schema default (`"lead"`).
  Use `["lifecycle_stage"]` for HubSpot contacts and companies instead of
  literal id lists. `["properties", "lifecyclestage"]` is a different field
  (a key of the `properties` mapping).
- `final.records@1` (and `records.retained_when@1` predicates, aggregates and
  record completion) read one key of a string-keyed mapping as the last step,
  like `initial.records@1`: `"fields": {"Risk": ["properties", "churn_risk"]}`
  or `["retained", "Props", "churn_risk"]` with `"Props": ["properties"]`. A
  missing key is unread (unknown). Prefer this over kept-value join chains for
  "the field ends as X".
- Gmail send scope: audited Gmail filing handlers (`gmail_add_label_to_email`,
  `gmail_remove_label_from_email`, `gmail_remove_thread_label`,
  `gmail_create_label`, `gmail_mark_as_read`, `gmail_mark_as_unread`,
  `gmail_archive_email`, `gmail_trash_email`, `gmail_star_messages`) are
  non-send writes for `gmail.messages@1` when their static footprint is Gmail
  only and the observed change touches nothing but existing messages'
  `label_ids`/`is_read`/`is_starred` and label definitions (same message ids,
  order and content). A run that only labels mail now closes send scope, so a
  missing confirmation is 0 rather than unknown. Any other observed change
  under those names keeps the inventory incomplete, and so does adding `SENT`
  or removing `DRAFT` (relabelling a draft imitates delivery).
- `unique_candidate` trap with read joins (diagnosis of
  `sales.full_sales_cycle_orchestrator`, check
  `stage-advanced-after-playbook-read`): the Slack read inventory on the Luna
  episode is complete and contains the playbook read (`slack_find_message_in_channel`
  at revision 1, before the stage update at revision 13), but Luna also listed
  the channel (`slack_get_channel_messages`, 20 messages). The population is
  every Slack message, so the one stage update matched 21 candidate rows
  through `joined.native_record_id == candidate.native_record_id`; with
  `match_cardinality: "unique_candidate"` a multi-candidate effect is never a
  witness, so the check abstained. Not an engine bug: when the effect match
  depends on the candidate only through a join (or not at all), declare
  `"match_cardinality": "per_candidate"` (mechanism 16). With it the Luna
  episode scores 1.
- Counts and amounts: a count written verbatim in the prompt may appear
  reformatted ("12,000" vs "12000"); use `mode: "amount_reformatted"` (or
  `amount` with a format) for counts in messages, not `verbatim`.
- `mentions` `mode: "prefix"` (below) for reference-code prefixes; `verbatim`
  is unchanged and keeps token boundaries ("INS-" never matches inside
  "INS-2026-014").
- `service.record_writes@1` update facts carry `added_items`: for every
  top-level field that is a list both before and after, the items present after
  but not before (multiset difference, AFTER order; `[]` when nothing was
  added). "The new message is customer-visible":
  `{"op": "any_item", "items": {"kind": "field", "path": ["effect", "added_items", "messages"]},
  "where": {"op": "eq", "left": {"kind": "field", "path": ["item", "visibility"], "domain": "string"},
  "right": {"kind": "literal", "value": "public"}}}`. Lists nested deeper
  (e.g. inside action `params`) are not diffed; read them from `effect.record`.
- Join `timing: "after"` (see mechanism 8/11): only effects committed strictly
  after the evaluated effect (`applied_revision` greater) are tested. Use it
  for exact self-correction exemptions ("unless a later write restores it"):
  `{"alias": "restored", "source": "updates", "timing": "after", "match": "any",
  "where": <same record, restored value>}` and require `join.restored == "none"`.
  `before`, `not_after` and `any` are unchanged.
- Replay cost: decoded snapshot worlds are shared by every effect index in
  the process, and adapter/guard/obligation input captures are memoised by
  (source digest, selector), so checks, restores and credit planning stop
  re-decoding and re-diffing the same episode; receipts are unchanged. Measured
  on `support.zendesk_hubspot_org_sync` (full draft, one scoring pass): 25.3 s
  -> 20.7 s. The 20-minute reviewer replays are not scoring: about 1,150 s of
  the 1,240 s `luna()` run is `vf.WireEpisode.model_validate_json` re-parsing
  the episode after two scoring passes have attached ~2,100 assessment batches
  (the reload check). Run that reload check once, on the final draft only.
  Scoring itself is dominated by the Verifiers framework re-verifying the
  shared view per assessment request (one request per candidate per check), so
  large populations with many inapplicable candidates cost time; prefer
  narrow populations where the public data allows.

25. Quantifiers over list items:
    `{"op": "any_item" | "all_items", "items": <field operand naming a list>,
    "where": <predicate>, "max_items": 4096}`. `where` reads `item` (the
    current element: `["item"]` for a scalar list, `["item", <key>, ...]` for
    records) plus the enclosing context (`effect.*`, `request.*`, `joined.*`,
    lookups...). `any_item` is true when some item is proven, false when every
    item is decided false (empty list: false), else unknown. `all_items` is
    false when some item is decided false, true when every item is proven
    (empty list: true), else unknown. An unresolved, null or non-list `items`
    (or one over `max_items`) is unknown. `items` must be a plain field operand
    (no `domain`/`allowed`); `item.*` outside a quantifier is rejected at load
    like any unknown root, and a nested quantifier's `item` shadows the outer
    one (and any lookup alias named `item`). Evidence paths report the element
    read (`effect.record.members.1.role`). Allowed wherever predicates are.
    "A DocuSign room member with email X and role Y":

        {"op": "any_item", "items": {"kind": "field", "path": ["effect", "record", "members"]},
         "where": {"op": "all", "args": [
           {"op": "eq", "left": {"kind": "field", "path": ["item", "email"], "domain": "string"},
            "right": {"kind": "field", "path": ["request", "Email"], "domain": "string"}},
           {"op": "eq", "left": {"kind": "field", "path": ["item", "role"], "domain": "string"},
            "right": {"kind": "literal", "value": "signer"}}]}}

    "The label list contains Z" on a scalar list: `"where": {"op": "eq",
    "left": {"kind": "field", "path": ["item"]}, "right": {"kind": "literal",
    "value": "Z"}}` (or the existing `in` with `domain: "sequence"`). Replace
    fixed positions wrapped in `proven`: they fail a correct agent that orders
    the list differently.

26. LinkedIn read evidence: effect source `{"adapter": "linkedin.reads@1"}`
    (`kind` is `read_record` and may be omitted). Use it for "research the
    attendees / check profiles and recent posts before outreach". One fact per
    record an acknowledged successful read returned: `linkedin_get_profile`,
    `linkedin_find_profile` (profiles and denormalised connections),
    `linkedin_get_my_profile`, `linkedin_get_connections`,
    `linkedin_find_post`, `linkedin_get_company`, `linkedin_list_companies`.
    Job lookups (`linkedin_get_job`, `linkedin_find_jobs`) return no facts.
    Params: `record_type` (`profile`|`connection`|`company`|`post`),
    `record_id` (native `id` in the pre-call world), `identity` (best stable
    identity: a profile's id, a connection's `connected_profile_id`, else its
    `email`, else null; a company's or post's id), `profile_id`, `email`,
    `full_name`, `public_profile_url` (profiles), `company`, `headline`;
    companies add `name`; posts add `author_id`, `text`, `is_deleted`; plus
    `returned_fields` and `operation`. A connection's `id` is generated at
    hydration when public state omits it, so never key on a connection's
    `record_id`; use `identity`, `profile_id` or `email`. Closure works like
    mechanisms 19/24: every returned record must exist in the pre-call world
    under its id and every returned field must agree with it (a rewritten
    result cannot invent a read); failed/empty reads return nothing; LinkedIn
    writes (messages, invitations, shares, company updates) are not reads;
    calls whose footprint excludes LinkedIn and left it unchanged are skipped;
    `api_fetch` and unknown tools leave the inventory incomplete; a complete
    inventory needs every ACK and a public-initial/terminal LinkedIn
    reconciliation. Usable as an obligation `source` (not a guard source) and
    as an `effect_joins` source in obligations and guards. "Email each attendee
    only after reading their profile" (attendees = `initial.records@1` over
    `linkedin.profiles`, whose `candidate.native_record_id` is the profile id):

        "effect_joins": [{"alias": "profile", "source": "li_reads", "timing": "before", "match": "any",
          "where": {"op": "all", "args": [
            {"op": "eq", "left": {"kind": "field", "path": ["joined", "record_type"]},
             "right": {"kind": "literal", "value": "profile"}},
            {"op": "eq", "left": {"kind": "field", "path": ["joined", "identity"]},
             "right": {"kind": "field", "path": ["candidate", "native_record_id"]}}]}}],
        "effect_match": {"op": "all", "args": [
          {"op": "eq", "left": {"kind": "field", "path": ["join", "profile"]},
           "right": {"kind": "literal", "value": "matched"}}, <the send targets this attendee>]}

    For "check their recent posts", join a `record_type == "post"` fact with
    `joined.author_id` equal to the attendee's profile id. Key on email
    (`joined.email`) when the attendee list comes from another service.
    Remember `match_cardinality: "per_candidate"` when the effect match does
    not otherwise depend on the candidate (mechanism 16).

27. `mentions` / `mentions_together` term `mode: "prefix"`: the exact source
    string starts a token that continues with at least one more word
    character, with the same left boundary as `verbatim` (no word character
    or `$` before it). `"INS-"` matches `"INS-2026-014"`; it does not match
    `"INS-"` alone, `"XINS-1"` or quoted/fenced lines (unknown). Use it for
    "cite the incident/ticket number" when only the prefix is public.
