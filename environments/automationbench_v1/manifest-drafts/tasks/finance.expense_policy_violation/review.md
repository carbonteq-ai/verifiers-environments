# finance.expense_policy_violation

Draft contains 2 expressed component obligation(s) and 1 explicit gap(s); 2 system-prompt rules are excluded from qualification scope. Whole-task status is **not qualified**. The recorded Luna score (0.625) is partial and is not evidence of task success.

Native retained-episode replay, serialize/reload/rescore parity, source-byte preservation, and scalar-reward preservation are recorded in `review.json`. Declared replay findings:
- `expense-carol-employee-notice`: valid value=1.0 (obligation_witnessed_required_effect)
- `expense-compliance-summary`: valid value=1.0 (obligation_witnessed_required_effect)

Genuine-handler isolated controls: 4 variants (correct representative, harmful one-field change, withheld ACK, duplicate/gaming). They test a declared component only, not full task execution. Missing ACK remains unknown/abstained.
No positive action credit is assigned. Bound numeric checks establish only the listed entity/field claims; they do not prove every possible conflicting value or report completeness.

## Round 2 review (reviewer A)

Edited. Added goals: Dave notice (recipient from row Email, verbatim Description and Amount), Status updated with "Violation" for the two offending rows (Carol row 4, Dave row 5), Dave Kim and $95 in the compliance summary. Dave is a violation regardless of the alcohol ambiguity: $95 Meals exceeds both the $75 team and $50 individual caps. Added harms: Violation status written on Alice/Bob/Eve rows; violation notice sent to those employees. Luna replay: 5/5 required goals met (official 0.625; the official misses are "Approved" on rows 2,3,6 which the prompt does not state), no harms. No-op: 0 goals, 0 harms. Synthetic controls for both guards and each goal fired as expected (probe in fin_hr/p1.py). Verdict ready.
