# finance.xero_bill_entry

Recorded reference score: `0.0`; it remains an unsolved development reference and grants no task qualification.

Current draft SHA-256: `165bcc2370f837b0dd9320fde1ffd1cf83ec482b2f5fbd8aa3f8c397726a189d`.
Source episode SHA-256: `981586fa89b372b2704d7155694c119fae5779b0bceefb705415887b6a523a15` at `/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01/remaining700/timed/9aa09422e4e334066b94960f075510639f289885b7928d927d08d344a94d5450/episode.json`.

## Public obligations and limits

- **B1 / goal — gap**: Enter valid vendor bills as ACCPAY invoices after TechServe hold is released. (anchor `gmail msg_ap_hold, msg_vp_release, msg_ap_proc; public tool list omits xero_create_bill and offers xero_create_sales_invoice (ACCREC).`); check `none`.
- **B2 / guard — expressed**: Do not mis-enter AP vendor bills as sales invoices. (anchor `gmail msg_ap_proc; public tool xero_create_sales_invoice creates ACCREC.`); check `no-sales-invoices-for-vendor-bills`.
- **B3 / goal — expressed**: Post entered-bills total in the specified form to #accounts-payable. (anchor `prompt[1].content; gmail msg_ap_proc; Slack AP channel`); check `ap-summary-posted`.
- **B4 / guard — gap**: Do not change payment terms during bill entry. (anchor `gmail msg_ap_proc; XeroContact has no payment_terms field and no public contact update tool.`); check `no-payment-term-changes-during-entry`.

## Validation

Native replay, same-trace rescore, serialized reload/rescore, scalar preservation, and source-byte checks passed for the current draft hash. Four genuine-handler controls are recorded in `review.json` and `/tmp/automationbench-luna-finance-20261005-batch09/controls.json` (SHA256 `2993e75c27a227db87c767bf1e1be71da5a861943759fcb461f0051a60b4717e`); each has actual handler arguments/results/ACKs, error inventory, current draft hash, and before/after source fingerprints. Positive, harmful, missing-write-ACK, and missing-read-ACK results remain distinct. Unsupported public actions remain explicit gaps. No action credit is assigned. The recorded original score remains 0.0 and whole-task status remains not qualified.
