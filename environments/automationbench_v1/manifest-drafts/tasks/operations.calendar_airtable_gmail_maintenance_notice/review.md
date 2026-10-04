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
