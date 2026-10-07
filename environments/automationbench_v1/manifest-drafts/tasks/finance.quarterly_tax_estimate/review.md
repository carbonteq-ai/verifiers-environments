# finance.quarterly_tax_estimate

Recorded official scalar: `0.0`. This is a retained development reference and these component checks do not qualify the whole task.

## Validation

- Current draft SHA-256: `8409c69858d65fe12c3d94d0b1cdfe9cd1b72c5feeb6dcecd10153b78a80d5c1`.
- Source episode SHA-256: `e6475c3ade3c8710f789f886ae8461866a4c2b6912c05e90872c994b9a6c8b03` (source path `/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01/remaining700/timed/22de07faa772c6b579988bdba4fbe5544d3f57116c6bd14ead32320c335eea8e/episode.json`).
- Native replay: pass; same-trace rescore and serialized/reloaded rescore reproduce findings; recorded scalar and source episode bytes are unchanged.
- Source: native HEAD `3d7ebc418d7e4c34390129847b517d55be5cdfda` plus dirty source module hashes recorded in `luna_replay.source_fingerprint.changed_source_module_sha256`.
- Genuine handler controls: `/tmp/automationbench-luna-finance-20261005-batch08/controls-first-two.json` and `/tmp/automationbench-luna-finance-20261005-batch08/controls-rest.json`; both file hashes and per-case draft hashes are in `luna_controls`. Ordinary benchmark rewards and manifest rewards compare equal for each control.

## Public obligations and limits

- **q1-estimate-report — expressed** (report): Calculate the Q1 2026 estimated tax payment; email the estimate to tax and controller. (public source `task_evidence.prompt.1.content`); checks `q1-estimate-tax-email; q1-estimate-controller-email`.
- **q1-source-rate-and-credit-policy — component_bound** (constraint): Blended 2 months at 5% and 1 month at 4.5%; procedure says subtract credits, divide annual estimate by 4, subtract prior quarter payments, round nearest dollar. (public source `task_evidence.initial_state.slack.messages.0.text`); checks `q1-estimate-tax-email; q1-estimate-controller-email`.
- **prior-year-payment-not-deducted — gap** (constraint): Prior payment notes explicitly say 2025 tax year; do not deduct from 2026 estimates. (public source `task_evidence.initial_state.google_sheets.rows`); checks `—`.

## Current gaps

- Public-source arithmetic used: taxable income is $425,000 from Jan–Mar; federal effective rate 21%; blended state rate (2×5%+1×4.5%)/3 = 4.8333%; annual credits total $16,000; 2025 Q4 payment $95,000 is explicitly excluded; (425000×(0.21+0.048333…)-16000)/4 rounds to $23,448. The task/procedure does not clarify annualization basis beyond using Q1 YTD values, so the exact result is a bounded interpretation.
- The email checks require recipient and expected estimate with both public policy sources read, but do not establish the calculation from arbitrary changed rows or every qualifying prior-payment population.

See `review.json` for every finding, current hashes, source fingerprints and control outcomes.

## Evidence provenance audit (2026-10-05)

- Current draft SHA-256 at rerun: `8409c69858d65fe12c3d94d0b1cdfe9cd1b72c5feeb6dcecd10153b78a80d5c1`; public source episode SHA-256: `e6475c3ade3c8710f789f886ae8461866a4c2b6912c05e90872c994b9a6c8b03`.
- Native replay with error inventories and same-trace plus serialized/reloaded semantic parity: `/tmp/automationbench-luna-finance-20261005-batch08/audit-nine/quarterly_tax_estimate-native-replay.json` (SHA-256 `89fa018aa49bc0e93bf1fbe710419d7bff5a4e3f1083c7c6e7cb5f013cc74152`). Scalars and source episode bytes were unchanged.
- Genuine handler controls with native arguments/results, ACK receipts, raw handler material, full native episodes, source module fingerprints, and ordinary/manifest reward comparisons: `/tmp/automationbench-luna-finance-20261005-batch08/audit-nine/audit-nine-evidence.json` (SHA-256 `316da2486f057b8318571c1d21b3ccf2dd51ac8d364d48866121a557c2c78ad1`). This task has 3 actual controls; every control has zero handler/native/assessment/credit errors and stable before/after module hashes.
- Historical compact controls are preserved in `validation_history`; they are superseded for raw provenance and source identity.

