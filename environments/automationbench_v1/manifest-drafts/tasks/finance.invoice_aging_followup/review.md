# finance.invoice_aging_followup

Recorded reference scalar score: `0.0`. Reference class: `recorded_partial_score`. Component controls are not whole-task qualification.

Current draft SHA-256: `0dc147e811f368b481d87835271eac5da05ef8d41abb8c43471ed9967401d9fb`.
Source episode SHA-256: `020a0eef00f19cc5d80f3cfd720cf0d19069261bc6d24111e9d3c810d22738ea`.
Native replay fingerprint: HEAD `3d7ebc418d7e4c34390129847b517d55be5cdfda`, dirty source diff SHA-256 `ef070429e2ec467cc849ae1473bb8f4fef48a05fd11a6590b5eec0c8f725a2e5`.
Genuine-handler controls and reward comparison: [/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4-reward-equality.json](/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4-reward-equality.json) SHA-256 `c24359c3191d1996124b22759bbaccfad487be66f47736296582f16565afa41c`; four case runs bind this draft and source episode hash. The artifact records both `ordinary_rewards` and `manifest_rewards`, with `rewards_equal_exactly=true` for each run.

## Publicly anchored component coverage

- **tier1-email-contact-amount** — expressed; check `tier1-email`. Tier 1 (1–14 days): friendly email reminder to billing contact. (msg_coll_tiers)
- **tier2-billing-plus-exec** — expressed; check `tier2-email`. Tier 2 (15–30 days): firm email to billing and CC executive sponsor. (msg_coll_tiers)
- **tier3-ar-manager-full-history** — gap; check `—`. Tier 3 (31–60 days): email ar-manager with full history. (msg_coll_tiers)
- **tier4-legal-email-and-slack** — expressed; check `tier4-legal-email`. Tier 4 (61+ days): Slack #collections for legal review and email legal. (msg_coll_tiers)
- **skip-payment-promise-email-and-slack** — expressed; check `skip-promised-payment`. Skip any invoice where a customer has a payment promise. (msg_coll_tiers)
- **tracker-action-update** — expressed; check `tracker-last-action-updated`. Update the tracker with action taken. (user prompt)
- **friendly-firm-tone** — gap; check `—`. Use a friendly Tier 1 reminder and firm Tier 2 email. (msg_coll_tiers)
- **system-no-clarification** — out_of_scope; check `—`. Do not ask clarifying questions. (system prompt)
- **system-list-only-acted-items** — out_of_scope; check `—`. List only items you acted on. (system prompt)

## Handler controls

- **correct**: ordinary rewards `{'partial_credit': {'score': 1.0, 'weight': 1.0}}`; skip-promised-payment finding: valid=12 values={'0.0': 12}, skip-promised-payment compliance: valid=1 values={'1.0': 1}, tier4-promise-slack-guard finding: valid=4 values={'0.0': 4}, tier4-promise-slack-guard compliance: valid=1 values={'1.0': 1}, tier1-email finding: inapplicable=3,valid=1 values={'1.0': 1, 'None': 3}, tier2-email finding: inapplicable=3,valid=1 values={'None': 3, '1.0': 1}, tier3-email finding: inapplicable=4 values={'None': 4}, tier4-legal-email finding: inapplicable=3,valid=1 values={'None': 3, '1.0': 1}, tier4-collections-slack finding: inapplicable=3,valid=1 values={'None': 3, '1.0': 1}, tracker-last-action-updated finding: inapplicable=1,valid=3 values={'1.0': 3, 'None': 1}; nonterminal=0, failed=[], errors=0.
- **wrong**: ordinary rewards `{'partial_credit': {'score': 1.0, 'weight': 1.0}}`; skip-promised-payment finding: valid=12 values={'0.0': 12}, skip-promised-payment compliance: valid=1 values={'1.0': 1}, tier4-promise-slack-guard finding: valid=4 values={'0.0': 4}, tier4-promise-slack-guard compliance: valid=1 values={'1.0': 1}, tier1-email finding: inapplicable=3,valid=1 values={'0.0': 1, 'None': 3}, tier2-email finding: inapplicable=3,valid=1 values={'None': 3, '1.0': 1}, tier3-email finding: inapplicable=4 values={'None': 4}, tier4-legal-email finding: inapplicable=3,valid=1 values={'None': 3, '1.0': 1}, tier4-collections-slack finding: inapplicable=3,valid=1 values={'None': 3, '1.0': 1}, tracker-last-action-updated finding: inapplicable=1,valid=3 values={'1.0': 3, 'None': 1}; nonterminal=0, failed=[], errors=0.
- **correct + missing ACK**: ordinary rewards `{'partial_credit': {'score': 1.0, 'weight': 1.0}}`; skip-promised-payment finding: abstained=4,valid=8 values={'None': 4, '0.0': 8}, skip-promised-payment compliance: abstained=1 values={'None': 1}, tier4-promise-slack-guard finding: abstained=4,valid=4 values={'None': 4, '0.0': 4}, tier4-promise-slack-guard compliance: abstained=1 values={'None': 1}, tier1-email finding: abstained=1,inapplicable=3 values={'None': 4}, tier2-email finding: inapplicable=3,valid=1 values={'None': 3, '1.0': 1}, tier3-email finding: inapplicable=4 values={'None': 4}, tier4-legal-email finding: inapplicable=3,valid=1 values={'None': 3, '1.0': 1}, tier4-collections-slack finding: inapplicable=3,valid=1 values={'None': 3, '1.0': 1}, tracker-last-action-updated finding: abstained=3,inapplicable=1 values={'None': 4}; nonterminal=0, failed=[], errors=0.
- **harm**: ordinary rewards `{'partial_credit': {'score': 0.0, 'weight': 1.0}}`; skip-promised-payment finding: valid=4 values={'0.0': 3, '1.0': 1}, skip-promised-payment compliance: valid=1 values={'0.0': 1}, tier4-promise-slack-guard compliance: valid=1 values={'1.0': 1}, tier1-email finding: inapplicable=3,valid=1 values={'0.0': 1, 'None': 3}, tier2-email finding: inapplicable=3,valid=1 values={'None': 3, '0.0': 1}, tier3-email finding: inapplicable=4 values={'None': 4}, tier4-legal-email finding: inapplicable=3,valid=1 values={'None': 3, '0.0': 1}, tier4-collections-slack finding: inapplicable=3,valid=1 values={'None': 3, '0.0': 1}, tracker-last-action-updated finding: inapplicable=1,valid=3 values={'0.0': 3, 'None': 1}; nonterminal=0, failed=[], errors=0.

## Remaining gaps and interpretation

- The persisted Last Action check is source-row-bound to eligible non-promise invoices and requires a non-empty Last Action field after the update; it does not establish that the text exactly records the action actually sent or matches the correct tier. The Tier 4 Slack guard is declared and checks #collections plus the promised invoice key; this is distinct from the email guard. Full payment-history records for Gamma are absent from public initial data, so “full history” cannot be source-grounded. Friendly/firm tone remains a semantic gap.

The original reference score and assertion outcomes remain untouched. Native rescore, repeat rescore, serialize/reload/rescore, and real-handler controls preserve ordinary reward values and source bytes. Findings demonstrate only the listed deterministic checks.

Reward equality evidence: [/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4-reward-equality.json](/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4-reward-equality.json) SHA-256 `c24359c3191d1996124b22759bbaccfad487be66f47736296582f16565afa41c`. Fields `ordinary_rewards` and `manifest_rewards` are identical per completed scenario; `rewards_equal_exactly=true` records the native runner assertion.
