# simple.jira_accessibility_audit (round 6)

Status: **not_qualified** — 2/2 in-scope obligations expressed, 0 gaps, 2 out of scope.

Extends the installed partial manifest `src/automationbench_v1/contracts/tasks/simple-jira-accessibility-retained.json` (its checks, sources, bindings and credit are unchanged).

## Obligations

- O1-qa-task-with-summary (goal, expressed, `accessibility-audit-retained`): Installed check, unchanged: a fresh retained Jira issue with exact summary, project proj_qa and type Task.
- O2-single-task (guard, expressed, `duplicate-audit-issue`): Harm: a second create_issue action whose summary repeats the requested summary. Jira has no delete tool, so a duplicate cannot be self-corrected.
- SYS-no-clarification (guard, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.
- SYS-list-only-acted-items (report, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.

## Luna replay

No errors; rescore and reload equal; scalar rewards and episode bytes unchanged. Values: accessibility-audit-retained=0.0, duplicate-audit-issue=0.0.

## Simulator runs and gaming

H2 duplicate -> guard 1 on the second create; act-then-undo is closed by the final-state retained check (jira_update_issue only transitions status, it cannot change summary/project/type).

Mechanism notes: Luna episode predates the persisted-issue Jira handler: its create_issue wrote only an action record, so the installed retained check scores the correct Luna run 0 (created_matching_fresh_object_absent). This is the installed, tested behaviour (tests/test_jira_accessibility_manifest.py::test_recorded_action_log_does_not_invent_retained_issue), not a draft error; it blocks qualification until a reference episode is re-recorded on the current handler.

Both in-scope obligations are expressed and verified on the simulator, but the recorded Luna episode (old action-only Jira handler) scores O1 0 by design; needs a re-recorded reference.
