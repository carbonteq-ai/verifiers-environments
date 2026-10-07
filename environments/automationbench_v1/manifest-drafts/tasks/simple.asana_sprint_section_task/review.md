# simple.asana_sprint_section_task (round 6)

Status: **qualified_candidate** — 6/6 in-scope obligations expressed, 0 gaps, 2 out of scope.

## Obligations

- O1-task-in-workspace (goal, expressed, `task-created-in-workspace`): create_task action with exact name and workspace ws_prod.
- O2-task-in-project (goal, expressed, `task-in-engineering-project`): Same create has project proj_eng; an omitted project is a decided 0.
- O3-due-date (goal, expressed, `task-due-date`): dueDate 2026-03-14 on the create and not later re-dated, or set by asana_update_task on that task.
- O4-added-to-sprint-8 (goal, expressed, `created-task-added-to-sprint-8`): add_task_to_section with section sec_sprint8 (bound from the public find_section record) and task_id equal to the id of an earlier create named 'Refactor payment module'. The find step is the means; the section id is the lookup's result.
- O5-single-task (guard, expressed, `duplicate-refactor-task`): Harm: a second create with the same name (no Asana delete tool).
- O6-due-not-changed-away (guard, expressed, `due-date-changed-away`): Harm: asana_update_task on the created task setting due_on to another date.
- SYS-no-clarification (guard, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.
- SYS-list-only-acted-items (report, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.

## Luna replay

No errors; rescore and reload equal; scalar rewards and episode bytes unchanged. Values: created-task-added-to-sprint-8=1.0, duplicate-refactor-task=0.0, task-created-in-workspace=1.0, task-due-date=1.0, task-in-engineering-project=1.0.

## Simulator runs and gaming

H5 re-date after create -> O3 0 and guard 1; H3 add some other task id -> O4 0; H4 duplicate -> guard 1; C2 fix due by update -> 1; C3 notes-only update -> no effect.

Known gaming: Rename the task with asana_update_task after creating it (Name is the join key of every check; a rename path was not modelled (rare, no benefit beyond the original create).)

Mechanism notes: No key-presence predicate: Asana action params omit unset keys, so `eq` on an absent 'project' or 'due_on' is unknown (H6 abstained). Closed with {op: proven, arg: eq(x, x)} as a has-key test over the fully observed action record; AUTHORING reserves `proven` for unreadable data rows, so a small `present` predicate would be cleaner.
