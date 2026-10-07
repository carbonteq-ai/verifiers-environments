# operations.calendar_airtable_gmail_maintenance_notice - round 6 review (ops-b)

Task: schedule the approved, unblocked Data Closet shutdown on cal_ops, log it on Airtable
rec_200 and email it-ops.

**Coverage: 9 / 10 in-scope obligations expressed, 1 gap, 2 out of scope. Status: not qualified.**

Eligibility from the plan: Data Closet + Approved + no SUPERSEDED/security/contract/awaiting
note -> 2026-02-22 02:00-04:00Z only.

Checks: cal_ops event at the exact start/end naming Data Closet; Airtable write naming
rec_200 (+ base_ops or Maintenance) with the date and both times, tied to the event; email
to it-ops with system, date and times, tied to the event; no event at a held window's start
on any calendar; no email/Airtable text stating a held window's date; no delete/cancel of
the scheduled event.

Gap: 'review all scheduling guidelines in the plan first' - no Sheets read evidence source
(required_read_ordering).

Luna: all goals 1, no harm, no errors; scalars and bytes unchanged; rescore/reload repeat.

Simulator: verbatim and prose-time correct paths score 1; the SEC-hold window fires both
guards and earns nothing; primary calendar earns no event credit; listing other windows'
dates fires the announcement guard; schedule-then-delete fires the undo guard; notice with
no event earns nothing; missing ACK stays unknown.

## Calendar current check addendum (2026-10-05)

A current-hash genuine-handler control set now covers `scheduled-window-cancelled`: unrelated deletion is valid/0, canceling the requested event is valid/1, and an unacknowledged cancellation abstains. The ordinary event, Airtable, and email goals remain valid/1 in the positive scenario. The read-before-act requirement remains unsupported. Full source hashes and candidate findings are in `/tmp/automationbench-ops-review-addenda-20261005/calendar_airtable_gmail_maintenance_notice-current-controls.json`.

A later shared `predicates.py` change (current SHA-256 `cd2dcf3358cedb128f39f194b56105e712bf17906d8e8bd1ec61a5e2d413cab6`) only altered trailing-colon amount parsing. This cancellation check does not use that operator; the executed controls remain historical under their recorded helper hashes, not restamped to the new source.
