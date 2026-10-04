# hr.handbook_acknowledgment — Luna manifest review

Whole task: **not_qualified** (2/4 in-scope obligations expressed; 2 gap(s)).

## Expressed checks (2)
- **leave-exempt-no-reminder** (`leave-exempt-no-reminder`): Per-candidate leave exemption guard; tested with native Gmail handler.
- **reminder-to-noncompliant-employee-and-manager** (`handbook-reminders`): Declared using task public rows and deterministic effect evidence.

## Gaps
- **45-day-escalation** [required_read_ordering]: The escalation cutoff and the current task date have no frozen, authoritative relationship in the current rows; requiring the escalation for rows exactly on the boundary risks turning an unresolved inclusive/exclusive deadline into a guess.
- **three-year-retention** [other:retention_duration]: No public retention ledger or timestamp field establishes record retention duration in this task state.

## Luna replay
- `leave-exempt-no-reminder`: valid=0.0 x8.
- `handbook-reminders`: inapplicable=None x4, valid=0.0 x4.
- Errors: 0; findings repeat/reload: True/True; scalar and episode bytes unchanged: True/True.

## Simulator and limits
- required reminders: Required reminder outcomes scored 1.
- leave-exempt reminder: Leave guard fired and compliance scored 0.
- missing ACK: Reminder obligation abstained.
- wrong manager CC: Affected reminder outcome scored 0.
- Out of scope: system-no-clarifying-questions.
- Out of scope: system-list-only-acted-on.
- Source authority: public prompt and initial state; hidden assertions do not define requirements. Whole-task status remains not qualified while any in-scope obligation is a gap.
