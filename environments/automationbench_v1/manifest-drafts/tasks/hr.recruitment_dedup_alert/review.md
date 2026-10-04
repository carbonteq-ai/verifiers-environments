# hr.recruitment_dedup_alert — Luna manifest review

Whole task: **not_qualified** (2/3 in-scope obligations expressed; 1 gap(s)).

## Expressed checks
- 2 expressed checks; IDs and public anchors are preserved in review.json.

## Gaps
- duplicate-pair-completeness [cross_system_reconciliation]: The source tracker exposes candidate rows, but this contract binds exact known duplicate-email groups and does not prove every external recruitment channel was included.

## Native replay
- 2 checks replayed; 0/abstentions observed in: none; exact outcomes are in review.json.
- Errors=0; finding rescore/reload=True/True; scalar/source bytes unchanged=True/True.

## Native simulator
- positive: errors=0; finding counts retained in review.json.
- wrong-recruiter: errors=0; finding counts retained in review.json.
- missing-read-ack: errors=0; finding counts retained in review.json.
- nonduplicate-flagged: errors=0; finding counts retained in review.json.
- Source authority: public prompt and initial state; hidden assertions do not define requirements.
