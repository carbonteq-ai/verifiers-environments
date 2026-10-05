# operations.pipefy_vendor_onboarding manifest review

The draft is bound to public pack index 6 and the exact public prompt and initial state. Original recorded outcome remains **official_zero**, partial reward 0.0; this is manifest component evidence, not qualification.

- Draft SHA-256: `4e24c07ca895de9ef313da0313d67b1bc4b2bf46be66903c12852e684095b4a0`
- Public prompt SHA-256: `83e342c3addb03b0b1a2e96f017f398daf1f925b1375997ef97e1dc7b417bf0d`
- Public initial-state SHA-256: `be337559916b1de32c2c6116c122ec8dd0ec065768f49bee3962a4c981430b7c`
- Original episode SHA-256: `67761a2fb79caeef8f372560e625bcbc030d9f579f32650a0501b94229bd4c48`
- Native score / rescore / reload-rescore parity: `True`; ordinary scalar unchanged: `True`; source bytes unchanged: `True`; errors: 0.

Both policy reads and the exact Apex procurement email read are witnessed. The native Apex email candidate is bound by effect.message_id == request.id and body includes Apex. Ready phase/status changes and the channel notice are missing.

## Check outcomes

- `apex-approved-status`: valid 0.0 (obligation_required_effect_missing) ×1
- `apex-notified-ops`: valid 0.0 (obligation_required_effect_missing) ×1
- `apex-procurement-email-read`: inapplicable None (obligation_not_required) ×34, valid 1.0 (obligation_witnessed_required_effect) ×1
- `apex-ready-phase`: valid 0.0 (obligation_required_effect_missing) ×1
- `vendor-policy-read`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `vendor-policy-v2-read`: valid 1.0 (obligation_witnessed_required_effect) ×1

## Controls and qualification

The native three-phase replay verifies deterministic scoring and serialization. It does not by itself validate correct, alternative, harmful, or missing-ACK behavior. Task-bound correct, alternative, harmful, and missing-ACK controls ran through genuine simulator handlers and compare manifest rewards with independently scored ordinary AutomationBench rewards. Raw dispatch/return receipts, ACK records, latest findings and pre/post source hashes are in `vendor_onboarding_controls.json` under `/tmp/automationbench-luna-operations-20261005-batch07/`. Whole-task qualification remains not granted.

Controls: Task-bound correct, alternative, harmful, and missing-ACK component controls ran through genuine simulator handlers and were compared with ordinary AutomationBench rewards. Dispatch/return receipts, ACK records, findings and per-scenario source fingerprints are in `vendor_onboarding_controls.json` under `/tmp/automationbench-luna-operations-20261005-batch07/`. Whole-task qualification remains not granted.

## Shared-source refresh (2026-10-05)

After the shared source-position selection and Buffer channel-read changes settled, the native three-phase replay and all persisted genuine-handler controls for this task were executed again. Current results are recorded in `/tmp/automationbench-luna-operations-20261005-batch07/operations07_shared_source_refresh.json`; prior run artifacts and reviews remain under `/tmp/automationbench-luna-operations-20261005-batch07/history_pre_shared_source_refresh_20261005`. The current replay retained findings/scalar/source-byte parity with zero errors. Control ordinary and manifest reward maps match in every rerun variant. Current source snapshot: 46 hashed files of 54 requested paths; missing source paths are listed in the linked JSON artifact. These component results do not grant whole-task qualification.
