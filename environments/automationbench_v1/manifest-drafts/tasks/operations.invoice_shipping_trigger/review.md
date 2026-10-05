# operations.invoice_shipping_trigger — batch05 review

- Status: `not_qualified`; original Luna outcome remains `official_partial` with selection score `0.5714285714285714`.
- Draft SHA-256: `59a2839d2589aef99385824bc628ebab6942bbe0efe0deadfee33ec83d151e30`; source HEAD: `3d7ebc418d7e4c34390129847b517d55be5cdfda`; source file fingerprints are in `review.json`.
- Native replay: scalar unchanged `True`, episode bytes unchanged `True`, rescore parity `True`, reload parity `True`.
- Checks: 5 expressed, 0 unavailable/unknown.
- Controls: genuine-handler correct/alternative/harm/missing-ACK component controls are recorded in `review.json`; do not infer task acceptance.

## Findings

- Public shipped aggregate excludes recalled HZ-8800-EXP and selects WG-4410-EXP + FL-7700-EXP: 2 lines / $13,600. Native Luna action misses the compliant Monday summary and per-line customer messages. Genuine handler read succeeds, while positive summary/email predicates currently return zero; recalled-line prohibited match is detected in the harmful control. Status and due-date requirements remain uncovered.

See `review.json` for per-check outcomes, public pack/hash bindings, source hashes, and native run timing.


## Genuine-handler controls

Read control succeeds, but genuine Monday/email positive components score zero; the harmful recalled-line email is detected. Missing persisted ACK abstains on required actions.


## Declaration repair evidence

The source-correct declaration repair changed the draft from `59a2839d2589aef99385824bc628ebab6942bbe0efe0deadfee33ec83d151e30` to `1a077d8dfc6e87182e1f6fc6c993949a6ad376cac4d242e806cd6e723ae48637`. The earlier review and draft remain in `/tmp/automationbench-luna-operations-20261005-batch06/invoice_history`; the earlier native result is retained inside `before_review.json`. No simulator source changed. The corrected genuine-handler controls passed positive and alternative Sheet-read, Monday-item, and email checks; a recalled HZ-8800-EXP write/email variant activated both harm guards; removing the Monday-write ACK abstained that check. Ordinary benchmark reward maps matched in all four controls.

The recorded Luna episode still misses the Monday write and email, so the original partial score and failed native evidence remain. Monday Pending status and due date are still unsupported; whole-task status remains `not_qualified`.
