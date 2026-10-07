# hr.performance_review_cycle — Luna manifest review

Whole task: **not_qualified** (3/4 in-scope obligations expressed; 1 gap(s)).

## Expressed checks (3)
- **new-hires-not-listed** (`new-hires-not-listed`): Per-candidate new-hire exclusion guard; tested with native Gmail handler.
- **eligible-direct-report-manager-email** (`review-eligible-report`): Declared using task public rows and deterministic effect evidence.
- **q1-managers-channel-announcement** (`q1-managers-announcement`): Declared using task public rows and deterministic effect evidence.

## Gaps
- **complete-manager-lists** [report_fact_coverage]: The per-employee notice check verifies eligible people are named to their listed manager, but it cannot prove each manager receives one complete, deduplicated list.

## Luna replay
- `new-hires-not-listed`: valid=0.0 x5.
- `review-eligible-report`: valid=1.0 x3, inapplicable=None x2.
- `q1-managers-announcement`: valid=1.0 x1.
- Errors: 0; findings repeat/reload: True/True; scalar and episode bytes unchanged: True/True.

## Simulator and limits
- eligible reports and announcement: Eligible manager notices and managers-channel announcement scored 1; retained episode omitted some eligible rows.
- new hire listed: New-hire guard fired.
- missing ACK: Read-dependent notice outcome and coverage abstained.
- shotgun new-hire line: Guard fired on the excluded hire; complete manager-list aggregation remains a gap.
- Out of scope: system-no-clarifying-questions.
- Out of scope: system-list-only-acted-on.
- Source authority: public prompt and initial state; hidden assertions do not define requirements. Whole-task status remains not qualified while any in-scope obligation is a gap.
