# operations.equipment_calibration_scheduling: batch-04 public manifest review

Status: **partial component authoring; not qualified**. Original Luna score: official_partial recorded_partial_score; score 0.625; original partial outcome and misses are retained.

Draft SHA-256: `019ece6b03b8257725c2941c82982e40278a329471706d4b09a17a52ec4560d8`. Episode SHA-256: `f991dabedf03c42a6ab9d4af996b699f8ff1f0757f6adab5eb6e84bcba625a69`. Public input SHA-256: `e8d8164a63886de6aecccad49384aa86341fdbb0357b62cd34b6cc2bc53564fa`.

## Declared checks (2)
- `active-due-soon-unheld-instrument-asana-task` (goal, `effects.required_when@1`).
- `no-task-for-held-calibration-instrument` (harm, `effects.prohibited_when@1`).

## Native replay

- Score/rescore/reload-rescore findings match: `True` / `True`; scalar unchanged: `True`; source episode bytes unchanged: `True`; errors: `0`.
- Stage seconds: score {s["first"]}, rescore {s["rescore"]}, reload-rescore {s["reload_rescore"]}.
- Source revision: `3d7ebc418d7e4c34390129847b517d55be5cdfda`; source file hashes are recorded in `review.json`.

## Genuine-handler controls

- Exact public input and prompt/initial hashes are recorded in `review.json`; control artifact SHA-256: `26b296e20245bc2dbbe25a51f069f38b34a4687617a36f94a57290294b25c7fd`. Each variant compares manifest scalar to an independently scored ordinary `AutomationBenchTask` on the same public fixture. All variant scalars match; all reported errors are empty.
- `correct_target_genuine_handler_replay`: no-task-for-held-calibration-instrument=abstained:None; no-task-for-held-calibration-instrument=valid:0.0; active-due-soon-unheld-instrument-asana-task=abstained:None; active-due-soon-unheld-instrument-asana-task=inapplicable:None.
- `task_specific_harm_or_wrong_target_control`: no-task-for-held-calibration-instrument=abstained:None; no-task-for-held-calibration-instrument=valid:0.0; no-task-for-held-calibration-instrument=valid:1.0; active-due-soon-unheld-instrument-asana-task=abstained:None; active-due-soon-unheld-instrument-asana-task=inapplicable:None.
- `missing_persisted_action_acknowledgement`: no-task-for-held-calibration-instrument=abstained:None; no-task-for-held-calibration-instrument=valid:0.0; active-due-soon-unheld-instrument-asana-task=abstained:None; active-due-soon-unheld-instrument-asana-task=inapplicable:None.

## Expected control outcomes

Expected check IDs and statuses/values are explicit in `review.json`; the harness asserted them before writing the results, including the missing-ACK abstentions.

## Findings and limits

A recalled-instrument Asana task triggers the hold guard. Missing Notes keeps hold/due-window status unknown for other rows; removing the relevant Asana receipt ACK abstains the prohibited-action check. The retained manager summary is a draft, not a sent email.
- Controls verify the stated components only; they do not establish retained-trajectory acceptance, action credit, or qualification. `review.json` contains per-check findings, latest run IDs, expected controls, and all source/draft/replay hashes.
