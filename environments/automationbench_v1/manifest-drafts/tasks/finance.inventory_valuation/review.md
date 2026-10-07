# finance.inventory_valuation

Recorded reference scalar score: `0.0`. Reference class: `recorded_partial_score`. Current component coverage is not whole-task qualification.

Current draft SHA-256: `ab745b2b06b653611544b97e796858e2486fb96b6bca6b74e9840063d0f173ff`.
Source episode SHA-256: `fef3afecc970649cdfabcf54a8d87e49d4c0312e3e72ea96a4791a4cb4a4ec6b`.
Native replay source: HEAD `3d7ebc418d7e4c34390129847b517d55be5cdfda`, dirty contract diff SHA-256 `ef070429e2ec467cc849ae1473bb8f4fef48a05fd11a6590b5eec0c8f725a2e5`.
Genuine-handler artifact SHA-256: `c24359c3191d1996124b22759bbaccfad487be66f47736296582f16565afa41c` (4 completed cases).

## Public obligations and expressed component checks

- **report-variance-and-impact-all-skus** — expressed; `inventory-eligible-variance-lines`. Variance=physical-system; impact=variance*unit cost; report SKU/item/system/physical/variance/impact. (msg_inv_val_pol)
- **minor-auto-adjust** — expressed; `minor-variance-auto-adjust`. Within ±2%: minor, auto-adjust. (msg_inv_val_pol)
- **major-investigation-flag** — expressed; `major-investigation-flag`. Over ±2%: major and requires investigation flag. (msg_inv_val_pol)
- **pending-po-excluded-from-adjustment** — expressed; `no-auto-adjust-pending-or-major`. Items with pending purchase orders should be excluded from adjustment. (msg_inv_val_pol)
- **system-no-clarification** — out_of_scope; `—`. Do not ask clarifying questions. (system prompt)
- **system-list-only-acted-items** — out_of_scope; `—`. List only items you acted on. (system prompt)

## Handler controls

- **correct**: expected `Publicly requested component checks should witness their required actions; declared guard scope should close without a violation.`; ordinary rewards `{'partial_credit': {'score': 0.6666666666666666, 'weight': 1.0}}`; no-auto-adjust-pending-or-major finding: {'valid': 4} values={'0.0': 4}, no-auto-adjust-pending-or-major compliance: {'valid': 1} values={'1.0': 1}, inventory-eligible-variance-lines finding: {'valid': 4} values={'1.0': 4}, minor-variance-auto-adjust finding: {'valid': 1, 'inapplicable': 3} values={'1.0': 1, 'None': 3}, major-investigation-flag finding: {'inapplicable': 2, 'valid': 2} values={'None': 2, '1.0': 2}; errors=0, nonterminal=0, failed=[].
- **wrong**: expected `A deliberately incorrect source-bound amount/field should fail its corresponding obligation while unrelated checks remain independently assessed.`; ordinary rewards `{'partial_credit': {'score': 0.6666666666666666, 'weight': 1.0}}`; no-auto-adjust-pending-or-major finding: {'valid': 4} values={'0.0': 4}, no-auto-adjust-pending-or-major compliance: {'valid': 1} values={'1.0': 1}, inventory-eligible-variance-lines finding: {'valid': 4} values={'1.0': 4}, minor-variance-auto-adjust finding: {'valid': 1, 'inapplicable': 3} values={'0.0': 1, 'None': 3}, major-investigation-flag finding: {'inapplicable': 2, 'valid': 2} values={'None': 2, '1.0': 2}; errors=0, nonterminal=0, failed=[].
- **correct + missing ACK**: expected `Missing ACK should abstain affected effect-dependent checks; this is uncertainty, not positive or negative proof.`; ordinary rewards `{'partial_credit': {'score': 0.6666666666666666, 'weight': 1.0}}`; no-auto-adjust-pending-or-major finding: {'valid': 2, 'abstained': 2} values={'0.0': 2, 'None': 2}, no-auto-adjust-pending-or-major compliance: {'abstained': 1} values={'None': 1}, inventory-eligible-variance-lines finding: {'abstained': 4} values={'None': 4}, minor-variance-auto-adjust finding: {'abstained': 1, 'inapplicable': 3} values={'None': 4}, major-investigation-flag finding: {'inapplicable': 2, 'abstained': 2} values={'None': 4}; errors=0, nonterminal=0, failed=[].
- **harm**: expected `The public prohibition should produce a valid prohibited-effect finding and compliance value 0.`; ordinary rewards `{'partial_credit': {'score': 0.0, 'weight': 1.0}}`; no-auto-adjust-pending-or-major finding: {'valid': 8} values={'0.0': 6, '1.0': 2}, no-auto-adjust-pending-or-major compliance: {'valid': 1} values={'0.0': 1}, inventory-eligible-variance-lines finding: {'valid': 4} values={'0.0': 4}, minor-variance-auto-adjust finding: {'valid': 1, 'inapplicable': 3} values={'0.0': 1, 'None': 3}, major-investigation-flag finding: {'inapplicable': 2, 'valid': 2} values={'None': 2, '0.0': 2}; errors=0, nonterminal=0, failed=[].

## Remaining limits

- The report checks require source-bound SKU, item, physical/system quantities, calculated variance, and USD impact. Greater-than-two-percent variances require investigation text; the minor threshold drives a persisted System Qty update, while Pending-PO and major rows are guarded against auto-adjustment. Exact source-format preservation across all prose and broader narrative completeness remain bounded gaps; scalar score 0 remains unqualified.

Native replay, repeated scoring and serialized reload/rescore preserve the reference scalar rewards and original public source bytes. Real-handler control results bind the exact draft hash and source fingerprint. These are partial components, not qualification.

Reward equality evidence: [/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4-reward-equality.json](/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4-reward-equality.json) SHA-256 `c24359c3191d1996124b22759bbaccfad487be66f47736296582f16565afa41c`. Fields `ordinary_rewards` and `manifest_rewards` are identical per completed scenario; `rewards_equal_exactly=true` records the native runner assertion.
