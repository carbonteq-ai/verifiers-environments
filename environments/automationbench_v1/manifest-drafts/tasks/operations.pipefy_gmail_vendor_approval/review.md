# operations.pipefy_gmail_vendor_approval manifest review

The draft is bound to public pack index 4 and the exact public prompt and initial state. Original recorded outcome remains **official_zero**, partial reward 0.0; this is manifest component evidence, not qualification.

- Draft SHA-256: `1f05959afcc6e7e3673001e98fe7c7ac71cf66be73aa692e676ffe2b3fe34725`
- Public prompt SHA-256: `b9b7f99110243620833c9f6d81152f8cd65988788d2a5fc29e2e4e997103112f`
- Public initial-state SHA-256: `631fc17ded8021e41a57d82b142576f2a1cb38d69ae925f0d6a4bb3d47a5611e`
- Original episode SHA-256: `14c2faa242b8ed3cfeea1b5ae8713d32f22605240354dc1da3521aee63f35526`
- Native score / rescore / reload-rescore parity: `True`; ordinary scalar unchanged: `True`; source bytes unchanged: `True`; errors: 0.

Four unread procurement review emails are read and each confirmation email is witnessed. Eight Pipefy move/status outcomes (four decisions, two outcomes each) remain missing; action evidence is distinct from the correct return-email outcomes.

## Check outcomes

- `apex-card-moved-to-decision-phase`: valid 0.0 (obligation_required_effect_missing) ×1
- `apex-procurement-confirmation-sent`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `apex-status-field-set-to-decision`: valid 0.0 (obligation_required_effect_missing) ×1
- `blueyard-card-moved-to-decision-phase`: valid 0.0 (obligation_required_effect_missing) ×1
- `blueyard-procurement-confirmation-sent`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `blueyard-status-field-set-to-decision`: valid 0.0 (obligation_required_effect_missing) ×1
- `northwind-llc-card-moved-to-decision-phase`: valid 0.0 (obligation_required_effect_missing) ×1
- `northwind-llc-procurement-confirmation-sent`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `northwind-llc-status-field-set-to-decision`: valid 0.0 (obligation_required_effect_missing) ×1
- `summit-card-moved-to-decision-phase`: valid 0.0 (obligation_required_effect_missing) ×1
- `summit-procurement-confirmation-sent`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `summit-status-field-set-to-decision`: valid 0.0 (obligation_required_effect_missing) ×1
- `unread-procurement-vendor-reviews-read`: inapplicable None (obligation_not_required) ×31, valid 1.0 (obligation_witnessed_required_effect) ×4

## Controls and qualification

The native three-phase replay verifies deterministic scoring and serialization. It does not by itself validate correct, alternative, harmful, or missing-ACK behavior. Task-bound correct, alternative, harmful, and missing-ACK component controls ran through genuine simulator handlers and were compared with ordinary AutomationBench rewards. Dispatch/return receipts, ACK records, findings and per-scenario source fingerprints are in `vendor_approval_controls.json` under `/tmp/automationbench-luna-operations-20261005-batch07/`. Whole-task qualification remains not granted. Whole-task qualification remains not granted.

## Shared-source refresh (2026-10-05)

After the shared source-position selection and Buffer channel-read changes settled, the native three-phase replay and all persisted genuine-handler controls for this task were executed again. Current results are recorded in `/tmp/automationbench-luna-operations-20261005-batch07/operations07_shared_source_refresh.json`; prior run artifacts and reviews remain under `/tmp/automationbench-luna-operations-20261005-batch07/history_pre_shared_source_refresh_20261005`. The current replay retained findings/scalar/source-byte parity with zero errors. Control ordinary and manifest reward maps match in every rerun variant. Current source snapshot: 46 hashed files of 54 requested paths; missing source paths are listed in the linked JSON artifact. These component results do not grant whole-task qualification.
