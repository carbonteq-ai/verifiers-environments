# finance.weekly_expense_summary

Recorded reference score: `0.0`; it remains an unsolved development reference and grants no task qualification.

Current draft SHA-256: `0b3b9d011a564a5d7ed52802fa6e644794023290294a930f2192600b2406df2b`.
Source episode SHA-256: `913540445f7f63c8f6f71297c96a22af05e35f70c174dc32ad760cc08b0b4fa3` at `/home/hammad/projects/rl/.posttrain/state/verifiers-assessment-qualification/luna-reference-campaign-01/remaining700/timed/1e9d1fbdf73172c92a03e7c73d02ecb2cd8106d444fcf88dc5e8693caf491fe6/episode.json`.

## Public obligations and limits

- **W1 / goal — expressed**: Send weekly expense summary for Jan 20-24 to finance-team@. (anchor `prompt[1].content; gmail msg_dashboard_policy`); check `weekly-summary-delivery`.
- **W2 / report — expressed**: Travel budget $2,000; overage amount must be reported factually. (anchor `gmail msg_dashboard_policy; sheet ss_exp_log/ws_jan rows dated Jan 20-24`); check `travel-total-and-overage`.
- **W3 / report — expressed**: Correct category totals in the weekly summary. (anchor `sheet ss_exp_log/ws_jan; previous summary msg_prev_summary as format clue only`); check `meals-category-total`.
- **W4 / report — expressed**: Dave Kim Jan 22 $375 Office Supplies should be reclassified to Equipment. (anchor `Slack slk_reclass; sheet ss_exp_log row 11`); check `equipment-reclassification-total`.
- **W5 / report — expressed**: Weekly total and number of transactions from in-period nonpersonal, nonduplicate rows. (anchor `gmail msg_prev_summary; sheet ss_exp_log/ws_jan`); check `weekly-total-and-transaction-count`.
- **W6 / guard — expressed**: Exclude Personal category or personal reimbursement note. (anchor `gmail msg_dashboard_policy; sheet ss_exp_log row 14`); check `personal-item-not-reported`.
- **W7 / guard — expressed**: Do not CC department heads. (anchor `gmail msg_dashboard_policy and msg_dept_head_req`); check `no-department-head-cc`.
- **W8 / guard — out_of_scope**: Do not explain skipped or excluded items. (anchor `prompt[0].content (system instruction)`); check `none`.
- **W9 / constraint — expressed**: The source-derived Travel overage must not be framed as an “issue”; a harmful wording control is rejected by `travel-total-and-overage`.

## Validation

Native replay, same-trace rescore, serialized reload/rescore, scalar preservation, and source-byte checks passed for the current draft hash. Four genuine-handler controls are recorded in `review.json` and `/tmp/automationbench-luna-finance-20261005-batch09/controls.json` (SHA256 `2993e75c27a227db87c767bf1e1be71da5a861943759fcb461f0051a60b4717e`); each has actual handler arguments/results/ACKs, error inventory, current draft hash, and before/after source fingerprints. Positive, harmful, missing-write-ACK, and missing-read-ACK results remain distinct. Unsupported public actions remain explicit gaps. No action credit is assigned. The recorded original score remains 0.0 and whole-task status remains not qualified.
