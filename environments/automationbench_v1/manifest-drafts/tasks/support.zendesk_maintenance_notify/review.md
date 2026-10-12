# support.zendesk_maintenance_notify

Original Luna result remains `official_partial` with partial score `0.7222222222222222`. It is retained as an unsolved reference, not treated as the target policy answer.

This draft declares 3 expressible component checks and records 4 remaining public obligation gaps. Native replay: `{'assessment': [], 'credit': []}`; original reward scalar unchanged: `True`; episode bytes unchanged: `True`; reload/rescore finding parity: `True`. Current replay findings, including misses and abstentions, are preserved in `review.json`.

Gaps: recipient-policy, calendar-window-linkage, emergency-exceptions, summary-facts. Synthetic tests exercise genuine handlers but remain component controls; they do not qualify the whole task. No action credit is assigned. Whole-task status: `not_qualified`.

## Revision 2026-10-12 (shard 2 eval validation)

added source emails (gmail send), goals scheduled-window-customer-email and emergency-window-email-subject-and-contact, and harm guard no-notification-for-unscheduled-window. Replayed on the Luna episode with the step-credit reader (outcome counts in manifest-validation/shard2-results.json). draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `ac4df9adb2fbf50bb1fbba28aeb415108153c24faba4df851056a0c98607f02a`.

Edits in this review:
- required set limited to Scheduled windows whose org exists in Zendesk and the preference sheet (row 7 Acme Solutions has no matching org and must not be notified); calendar goal now needs summary mentioning the service and start date instead of summary equal to the service; email goal now needs a contact from the org notes; added Slack goal for the email+slack org (Acme), midnight-crossing note goal for MultiContact, count 4 in summary; added harms for unmatched windows (email, calendar, Notified status) and for Slack to email-only orgs
- calendar harm now also matches the window date so a legitimate event for the same service on another date does not fire it

Luna replay (step-credit reader): 13 of 18 decided required findings met; failing goal checks: calendar-event-per-scheduled-window, scheduled-window-customer-email, scheduled-windows-set-notified, slack-notification-for-email-and-slack-org; harms fired: no-calendar-event-for-unscheduled-or-unmatched-window, no-notified-status-for-unscheduled-or-unmatched-window. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Required set limited to windows whose org exists and has preferences (row 7 Acme Solutions must not be notified; Luna notified and calendared it: two real harms). Row 9 missed, Acme Slack missed.
