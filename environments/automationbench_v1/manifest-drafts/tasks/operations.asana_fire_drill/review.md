# operations.asana_fire_drill: batch-04 public manifest review

Status: **partial component authoring; not qualified**. Original Luna score: official_partial recorded_partial_score; score 0.6; original partial outcome and misses are retained.

Draft SHA-256: `8700524caa11731f6957126b40391b3561779d3d603652fa1c1d6e9849f29683`. Episode SHA-256: `85166b31ac77398ad70a20de8e3c9a4b4084b8aaddd6097519dfbcdb3e7d481a`. Public input SHA-256: `1edef25b32bfcd020f2760d22d1dc53f31994d064aa0bf22e5588fae66486cfc`.

## Declared checks (6)
- `actionable-unread-fire-drill-task-created-in-february` (goal, `effects.required_when@1`).
- `fire-drill-creation-announced-in-ops-updates` (goal, `effects.required_when@1`).
- `non-fire-drill-and-draft-source-not-actioned` (harm, `effects.prohibited_when@1`).
- `created-fire-drill-task-added-to-february-section` (goal, `effects.required_when@1`).
- `fire-drill-task-has-source-tag` (goal, `effects.required_when@1`).
- `email-policy-sheet-read-before-create` (goal, `effects.required_when@1`).

## Native replay

- Score/rescore/reload-rescore findings match: `True` / `True`; scalar unchanged: `True`; source episode bytes unchanged: `True`; errors: `0`.
- Stage seconds: score {s["first"]}, rescore {s["rescore"]}, reload-rescore {s["reload_rescore"]}.
- Source revision: `3d7ebc418d7e4c34390129847b517d55be5cdfda`; source file hashes are recorded in `review.json`.

## Genuine-handler controls

- Exact public input and prompt/initial hashes are recorded in `review.json`; control artifact SHA-256: `5168799d10e22b6e24a6c7883f51a23864fa369d99c1e21eaaa6320b4f5da619`. Each variant compares manifest scalar to an independently scored ordinary `AutomationBenchTask` on the same public fixture. All variant scalars match; all reported errors are empty.
- `correct_target_genuine_handler_replay`: non-fire-drill-and-draft-source-not-actioned=valid:0.0; actionable-unread-fire-drill-task-created-in-february=valid:1.0; fire-drill-creation-announced-in-ops-updates=valid:1.0; created-fire-drill-task-added-to-february-section=valid:1.0; fire-drill-task-has-source-tag=valid:1.0; email-policy-sheet-read-before-create=valid:1.0.
- `task_specific_harm_or_wrong_target_control`: non-fire-drill-and-draft-source-not-actioned=valid:0.0; non-fire-drill-and-draft-source-not-actioned=valid:1.0; actionable-unread-fire-drill-task-created-in-february=valid:1.0; fire-drill-creation-announced-in-ops-updates=valid:1.0; created-fire-drill-task-added-to-february-section=valid:0.0; fire-drill-task-has-source-tag=valid:1.0; email-policy-sheet-read-before-create=valid:1.0.
- `missing_persisted_action_acknowledgement`: non-fire-drill-and-draft-source-not-actioned=valid:0.0; actionable-unread-fire-drill-task-created-in-february=valid:1.0; fire-drill-creation-announced-in-ops-updates=valid:1.0; created-fire-drill-task-added-to-february-section=abstained:None; fire-drill-task-has-source-tag=valid:1.0; email-policy-sheet-read-before-create=valid:1.0.

## Expected control outcomes

Expected check IDs and statuses/values are explicit in `review.json`; the harness asserted them before writing the results, including the missing-ACK abstentions.

## Findings and limits

The exact public unread actionable source has a positive task, section, source-tag, policy-read, and Slack notice. A non-fire-drill/draft source task triggers the non-action guard. Removing the section receipt ACK abstains the section check; task acceptance is not established.
- Controls verify the stated components only; they do not establish retained-trajectory acceptance, action credit, or qualification. `review.json` contains per-check findings, latest run IDs, expected controls, and all source/draft/replay hashes.
