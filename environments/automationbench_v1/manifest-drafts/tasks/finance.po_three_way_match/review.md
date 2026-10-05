# finance.po_three_way_match

Recorded reference score: `0.0`. Status: `not_qualified`; component evidence is not whole-task qualification.

Current draft SHA-256: `490d4691665db9b2e994d8bccef387e8ac790e6fc253bd2f4097993bf69104b6`.
Source episode SHA-256: `7823eb67c4360fb7fd5398ac6cf27eb5312095ec6a4af98815752233f68a59be`.
Native replay: `native_replayed`; same-trace rescore and serialize/reload/rescore preserve scalar rewards and episode bytes.
Genuine-handler control artifact: [/tmp/automationbench-luna-finance-20261005-batch07/controls.json](/tmp/automationbench-luna-finance-20261005-batch07/controls.json) SHA-256 `c91f27e03c72ecb91a7310ee434952de0e74089b8c81544e1eaf11f6d2aec93d`; 3 runs bind this draft and source episode hash.

## Publicly anchored component coverage

- **P1 / goal — expressed**: Run the three-way match for this batch of vendor invoices. Match each invoice against the purchase order and the receiving report. Approve invoices where all three match within tolerance. Flag any discrepancies and notify the AP team.  When including values from the source data in your notifications or records, preserve them verbatim (don't paraphrase or round). (public source path `prompt.1.content`); check `status-po-5501`.
- **P2 / goal — expressed**: Run the three-way match for this batch of vendor invoices. Match each invoice against the purchase order and the receiving report. Approve invoices where all three match within tolerance. Flag any discrepancies and notify the AP team.  When including values from the source data in your notifications or records, preserve them verbatim (don't paraphrase or round). (public source path `prompt.1.content`); check `status-po-5502`.
- **P3 / goal — expressed**: Run the three-way match for this batch of vendor invoices. Match each invoice against the purchase order and the receiving report. Approve invoices where all three match within tolerance. Flag any discrepancies and notify the AP team.  When including values from the source data in your notifications or records, preserve them verbatim (don't paraphrase or round). (public source path `prompt.1.content`); check `status-po-5503`.
- **P4 / goal — expressed**: Run the three-way match for this batch of vendor invoices. Match each invoice against the purchase order and the receiving report. Approve invoices where all three match within tolerance. Flag any discrepancies and notify the AP team.  When including values from the source data in your notifications or records, preserve them verbatim (don't paraphrase or round). (public source path `prompt.1.content`); check `status-po-5504`.

## Handler controls

- **correct**: ordinary `{'partial_credit': {'score': 0.6666666666666666, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 0.6666666666666666, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. status-po-5501 [finding] statuses={'valid': 1, 'inapplicable': 3} values=['1.0', 'None']; status-po-5502 [finding] statuses={'inapplicable': 3, 'valid': 1} values=['1.0', 'None']; status-po-5503 [finding] statuses={'inapplicable': 3, 'valid': 1} values=['1.0', 'None']; status-po-5504 [finding] statuses={'inapplicable': 3, 'valid': 1} values=['1.0', 'None']; ap-team-discrepancy-alert [finding] statuses={'valid': 1} values=['1.0']
- **wrong**: ordinary `{'partial_credit': {'score': 0.5, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 0.5, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. status-po-5501 [finding] statuses={'valid': 1, 'inapplicable': 3} values=['1.0', 'None']; status-po-5502 [finding] statuses={'inapplicable': 3, 'valid': 1} values=['1.0', 'None']; status-po-5503 [finding] statuses={'inapplicable': 3, 'valid': 1} values=['0.0', 'None']; status-po-5504 [finding] statuses={'inapplicable': 3, 'valid': 1} values=['1.0', 'None']; ap-team-discrepancy-alert [finding] statuses={'valid': 1} values=['1.0']
- **correct + missing ACK**: ordinary `{'partial_credit': {'score': 0.6666666666666666, 'weight': 1.0}}`; manifest `{'partial_credit': {'score': 0.6666666666666666, 'weight': 1.0}}` (equal); errors=0, nonterminal=0. status-po-5501 [finding] statuses={'abstained': 1, 'inapplicable': 3} values=['None']; status-po-5502 [finding] statuses={'inapplicable': 3, 'abstained': 1} values=['None']; status-po-5503 [finding] statuses={'inapplicable': 3, 'abstained': 1} values=['None']; status-po-5504 [finding] statuses={'inapplicable': 3, 'abstained': 1} values=['None']; ap-team-discrepancy-alert [finding] statuses={'abstained': 1} values=['None']

## Remaining limitations

- The four task-derived status outcomes are source arithmetic but this draft currently checks only exact status writes. It does not join each invoice against its purchase order and receiving report, does not prove price/quantity calculation or notification to AP, and does not evaluate alternate correct policy wording.

Reward-map evidence is stored in `review.json` → `luna_controls.cases[]` and the linked control artifact; fields are `ordinary_benchmark_rewards`, `manifest_benchmark_rewards`, and `rewards_equal_exactly`. Source fingerprint includes native HEAD, dirty diff hash, and per-module hashes recorded at control execution.
