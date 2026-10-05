# finance.forex_gain_loss

Recorded reference scalar score: `0.0`. Reference class: `recorded_partial_score`. Component controls are not whole-task qualification.

Current draft SHA-256: `99713f23bc00ed897be6015f098f6f21839e9f4fb7044660872d24ff76bffdda`.
Source episode SHA-256: `8b52bab895124a34ffd7b1853fecfae2fdb617838403e2d875541ffc2774fda5`.
Native replay fingerprint: HEAD `3d7ebc418d7e4c34390129847b517d55be5cdfda`, dirty source diff SHA-256 `ef070429e2ec467cc849ae1473bb8f4fef48a05fd11a6590b5eec0c8f725a2e5`.
Genuine-handler controls: [/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4.json](/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4.json) SHA-256 `c24359c3191d1996124b22759bbaccfad487be66f47736296582f16565afa41c`; 3 case runs tied to this draft hash and source episode.

## Publicly anchored component coverage

- **lookup-current-rate-by-currency** — expressed; check `invoice-fx-impact-report`. Compare original booking rate against today’s rate. (user prompt; ws_current_rates)
- **report-per-invoice-usd-impact** — expressed; check `invoice-fx-impact-report`. Determine gain/loss impact and email controller. (user prompt)
- **verbatim-source-values** — gap; check `—`. When including source values in notifications, preserve them verbatim. (user prompt)
- **system-no-clarification** — out_of_scope; check `—`. Do not ask clarifying questions. (system prompt)
- **system-list-only-acted-items** — out_of_scope; check `—`. List only items you acted on. (system prompt)

## Handler controls

- **correct**: ordinary rewards `{'partial_credit': {'score': 0.2, 'weight': 1.0}}`; invoice-fx-impact-report finding: valid=3 values={'1.0': 3}; nonterminal=0, failed=[], errors=0.
- **wrong**: ordinary rewards `{'partial_credit': {'score': 0.2, 'weight': 1.0}}`; invoice-fx-impact-report finding: valid=3 values={'0.0': 1, '1.0': 2}; nonterminal=0, failed=[], errors=0.
- **correct + missing ACK**: ordinary rewards `{'partial_credit': {'score': 0.2, 'weight': 1.0}}`; invoice-fx-impact-report finding: abstained=3 values={'None': 3}; nonterminal=0, failed=[], errors=0.

## Remaining gaps and interpretation

- The exact current rate is source-looked-up by currency; report contains the exact computed USD change and currency/invoice. The report check does not yet require the foreign and booked USD input values to appear verbatim.

The original reference score and assertion outcomes remain untouched. Native rescore, repeat rescore, serialize/reload/rescore, and real-handler controls preserve ordinary reward values and source bytes. Findings demonstrate only the listed deterministic checks.

Reward equality evidence: [/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4-reward-equality.json](/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4-reward-equality.json) SHA-256 `c24359c3191d1996124b22759bbaccfad487be66f47736296582f16565afa41c`. Fields `ordinary_rewards` and `manifest_rewards` are identical per completed scenario; `rewards_equal_exactly=true` records the native runner assertion.
