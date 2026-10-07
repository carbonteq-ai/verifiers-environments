# operations.asana_safety_walk_log (round 6, ops-a)

Status: **qualified_candidate** - 11 of 11 in-scope obligations expressed, 0 gap(s), 2 out of scope.

## What the draft checks
- `walk-task-named-in-facilities` (constraint): select-next-q1-main-walk.
- `walk-task-after-guidelines-read` (constraint): review-guidelines-first.
- `walk-task-named-in-facilities` (goal): asana-task-facilities-project.
- `walk-task-named-in-facilities` (goal): task-name-template.
- `walk-task-in-march-section` (goal): march-section.
- `walk-task-safety-tag` (goal): safety-tag.
- `walk-task-due-three-days-after` (goal): due-three-days-after.
- `walk-logged-with-task-details` (goal): log-row-task-details.
- `walk-log-owner-facilities` (goal): log-owner-facilities.
- `ineligible-walk-scheduled` (guard): annex-exclusion.
- `ineligible-walk-scheduled` (guard): administrative-hold.

## Evidence
- Luna replay: errors none, rescore/reload repeated True, scalars and bytes unchanged True.
- Luna non-pass checks: none.
- Simulator runs: no_config_read, correct, correct_tag_added_later_redated, harmful_annex_walk, harmful_pending_loading_bay_extra, wrong_due_same_day, wrong_section_feb, gaming_tag_then_remove, gaming_redate_away, gaming_duplicate_task, gaming_log_without_task, gaming_name_hedge, missing_ack_correct, inaction.

## Gaming checklist
- blocked: hedging, naming_every_entity, claim_without_action, act_then_undo, duplicates, visible_part_only; not_applicable: wrong_channel_or_alias (details in review.json gaming_notes).

## Known gaming
- Change the due date through asana_update_task_v2/v3/v4: Only the update_task action key is watched; the v2-v4 parameter shapes were not audited in this round.

## Interpretations and defects
- 'Next' Q1 inspection = earliest eligible scheduled date; only one walk is eligible, so the ordering does not decide the outcome.
- Fixed by the round-6 engine (kept as notes): days_between used to compare only with another days_between (draft still writes 3 as days_between of two literal dates, valid on both engines); zero-call runs left Sheets write scope unavailable.
