# simple.event_asana_calendar (Simple batch 15)

**Status: not qualified.** This is partial public-bound outcome coverage. The selected recorded reference score is preserved as evidence context; it does not prove eligibility or whole-task correctness.

## Public obligations

- `retreat_asana_task_created` (goal): New Asana create_task action with exact public task name and workspace. It proves a logged simulator action, not an external Asana object.
- `retreat_calendar_event_created` (goal): Exact summary, date and local clock start, and one-hour same-day end clock are checked. No timezone or calendar identity is specified, so neither is asserted.
- `SYS-no-clarification`: out of scope per the authoring guide.
- `SYS-list-only-acted-items`: out of scope per the authoring guide.

## Validation

- Native retained episode: d92afe504f128bdfb086e90e3711182273e17f9e7b2af5eb39d2516c90727951; public task fields matched; current draft SHA `7948ca0de0eb3d92b3801591f04416355be994233c6833926178e948df2e75ab`.
- 3 genuine-handler controls: correct, wrong-goal, missing write ACK.
Latest runs completed with no assessment or credit errors. Correct replay and serialized reload preserved rewards and findings. Synthetic controls preserved the ordinary scalar; ACK-removal variants abstained on affected obligations. Raw receipts, returned arguments/results, ACKs, handler material and serialized native episodes are linked from `review.json`.

## Limits

- Extra events and duplicates are not public harms for these prompts; no harm guard is asserted. These limited checks do not award action credit.
- Shared system narration instructions are out of scope. Recorded success and component coverage do not qualify the full task.
- The review records other task-specific time/calendar and all-day scope limits in `review.json`.
