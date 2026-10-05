# finance.vendor_credit_application

Recorded official scalar: `0.0`. This is a retained development reference and these component checks do not qualify the whole task.

## Validation

- Current draft SHA-256: `00f1b4e19e5daafd176035d12ab572a194c47fbae43e68c8adbd5cf781769f8a`.
- Source episode SHA-256: `b70428b591f091091b1dcd566593c0f23e5c28b7af0b0168b83a59b972a800d7` (source path `/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01/remaining700/timed/c93a5df638475fec4c86ecaa86d80f627572a8f08ace19f2671d825136b0782e/episode.json`).
- Native replay: pass; same-trace rescore and serialized/reloaded rescore reproduce findings; recorded scalar and source episode bytes are unchanged.
- Source: native HEAD `3d7ebc418d7e4c34390129847b517d55be5cdfda` plus dirty source module hashes recorded in `luna_replay.source_fingerprint.changed_source_module_sha256`.
- Genuine handler controls: `/tmp/automationbench-luna-finance-20261005-batch08/controls-first-two.json` and `/tmp/automationbench-luna-finance-20261005-batch08/controls-rest.json`; both file hashes and per-case draft hashes are in `luna_controls`. Ordinary benchmark rewards and manifest rewards compare equal for each control.

## Public obligations and limits

- **credits-applied-to-matching-oldest-bills — gap** (goal): Apply credits to oldest open same-vendor bill first; do not exceed bill amount; update remaining credit balance. (public source `task_evidence.initial_state.gmail.messages.0.body_plain`); checks `—`.
- **preserve-procurement-rating — expressed** (guard): Vendor ratings are managed exclusively by Procurement; AP staff must NOT modify vendor ratings. (public source `task_evidence.initial_state.gmail.messages.0.body_plain`); checks `no-vendor-info-rating-edits`.
- **vendor-confirmations — component_bound** (report): Email each vendor confirming credit application and include total credits applied. (public source `task_evidence.prompt.1.content`); checks `credit-confirm-acme; credit-confirm-techserve`.

## Current gaps

- Source credits VC-101/103 could be applied only within their vendors and are not held; VC-104 is older than the 120-day override window and requires verification; VC-105 is disputed/on hold; VC-102 is within 120 days. Vendor Info ratings are Procurement-owned.
- The current positive email checks cover Acme VC-101 $1,500 and TechServe VC-103 $3,200 only. They do not prove oldest-bill allocation or bill/credit residual math. Rating guard must be validated with real row-write effects before describing operational coverage.
- No accounting vendor-credit application tool is exposed; email confirmation would be misleading unless real application is established. Checks are bounded notification components, not proof that credits were applied.

See `review.json` for every finding, current hashes, source fingerprints and control outcomes.

## Evidence provenance audit (2026-10-05)

- Current draft SHA-256 at rerun: `00f1b4e19e5daafd176035d12ab572a194c47fbae43e68c8adbd5cf781769f8a`; public source episode SHA-256: `b70428b591f091091b1dcd566593c0f23e5c28b7af0b0168b83a59b972a800d7`.
- Native replay with error inventories and same-trace plus serialized/reloaded semantic parity: `/tmp/automationbench-luna-finance-20261005-batch08/audit-nine/vendor_credit_application-native-replay.json` (SHA-256 `6c37a27285b0e67936e91cb131714efa740183a5c9c9494d98d0091bde01914b`). Scalars and source episode bytes were unchanged.
- Genuine handler controls with native arguments/results, ACK receipts, raw handler material, full native episodes, source module fingerprints, and ordinary/manifest reward comparisons: `/tmp/automationbench-luna-finance-20261005-batch08/audit-nine/audit-nine-evidence.json` (SHA-256 `316da2486f057b8318571c1d21b3ccf2dd51ac8d364d48866121a557c2c78ad1`). This task has 3 actual controls; every control has zero handler/native/assessment/credit errors and stable before/after module hashes.
- Historical compact controls are preserved in `validation_history`; they are superseded for raw provenance and source identity.

