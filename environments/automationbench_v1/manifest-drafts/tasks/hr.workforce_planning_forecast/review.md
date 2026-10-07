# hr.workforce_planning_forecast — Luna manifest review

Whole task: **not_qualified** (11/13 in-scope obligations expressed; 2 gap(s)).

## Expressed checks
- 11 expressed checks; IDs and public anchors are preserved in review.json.

## Gaps
- hiring-committee-recipient [other:recipient_identity]: The recipient cannot be resolved from public sources; do not guess an address or channel.
- paused-requisition-status [other:status-semantics]: The public headcount table has Status=Approved but no paused-state vocabulary or requisition lifecycle source.

## Native replay
- 1 checks replayed; 0/abstentions observed in: hr-director-hold-update; exact outcomes are in review.json.
- Errors=0; finding rescore/reload=True/True; scalar/source bytes unchanged=True/True.

## Native simulator
- positive-hold: errors=0; finding counts retained in review.json.
- freeze-violating-post: errors=0; finding counts retained in review.json.
- freeze-violating-submission: errors=0; finding counts retained in review.json.
- missing-freeze-read-ack: errors=0; finding counts retained in review.json.
- Source authority: public prompt and initial state; hidden assertions do not define requirements.
