# hr.visa_expiry_tracking — Luna manifest review

Whole task: **not_qualified** (5/8 in-scope obligations expressed; 3 gap(s)).

## Expressed checks
- 5 expressed checks; IDs and public anchors are preserved in review.json.

## Gaps
- renewal-urgency-window [other:renewal_deadline]: There is no public urgency window that determines whether all remaining cases should be emailed/filed now.
- hr-direct-filing-prohibition [other:unsupported_filing_effect]: The declared public tools expose no immigration petition submission source to verify or prohibit an HR filing.
- requested-amounts-absent [other:missing_public_amount]: No amount can be copied or derived from public inputs.

## Native replay
- 5 checks replayed; 0/abstentions observed in: no-direct-dependent-email, pending-i140-not-to-attorney, no-green-card-renewal-notice, h1b-pending-i140-notice, dependent-included-attorney; exact outcomes are in review.json.
- Errors=0; finding rescore/reload=True/True; scalar/source bytes unchanged=True/True.

## Native simulator
- positive-special-routes: errors=0; finding counts retained in review.json.
- missing-contacts-policy-ack: errors=0; finding counts retained in review.json.
- dependent-direct-email: errors=0; finding counts retained in review.json.
- pending-i140-to-attorney: errors=0; finding counts retained in review.json.
- Source authority: public prompt and initial state; hidden assertions do not define requirements.
