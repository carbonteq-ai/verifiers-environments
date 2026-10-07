# hr.safety_incident_reporting — Luna manifest review

Whole task: **not_qualified** (8/10 in-scope obligations expressed; 2 gap(s)).

## Expressed checks
- 8 expressed checks; IDs and public anchors are preserved in review.json.

## Gaps
- five-year-retention [other:retention_duration]: Public state has no retention ledger or retained-until timestamps to verify five years.
- return-to-work-assessment [other:conditional_case_absent]: No public incident row identifies an employee currently returning from injury leave; the conditional branch has no positive test case.

## Native replay
- 8 checks replayed; 0/abstentions observed in: minor-routing, moderate-routing, serious-routing, safety-channel-incident-facts; exact outcomes are in review.json.
- Errors=0; finding rescore/reload=True/True; scalar/source bytes unchanged=True/True.

## Native simulator
- positive: errors=0; finding counts retained in review.json.
- wrong-recipient: errors=0; finding counts retained in review.json.
- missing-manual-read-ack: errors=0; finding counts retained in review.json.
- partial-slack-summary: errors=0; finding counts retained in review.json.
- Source authority: public prompt and initial state; hidden assertions do not define requirements.
