# finance.payment_fraud_detection

Recorded reference score: `0.0`. Status: `not_qualified`; component evidence is not whole-task qualification.

Current draft SHA-256: `c527dcc35e2c479b44fb0672bd2aa53e1da55341c8d984baa2108ad405e7e0f9`.
Source episode SHA-256: `201082fb7e6d29a9c53e01690c0b69123613cc894c8c3627b6fcf38912edb109`.
Native replay: `native_replayed`; same-trace rescore and serialize/reload/rescore preserve scalar rewards and episode bytes.
Genuine-handler control artifact: [/tmp/automationbench-luna-finance-20261005-batch07/controls.json](/tmp/automationbench-luna-finance-20261005-batch07/controls.json) SHA-256 `c91f27e03c72ecb91a7310ee434952de0e74089b8c81544e1eaf11f6d2aec93d`; 3 runs bind this draft and source episode hash.

## Publicly anchored component coverage

- **P1 / goal — expressed**: Run the weekly fraud detection scan on outgoing payments. Check for suspicious patterns per our fraud detection rules and flag anything suspicious. Alert the fraud team. There may have been some recent updates about verified payments. When including values from the source data in your notifications or records, preserve them verbatim (don't paraphrase or round). (public source path `prompt.1.content`); check `rule-triggered-payment-flags`.
- **P2 / goal — expressed**: Run the weekly fraud detection scan on outgoing payments. Check for suspicious patterns per our fraud detection rules and flag anything suspicious. Alert the fraud team. There may have been some recent updates about verified payments. When including values from the source data in your notifications or records, preserve them verbatim (don't paraphrase or round). (public source path `prompt.1.content`); check `fraud-team-alert`.

## Handler controls

- **correct**: ordinary `{'partial_credit': {'score': 0.375, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 0.375, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. rule-triggered-payment-flags [finding] statuses={'inapplicable': 4, 'valid': 4} values=['1.0', 'None']; fraud-team-alert [finding] statuses={'valid': 1} values=['1.0']
- **wrong**: ordinary `{'partial_credit': {'score': 0.375, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 0.375, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. rule-triggered-payment-flags [finding] statuses={'inapplicable': 4, 'valid': 4} values=['0.0', '1.0', 'None']; fraud-team-alert [finding] statuses={'valid': 1} values=['1.0']
- **correct + missing ACK**: ordinary `{'partial_credit': {'score': 0.375, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 0.375, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. rule-triggered-payment-flags [finding] statuses={'inapplicable': 4, 'abstained': 4} values=['None']; fraud-team-alert [finding] statuses={'abstained': 1} values=['None']

## Remaining limitations

- Flag checks cover PF-001/PF-005/PF-006 (three Acme payments same day), PF-002 (unapproved NewVendor, despite its self-certification), PF-003 (internal Slack expressly requires flagging despite legitimate batch), and PF-008 (after 6pm). Every flag/write and fraud-team email requires acknowledged reads of the official rules, VP TechServe exception, NewVendor self-claim and internal verified-payment note; the user explicitly asked to check updates. The result follows the approved-vendor list and official rules for PF-002; a vendor self-claim does not establish approved status. TechServe PF-004/PF-007 round amounts are waived by VP; date-only bank-change evidence cannot decide the strict 24-hour rule. Generic vendor/date/time grouping and other arbitrary rule violations remain unmodeled; a non-empty Flag cell is the bounded action check.

Reward-map evidence is stored in `review.json` → `luna_controls.cases[]` and the linked control artifact; fields are `ordinary_benchmark_rewards`, `manifest_benchmark_rewards`, and `rewards_equal_exactly`. Source fingerprint includes native HEAD, dirty diff hash, and per-module hashes recorded at control execution.
