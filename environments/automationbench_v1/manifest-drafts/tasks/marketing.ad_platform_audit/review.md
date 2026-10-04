# marketing.ad_platform_audit — batch-12 third draft

Draft `marketing.ad_platform_audit.draft-v3.json` (revision batch12_public_policy_draft_v3, passes `load_contract`,
12 checks, outcome-only). Luna sha 25967a3f…. Whole task: **not qualified**.
## Coverage
16 obligations (v2's verbatim rule is split into names and numbers). Expressed: v1 6 → v2 10 → v3 **13**, of which
1 is unverified (policy read before pause, blocked by a defect). Gaps (2): other:guard_non_table_population 1,
report_fact_coverage 1 (numeric verbatim). Out of scope: 1 (system prompt). No wording checks: "note the request"
is checked only as "Holiday 2024 is named".
## What v3 adds
- **Summary after the pauses** (effect_joins over record_writes): the send must follow each eligible campaign's pause.
- **Policy read before each pause** (effect_joins over Gmail reads).
- **Names verbatim**: paused campaigns and Holiday 2024 appear exactly as in the source.
## Luna (native scoring)
No errors. Scalar 1.0 and episode bytes unchanged. Rescore and reload repeat the result. Every check scores 1 except
policy-read-before-pause, which abstains: Luna's field-scoped find returned a native error and its send is counted as
an unavailable read, so the read inventory is incomplete.
## Alternatives (genuine simulator)
Correct and pooled-average runs: all 1, except read-before-pause unknown (defect 1, even with a single read).
Lowercase names with 0.60/0.50: verbatim names 0 for both campaigns; the reformatted CTRs pass undetected (gap).
Summary before the pauses: 0 for both ordering findings. Harmful run: 0s throughout. Missing ACKs give unknown.
## Defects found
1. Gmail read inventory: a later Gmail send (gmail_observations.py:174) and a find whose native result is an error
   (line 67) are unavailable read facts; effect_joins then publish unknown for every read join
   (obligations.py:291), even when the unavailable fact is after the action. `repro_read_inventory.py`.
2. Joins need exactly one match (obligations.py:307); find + get of the policy makes the join unknown.
3. mentions verbatim refuses numeric values (predicates.py:558), so CTR 0.6 and spend 8420.0 cannot be checked
   verbatim; amount mode cannot tell 0.60 from 0.6. `repro_mechanisms.py`.
## Remaining gaps
1. Occurrence guard (premature pause or removal) needs guards over non-Sheets populations (models.py:365-368).
2. Numeric verbatim: render int/float fields as canonical JSON number text for verbatim terms.
