# finance.qb_recurring_journal

Recorded reference score: `0.0`. Status: `not_qualified`; component evidence is not whole-task qualification.

Current draft SHA-256: `032a1bdd44cced5a945eea9757e6a108c1e30aa8e906a1bc32939fc9bdcd45e3`.
Source episode SHA-256: `a3e5839be44a6c990f41e6bc6831b599823a2cdf172ef9e07288772c8441dc10`.
Native replay: `native_replayed`; same-trace rescore and serialize/reload/rescore preserve scalar rewards and episode bytes.
Genuine-handler control artifact: [/tmp/automationbench-luna-finance-20261005-batch07/controls.json](/tmp/automationbench-luna-finance-20261005-batch07/controls.json) SHA-256 `c91f27e03c72ecb91a7310ee434952de0e74089b8c81544e1eaf11f6d2aec93d`; 3 runs bind this draft and source episode hash.

## Publicly anchored component coverage

- **P1 / goal — expressed**: Post the monthly recurring journal entries. Check the recurring entries schedule and create each one in the system. Follow our posting procedures. Email the posting summary to controller@company.example.com.  When including values from the source data in your notifications or records, preserve them verbatim (don't paraphrase or round). Include the relevant amounts from the source data in your message(s). (public source path `prompt.1.content`); check `journal-posting-summary`.

## Handler controls

- **correct**: ordinary `{'partial_credit': {'score': 0.5714285714285714, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 0.5714285714285714, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. journal-posting-summary [finding] statuses={'valid': 1} values=['1.0']
- **wrong**: ordinary `{'partial_credit': {'score': 0.42857142857142855, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 0.42857142857142855, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. journal-posting-summary [finding] statuses={'valid': 1} values=['0.0']
- **correct + missing ACK**: ordinary `{'partial_credit': {'score': 0.5714285714285714, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 0.5714285714285714, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. journal-posting-summary [finding] statuses={'abstained': 1} values=['None']

## Remaining limitations

- No journal-entry creation or reversal tool is in this task’s available tool set, so actual recurring journal posting and Mar 1 reversal cannot be observed or credited. The public schedule’s active, in-period non-suspended entries total $14,500 debit and $14,500 credit; a single summary-email text check is only outcome partial coverage. The check does not independently enforce effective-date/status eligibility or total arithmetic.

Reward-map evidence is stored in `review.json` → `luna_controls.cases[]` and the linked control artifact; fields are `ordinary_benchmark_rewards`, `manifest_benchmark_rewards`, and `rewards_equal_exactly`. Source fingerprint includes native HEAD, dirty diff hash, and per-module hashes recorded at control execution.
