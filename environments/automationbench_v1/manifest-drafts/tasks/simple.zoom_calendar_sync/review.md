# simple.zoom_calendar_sync (round 6)

Status: **qualified_candidate** — 9/9 in-scope obligations expressed, 0 gaps, 2 out of scope.

## Obligations

- O1-zoom-meeting (goal, expressed, `zoom-meeting-created`): Zoom meeting create with exact topic.
- O2-zoom-start (goal, expressed, `zoom-start`): start_time reads 2026-03-02 09:00 as written (no timezone is public); not later changed away; a zoom_update_meeting that sets it counts (self-correction).
- O3-zoom-duration (goal, expressed, `zoom-duration`): duration == 45 (the tool default is 60).
- O4-zoom-host (goal, expressed, `zoom-host`): host_email exact.
- O5-calendar-event (goal, expressed, `calendar-event-created`): Event whose summary equals the meeting title and that is not deleted.
- O6-calendar-start (goal, expressed, `calendar-start`): start__dateTime reads 2026-03-02 09:00; same change-away / fix-by-update rules.
- O7-calendar-end (goal, expressed, `calendar-end`): end__dateTime reads 2026-03-02 09:45.
- O8-single-meeting (guard, expressed, `duplicate-zoom-meeting`): Harm: a second meeting with the same title (no Zoom delete tool exists).
- O9-single-event (guard, expressed, `duplicate-calendar-event`): Harm: a second event with the same title, unless it or its twin is deleted (self-correction).
- SYS-no-clarification (guard, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.
- SYS-list-only-acted-items (report, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.

## Luna replay

No errors; rescore and reload equal; scalar rewards and episode bytes unchanged. Values: calendar-end=1.0, calendar-event-created=1.0, calendar-start=1.0, duplicate-calendar-event=0.0, duplicate-zoom-meeting=0.0, zoom-duration=1.0, zoom-host=1.0, zoom-meeting-created=1.0, zoom-start=1.0.

## Simulator runs and gaming

H5 create-then-delete event -> O5-O7 0; H6/H7 change the time after creating -> start 0; H8/H9 duplicates -> guard 1; C3 fix by update and C4 duplicate-then-delete are not penalised.

Mechanism notes: Authoring trap (not an engine defect): Zoom meeting ids are integers, so `record_id` compared with domain 'string' made every join unknown (H6 abstained). Use domain 'scalar' for record ids.
