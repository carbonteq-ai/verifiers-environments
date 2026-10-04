# finance.expense_split_allocation: round 4

Status: **qualified candidate**, with one open gaming risk for review. Coverage 14/16 → **16/16** in-scope obligations; 3 out of scope (two system-prompt rules, residual-cent rule).

## What changed (`draft.json`, 20 checks, outcome-only)
- **E12 expressed (agent-named log columns).** The six log checks read each created Allocations row through `service.record_writes@1` `values_text`, so any header works. Each row must name the expense and the department and contain the correct share (cent or whole dollar).
  - For the Sales, Marketing and Operations training rows, the share (3,000/2,000/1,000) equals that department's Sq Ft. There the share must carry a dollar sign (`usd_marked`) or sit under an "Allocation" header. Otherwise the result stays unknown rather than a guessed 0 or 1.
- **Excluded-expense guard** matches the expense name in any column.
- **E11b expressed.** The email verbatim guard uses `amount_reformatted`, so any reformatted occurrence is harm. A new guard applies the same rule to log rows ("notifications or records").
- **Block-format emails.** An expense and its share in one blank-line paragraph that names no other expense now counts.

## Luna replay (hash-bound, native)
- Holiday party: logs, charges and source amounts are 1.
- Every wrong log and charge is a known 0. That includes the training rows ($3,300/$2,200/$1,100 beside Sq Ft 3,000/2,000/1,000), which a naive `values_text` check would have passed.
- Guards are compliant and scopes close. Scalars and bytes are unchanged; rescoring and reloading repeat the findings.

## Genuine-simulator alternatives (29 runs)
- **Pass:** cents and whole-dollar shares; one email to all heads; tables; HTML-only; blank-line paragraph emails; logs under other headers (marked); Luna-style columns.
- **0 or harm:**
  - Stale headcount, wrong or swapped shares.
  - Reformatted source amounts (email or log), including mixed "$36,000 (36000 USD)".
  - An excluded expense logged under another header; no log.
- **Unknown:** unmarked shares under non-"Allocation" headers for the three training rows. Missing acknowledgement abstains.
- **Gaming:**
  - One-paragraph email shotgun scores 0.
  - **A log row with extra cells listing every candidate share passes every log check.** `values_text` has no "sole amount" test; email lines with several shares have the same weakness. This is recorded as a mechanism request: terms that must be absent from the same unit.

## Limitations
- Wide-format logs (departments as headers) score 0.
- Tight block emails score 0.
- Duplicate conflicting rows are not penalized.
- Presence, not assertion.
