# sales.calendly_no_show_followup — batch-12 review v3

Pack `batch-07.json` task 0; Luna episode `ce455d0a…ccf6`. Whole task: **not qualified**.

**Coverage.** 12 obligations, 8 task-specific. Expressed v1 0 → v2 4 → v3 5 (adds C6 scheduled time).
Gaps: 3 `other:public_policy_ambiguity` (C2 which event, C3 exact subject, C8 future event). Out of scope 4
(2 system-prompt rules, 2 reviewed non-obligations).

**New check `followup-scheduled-time`** (mechanisms 6 and 7): for the event named in the subject, the
description must give its start time of day. Accepted: the UTC time (14:00 / 2:00 PM / 2pm) on a line with
no other zone label, or the New York time (9:00 AM) next to ET/EST/Eastern/America/New_York. The minutes
come from `iso_instant` arithmetic on the bound start times. Subject and time are coupled per event.

**Luna replay**: task 1, priority 1, pipeline 1, scheduled time **0**. Luna wrote '14:00–14:30
America/New_York' for a 14:00 UTC event, which states the wrong instant. Bindings verified, no errors,
scalars and bytes unchanged, rescore/reload repeated.

**Alternatives** (16 runs): 6 correct variants give 1/1/1/1. Mislabelled zone, Product Demo time under a
Discovery Call subject, and no time are known 0. A bare '2:00' abstains. Old threshold, cancelled event and
missing description stay known 0 (D2 fixed). Missing ACK abstains.

**Remaining gaps.** C2/C3/C8 still need a decision. Reading A ('event dated today', not yet started) is
now decidable with iso_instant. Reading B ('most recent past event') still needs member-level lookups
inside selections.

**Limits.** Zone handling is enumerated: a correct conversion to another zone ('6:00 AM PT') is a false 0.
Smallest fix: a `mentions` instant mode that reads a time with its zone label. Date is not required.
**Defects:** none new.
