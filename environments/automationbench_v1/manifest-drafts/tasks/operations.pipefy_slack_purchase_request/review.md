# operations.pipefy_slack_purchase_request manifest review

The draft is bound to public pack index 5 and the exact public prompt and initial state. Original recorded outcome remains **official_zero**, partial reward 0.0; this is manifest component evidence, not qualification.

- Draft SHA-256: `0b4035f63a626e16bfd67029c1faa503df0fc9b9fc0bcad257f24130996c7470`
- Public prompt SHA-256: `724d2fa83827926e7d196f88c8d876fedfa2f7278dde3615c735cbf82738cebf`
- Public initial-state SHA-256: `7378b66126ae1e96cb32c9fcd3fa5e5db2ffb90948300a6cff063dffb2c50c2e`
- Original episode SHA-256: `0848dcf269c4377b7321b26822f8c7a4d96806fb60672a0078b41c69207100ba`
- Native score / rescore / reload-rescore parity: `True`; ordinary scalar unchanged: `True`; source bytes unchanged: `True`; errors: 0.

Both Purchase Requests and policy Sheet reads are witnessed. The Pipefy phase/status mutation and #ops-updates notice for the public highest-cost eligible request are missing.

## Check outcomes

- `purchase-approval-summary-to-ops`: valid 0.0 (obligation_required_effect_missing) ×1
- `purchase-policy-read`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `purchase-requests-read`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `selected-purchase-moved-to-approved`: valid 0.0 (obligation_required_effect_missing) ×1
- `selected-purchase-status-approved`: valid 0.0 (obligation_required_effect_missing) ×1

## Controls and qualification

The native three-phase replay verifies deterministic scoring and serialization. It does not by itself validate correct, alternative, harmful, or missing-ACK behavior. Task-bound correct, alternative, harmful, and missing-ACK controls ran through genuine simulator handlers and compare manifest rewards with independently scored ordinary AutomationBench rewards. Raw dispatch/return receipts, ACK records, latest findings and pre/post source hashes are in `purchase_controls.json` under `/tmp/automationbench-luna-operations-20261005-batch07/`. Whole-task qualification remains not granted.

Controls: Task-bound correct, alternative, harmful, and missing-ACK component controls ran through genuine simulator handlers and were compared with ordinary AutomationBench rewards. Dispatch/return receipts, ACK records, findings and per-scenario source fingerprints are in `purchase_controls.json` under `/tmp/automationbench-luna-operations-20261005-batch07/`. Whole-task qualification remains not granted.

## Shared-source refresh (2026-10-05)

After the shared source-position selection and Buffer channel-read changes settled, the native three-phase replay and all persisted genuine-handler controls for this task were executed again. Current results are recorded in `/tmp/automationbench-luna-operations-20261005-batch07/operations07_shared_source_refresh.json`; prior run artifacts and reviews remain under `/tmp/automationbench-luna-operations-20261005-batch07/history_pre_shared_source_refresh_20261005`. The current replay retained findings/scalar/source-byte parity with zero errors. Control ordinary and manifest reward maps match in every rerun variant. Current source snapshot: 46 hashed files of 54 requested paths; missing source paths are listed in the linked JSON artifact. These component results do not grant whole-task qualification.
