# sales.calendly_no_show_followup — round-4 review

Pack `batch-07.json` task 0; Luna episode `ce455d0a…ccf6`. Whole task: **qualified candidate**.

**Coverage.** 12 obligations, 8 in scope; expressed 5 → **8 / 8**. Out of scope: 2 system-prompt
rules, marking the no-show in Calendly, and the "Deal closed" message (CRM stays the authority).

**Decisions on the three former ambiguities (RL lens)**
- C2, which event: the invitee's active event that had already started when the no-show was
  reported (2026-02-15 09:00Z). Only the Discovery Call (Feb 10, 14:00Z) qualifies. The Product Demo
  starts at 15:00Z that day, so nobody could have missed it yet, and the Follow-up Call was cancelled.
  Rewarding the Product Demo would teach the agent to log no-shows for meetings that have not
  happened. The population is all Calendly invitations, with decided event and contact lookups; the
  build asserts exactly one qualifies.
- C3, subject: must equal `Follow up on missed call - Discovery Call` exactly.
- C8, harm (`no-followup-for-other-event`): a missed-call task naming the future or cancelled event.
  This also catches hedging with one task per event.

**Scheduled time (C6).** Accepted: UTC (labelled or not), or a conversion to ET, CT, MT, PT or CET
next to that zone's label. Also accepted: the raw `start_time` copied, its Z form, or `14:00:00`. A
UTC time under a non-UTC label scores 0 (Luna's case). The Product Demo's 15:00 anywhere scores 0
(anti-hedge), except as "15:00 CET".

**Luna replay**: task 1, priority 1, pipeline 1, time **0** (Luna wrote "14:00–14:30
America/New_York" for a 14:00 UTC event), guard compliant. No errors, no failed runs, scalars and
bytes unchanged, rescore and reload repeated.
**Alternatives** (30 runs on the real simulator): 13 correct variants score 1/1/1/1.
- Wrong instants score 0 on time; a bare "2:00" abstains because it is ambiguous.
- Product Demo or Follow-up subjects score task 0 and fire the guard.
- The old $100k threshold scores 0 on priority and on the pipeline total.
- Hedging is caught by the guard or the exact-subject check; a missing ACK abstains.

**Mechanism defects** (reproducers in `round-4/sales-support/repro/`): D1 `clock_time` reads
`14:00:00` and ISO timestamps as absent; D2 "am"/"pm" starting the next word ("08:00
America/Chicago") is taken as a meridiem, so the time is dropped; D3 a contract can load and still
fail every producer run once re-serialised (budget; the draft now uses clock literals); D4 `amount`
reads "$87,000," as absent.

Workarounds for D1/D2/D4 (verbatim source strings) are in the draft. Limits: zones are enumerated;
the meeting date is not required.
