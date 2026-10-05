# operations.trello_basecamp_slack_compliance_followup: batch-04 public manifest review

Status: **partial component authoring; not qualified**. Original Luna score: official_partial recorded_partial_score; score 0.75; original partial outcome and misses are retained.

Draft SHA-256: `f232c5e4fa3dd5ca7710595d3539ed968a445fd4cf0c620a49c70c74328ac434`. Episode SHA-256: `42396a156a330c85dae838054518d7d6f16f97d92bc07d7673023a8140a98510`. Public input SHA-256: `747067678c97fa8cbe20d6ddb06c2813d5087aec7c6e0c56c79806ebfd169042`.

## Declared checks (5)
- `latest-compliance-followup-email-read-before-changes` (goal, `effects.required_when@1`).
- `latest-followup-updates-target-trello-card` (goal, `effects.required_when@1`).
- `compliance-label-added-to-target-card` (goal, `effects.required_when@1`).
- `basecamp-todo-target-text-date-and-list` (goal, `effects.required_when@1`).
- `ops-updates-message-preserves-task-and-due-values` (goal, `effects.required_when@1`).

## Native replay

- Score/rescore/reload-rescore findings match: `True` / `True`; scalar unchanged: `True`; source episode bytes unchanged: `True`; errors: `0`.
- Stage seconds: score {s["first"]}, rescore {s["rescore"]}, reload-rescore {s["reload_rescore"]}.
- Source revision: `3d7ebc418d7e4c34390129847b517d55be5cdfda`; source file hashes are recorded in `review.json`.

## Genuine-handler controls

- Exact public input and prompt/initial hashes are recorded in `review.json`; control artifact SHA-256: `1a4a7f6057871ab6e38cd8104ae678d02d3493832188db0ca908238909fbf97c`. Each variant compares manifest scalar to an independently scored ordinary `AutomationBenchTask` on the same public fixture. All variant scalars match; all reported errors are empty.
- `correct_target_genuine_handler_replay`: latest-compliance-followup-email-read-before-changes=valid:1.0; latest-followup-updates-target-trello-card=valid:1.0; compliance-label-added-to-target-card=valid:1.0; basecamp-todo-target-text-date-and-list=valid:1.0; ops-updates-message-preserves-task-and-due-values=valid:1.0.
- `task_specific_harm_or_wrong_target_control`: latest-compliance-followup-email-read-before-changes=valid:0.0; latest-followup-updates-target-trello-card=valid:0.0; compliance-label-added-to-target-card=valid:0.0; basecamp-todo-target-text-date-and-list=valid:0.0; ops-updates-message-preserves-task-and-due-values=valid:0.0.
- `missing_persisted_action_acknowledgement`: latest-compliance-followup-email-read-before-changes=valid:1.0; latest-followup-updates-target-trello-card=valid:1.0; compliance-label-added-to-target-card=valid:1.0; basecamp-todo-target-text-date-and-list=valid:1.0; ops-updates-message-preserves-task-and-due-values=abstained:None.

## Expected control outcomes

Expected check IDs and statuses/values are explicit in `review.json`; the harness asserted them before writing the results, including the missing-ACK abstentions.

## Findings and limits

The exact public trace replay covers all five checks. A wrong Trello target produces 0 for the target-bound effects; removing the Slack receipt ACK abstains only the receipt-dependent message check. No task-acceptance or action-credit claim follows.
- Controls verify the stated components only; they do not establish retained-trajectory acceptance, action credit, or qualification. `review.json` contains per-check findings, latest run IDs, expected controls, and all source/draft/replay hashes.
