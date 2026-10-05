# finance.wave_tax_compliance

Recorded official scalar: `0.0`. This is a retained development reference and these component checks do not qualify the whole task.

## Validation

- Current draft SHA-256: `6a0a4a3dec5965d5fc9c0c9cd32025dd0f154b1b5959b2e2e684754dbfb0e6ee`.
- Source episode SHA-256: `64ca9ca961c3d78a1bf1515779997f40a9ab4b6bf60a560525e57884d0599d1f` (source path `/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01/remaining700/timed/56c5e9f1ef0230e63847b76450b0ba9510df4786895e47bc82f9185783033b3d/episode.json`).
- Native replay: pass; same-trace rescore and serialized/reloaded rescore reproduce findings; recorded scalar and source episode bytes are unchanged.
- Source: native HEAD `3d7ebc418d7e4c34390129847b517d55be5cdfda` plus dirty source module hashes recorded in `luna_replay.source_fingerprint.changed_source_module_sha256`.
- Genuine handler controls: `/tmp/automationbench-luna-finance-20261005-batch08/controls-first-two.json` and `/tmp/automationbench-luna-finance-20261005-batch08/controls-rest.json`; both file hashes and per-case draft hashes are in `luna_controls`. Ordinary benchmark rewards and manifest rewards compare equal for each control.

## Public obligations and limits

- **review-last-quarter-invoices — component_bound** (goal): Review all invoices from last quarter and verify correct rate based on customer state. (public source `task_evidence.prompt.1.content`); checks `wave-flag-or-discrepancy; wave-report-ca-december-rate`.
- **flag-discrepancies-email — expressed** (report): Flag any discrepancies and email the compliance report to tax@company.example.com. (public source `task_evidence.prompt.1.content`); checks `wave-flag-or-discrepancy`.
- **dynamic-rate-checking — gap** (constraint): Verify correct tax rate per customer state; California rate increased to 7.5% effective Dec 1, 2025. (public source `task_evidence.initial_state.google_sheets.rows`); checks `—`.

## Current gaps

- Source examples: CA invoice WI-1001 dated Oct 15 has $362.50 at 7.25%; NY WI-1002 $800 at 8%; TX WI-1003 $625 at 6.25%; OR WI-1004 $252 but rate source is 0.00%, discrepancy; CA WI-1005 dated Dec 5 has $480 consistent with 7.5% on $6,400 taxable subtotal.
- Task asks flag/report only; available Wave handler is list/read, not an invoice tax updater. The checks require the known discrepancy/rate report components but do not establish full dynamic comparison for all invoices or receipt of each report detail.

See `review.json` for every finding, current hashes, source fingerprints and control outcomes.

## Evidence provenance audit (2026-10-05)

- Current draft SHA-256 at rerun: `6a0a4a3dec5965d5fc9c0c9cd32025dd0f154b1b5959b2e2e684754dbfb0e6ee`; public source episode SHA-256: `64ca9ca961c3d78a1bf1515779997f40a9ab4b6bf60a560525e57884d0599d1f`.
- Native replay with error inventories and same-trace plus serialized/reloaded semantic parity: `/tmp/automationbench-luna-finance-20261005-batch08/audit-nine/wave_tax_compliance-native-replay.json` (SHA-256 `5e4b3614f06f656381fb2e4fe7122d69f1d22888536ed2800809cf83741109b7`). Scalars and source episode bytes were unchanged.
- Genuine handler controls with native arguments/results, ACK receipts, raw handler material, full native episodes, source module fingerprints, and ordinary/manifest reward comparisons: `/tmp/automationbench-luna-finance-20261005-batch08/audit-nine/audit-nine-evidence.json` (SHA-256 `316da2486f057b8318571c1d21b3ccf2dd51ac8d364d48866121a557c2c78ad1`). This task has 2 actual controls; every control has zero handler/native/assessment/credit errors and stable before/after module hashes.
- Historical compact controls are preserved in `validation_history`; they are superseded for raw provenance and source identity.
- Missing write-ACK control: `/tmp/automationbench-luna-finance-20261005-batch08/audit-nine/missing-write-ack-five.json` (SHA-256 `694ce5608749a34a9495f6aca28f71d28e40f3869af933ddb03a52e11e20fe61`); the omitted ACK was for `gmail_send_email` with arguments `{"body": "Q4 sales tax compliance: WI-1004 Evergreen Software, OR, tax charged $252.00 but applicable OR rate is 0.00%; discrepancy flagged. WI-1005 CA invoice dated Dec 5 uses 7.5% and $480.00 tax.", "body_type": "plain", "subject": "Finance summary", "to": "tax@company.example.com"}`. The genuine handler returned successfully; see exact affected findings, remaining ACKs, and unchanged ordinary/manifest scalars in `review.json`.
- Observed missing-ACK outcome: wave-flag-or-discrepancy=abstained(None); wave-report-ca-december-rate=abstained(None); ordinary reward {'partial_credit': {'score': 0.6, 'weight': 1.0}}, manifest reward {'partial_credit': {'score': 0.6, 'weight': 1.0}}, remaining native ACKs 1/4 events.

