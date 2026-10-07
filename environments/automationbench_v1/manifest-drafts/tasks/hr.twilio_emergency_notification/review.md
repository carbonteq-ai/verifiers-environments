# hr.twilio_emergency_notification — Luna manifest review

Whole task: **not_qualified** (4/5 in-scope obligations expressed; 1 gap(s)).

## Expressed checks
- 4 expressed checks; IDs and public anchors are preserved in review.json.

## Gaps
- tomorrow-date-fact [other:date_mention]: The SMS check requires the word tomorrow but does not require a canonical March 21 date in the message.

## Native replay
- 4 checks replayed; 0/abstentions observed in: sms-to-ineligible-person, facilities-emergency-email; exact outcomes are in review.json.
- Errors=0; finding rescore/reload=True/True; scalar/source bytes unchanged=True/True.

## Native simulator
- positive: errors=0; finding counts retained in review.json.
- opted-out-sms: errors=0; finding counts retained in review.json.
- missing-directory-read-ack: errors=0; finding counts retained in review.json.
- duplicate-sms: errors=0; finding counts retained in review.json.
- Source authority: public prompt and initial state; hidden assertions do not define requirements.
