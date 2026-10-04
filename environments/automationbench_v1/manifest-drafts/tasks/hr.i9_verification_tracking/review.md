# hr.i9_verification_tracking — Luna manifest review

Whole task: **not_qualified** (1/3 in-scope obligations expressed; 2 gap(s)).

## Expressed checks (1)
- **past-window-legal-notice** (`i9-legal-violation-notice`): Declared using task public rows and deterministic effect evidence.

## Gaps
- **in-window-reminders** [required_read_ordering]: The current public task provides no business-day calendar or holiday list, so the positive cutoff can be verified for clearly overdue starts only; edge dates and in-window actions remain unexpressed.
- **tracker-status-updates** [other:cross_service_ordered_status]: The expressed check covers the legal email only; no matching tracker status transition is declared.

## Luna replay
- `i9-legal-violation-notice`: inapplicable=None x4, valid=1.0 x4.
- Errors: 0; findings repeat/reload: True/True; scalar and episode bytes unchanged: True/True.

## Simulator and limits
- past-deadline legal notices: Required notices to Legal scored 1.
- wrong recipient: Required notices to HR instead scored 0.
- missing ACK: At least one notice abstained and coverage abstained.
- in-window legal notice: Current checks did not flag an extra premature legal notice; in-window handling remains a gap.
- Out of scope: system-no-clarifying-questions.
- Out of scope: system-list-only-acted-on.
- Source authority: public prompt and initial state; hidden assertions do not define requirements. Whole-task status remains not qualified while any in-scope obligation is a gap.
