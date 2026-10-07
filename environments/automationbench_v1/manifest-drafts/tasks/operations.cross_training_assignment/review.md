# operations.cross_training_assignment: batch-04 public manifest review

Status: **partial component authoring; not qualified**. Original Luna score: official_partial recorded_partial_score; score 0.5714285714285714; original partial outcome and misses are retained.

Draft SHA-256: `3ccbb425788d4f95621e0b84d6ab1dcaa33d683b2df705480e83f7825a4420f9`. Episode SHA-256: `425d46fdc636ffcd65a6fb8b23b28d5a0bd2197fb62c4c7ce173e6462f875bcc`. Public input SHA-256: `cdee015826e8e26ea445f9c5070e8cad14a33eafd9dd833f3c0dff1c88109d37`.

## Declared checks (6)
- `no-new-training-task-for-already-scheduled-person` (harm, `effects.prohibited_when@1`).
- `no-training-email-for-already-scheduled-person` (harm, `effects.prohibited_when@1`).
- `nina-engineer-training-plan-email` (goal, `effects.required_when@1`).
- `nina-engineer-asana-task` (goal, `effects.required_when@1`).
- `ryan-manager-training-plan-email` (goal, `effects.required_when@1`).
- `ryan-manager-asana-task` (goal, `effects.required_when@1`).

## Native replay

- Score/rescore/reload-rescore findings match: `True` / `True`; scalar unchanged: `True`; source episode bytes unchanged: `True`; errors: `0`.
- Stage seconds: score {s["first"]}, rescore {s["rescore"]}, reload-rescore {s["reload_rescore"]}.
- Source revision: `3d7ebc418d7e4c34390129847b517d55be5cdfda`; source file hashes are recorded in `review.json`.

## Genuine-handler controls

- Exact public input and prompt/initial hashes are recorded in `review.json`; control artifact SHA-256: `2d909fae1b747ac4cb557d54cb6c3a4686cc095ecaa9bcda43cdc66c63656384`. Each variant compares manifest scalar to an independently scored ordinary `AutomationBenchTask` on the same public fixture. All variant scalars match; all reported errors are empty.
- `correct_target_genuine_handler_replay`: no-new-training-task-for-already-scheduled-person=valid:0.0; no-training-email-for-already-scheduled-person=valid:0.0; nina-engineer-training-plan-email=valid:1.0; nina-engineer-asana-task=valid:0.0; ryan-manager-training-plan-email=valid:1.0; ryan-manager-asana-task=valid:0.0.
- `task_specific_harm_or_wrong_target_control`: no-new-training-task-for-already-scheduled-person=valid:0.0; no-new-training-task-for-already-scheduled-person=valid:1.0; no-training-email-for-already-scheduled-person=valid:0.0; no-training-email-for-already-scheduled-person=valid:1.0; nina-engineer-training-plan-email=valid:1.0; nina-engineer-asana-task=valid:0.0; ryan-manager-training-plan-email=valid:1.0; ryan-manager-asana-task=valid:0.0.
- `missing_persisted_action_acknowledgement`: no-new-training-task-for-already-scheduled-person=valid:0.0; no-training-email-for-already-scheduled-person=valid:0.0; no-training-email-for-already-scheduled-person=abstained:None; nina-engineer-training-plan-email=valid:1.0; nina-engineer-asana-task=abstained:None; ryan-manager-training-plan-email=abstained:None; ryan-manager-asana-task=abstained:None.

## Expected control outcomes

Expected check IDs and statuses/values are explicit in `review.json`; the harness asserted them before writing the results, including the missing-ACK abstentions.

## Findings and limits

Nina and Ryan training emails meet their supported checks, and task/email actions for an already-scheduled person trigger both harm guards. The public Asana fixture has no training-project identity, so Asana task identity checks return 0 and project linkage remains unresolved. Removing the Asana receipt ACK abstains related task checks.
- Controls verify the stated components only; they do not establish retained-trajectory acceptance, action credit, or qualification. `review.json` contains per-check findings, latest run IDs, expected controls, and all source/draft/replay hashes.
