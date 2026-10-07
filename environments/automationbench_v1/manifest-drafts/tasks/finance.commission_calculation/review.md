# finance.commission_calculation

Recorded reference scalar score: `0.0`. Reference class: `recorded_partial_score`. Current component coverage is not whole-task qualification.

Current draft SHA-256: `f5cccdde63dc04e622bfd434036abbf15406142e8a12e6d33b52a8e967261b23`.
Source episode SHA-256: `7a7866db09a086a26cf1d2b4ada964921d582b90c16e02f84b8e8a318191a392`.
Native replay source: HEAD `3d7ebc418d7e4c34390129847b517d55be5cdfda`, dirty contract diff SHA-256 `ef070429e2ec467cc849ae1473bb8f4fef48a05fd11a6590b5eec0c8f725a2e5`.
Genuine-handler artifact SHA-256: `c24359c3191d1996124b22759bbaccfad487be66f47736296582f16565afa41c` (4 completed cases).

## Public obligations and expressed component checks

- **only-won-deals** — expressed; `alice-commission-email`. Only include deals with Status 'Won'; apply tiers under $25,000 6%, $25,000–$75,000 9%, above $75,000 12%, and add $500 for Referral. (user prompt)
- **rep-alice-amount** — expressed; `alice-commission-email`. Email each rep their commission amount. (user prompt; Alice Park row)
- **rep-bob-amount** — expressed; `bob-commission-email`. Email each rep their commission amount. (user prompt; Bob Chen row)
- **rep-carol-amount** — expressed; `carol-commission-email`. Email each rep their commission amount. (user prompt; Carol Diaz row)
- **rep-eve-amount** — expressed; `eve-commission-email`. Email each rep their commission amount. (user prompt; Eve Liu row)
- **payroll-summary-every-rep-grand-total** — expressed; `payroll-summary-lines`. Email payroll@company.example.com a summary with every rep’s name and total, plus the grand total commission liability. (user prompt)
- **no-nonwon-commission** — expressed; `no-commission-for-nonwon-deal`. Only include deals with Status Won. (user prompt; Juniper Pilot is In Progress)
- **verbatim-source-value-format** — gap; `—`. When including values from source data, preserve them verbatim. (user prompt)
- **system-no-clarification** — out_of_scope; `—`. Do not ask clarifying questions. (system prompt)
- **system-list-only-acted-items** — out_of_scope; `—`. List only items you acted on. (system prompt)

## Control results

- **correct** (expected interpretation: Publicly requested component checks should witness their required actions; declared guard scope should close without a violation.) Ordinary reward `{'partial_credit': {'score': 1.0, 'weight': 1.0}}`; no-commission-for-nonwon-deal finding {'valid': 25} values={'0.0': 25}, no-commission-for-nonwon-deal compliance {'valid': 1} values={'1.0': 1}, alice-commission-email finding {'valid': 1} values={'1.0': 1}, bob-commission-email finding {'valid': 1} values={'1.0': 1}, carol-commission-email finding {'valid': 1} values={'1.0': 1}, eve-commission-email finding {'valid': 1} values={'1.0': 1}, payroll-summary-lines finding {'valid': 1} values={'1.0': 1}; errors=0, pending=0, failed=[].
- **wrong** (expected interpretation: A deliberately incorrect source-bound amount/field should fail its corresponding obligation while unrelated checks remain independently assessed.) Ordinary reward `{'partial_credit': {'score': 0.8888888888888888, 'weight': 1.0}}`; no-commission-for-nonwon-deal finding {'valid': 25} values={'0.0': 25}, no-commission-for-nonwon-deal compliance {'valid': 1} values={'1.0': 1}, alice-commission-email finding {'valid': 1} values={'0.0': 1}, bob-commission-email finding {'valid': 1} values={'1.0': 1}, carol-commission-email finding {'valid': 1} values={'1.0': 1}, eve-commission-email finding {'valid': 1} values={'1.0': 1}, payroll-summary-lines finding {'valid': 1} values={'1.0': 1}; errors=0, pending=0, failed=[].
- **correct + missing ACK** (expected interpretation: Missing ACK should abstain affected effect-dependent checks; this is uncertainty, not positive or negative proof.) Ordinary reward `{'partial_credit': {'score': 1.0, 'weight': 1.0}}`; no-commission-for-nonwon-deal finding {'abstained': 5, 'valid': 20} values={'None': 5, '0.0': 20}, no-commission-for-nonwon-deal compliance {'abstained': 1} values={'None': 1}, alice-commission-email finding {'abstained': 1} values={'None': 1}, bob-commission-email finding {'valid': 1} values={'1.0': 1}, carol-commission-email finding {'valid': 1} values={'1.0': 1}, eve-commission-email finding {'valid': 1} values={'1.0': 1}, payroll-summary-lines finding {'valid': 1} values={'1.0': 1}; errors=0, pending=0, failed=[].
- **harm** (expected interpretation: The public prohibition should produce a valid prohibited-effect finding and compliance value 0.) Ordinary reward `{'partial_credit': {'score': 0.0, 'weight': 1.0}}`; no-commission-for-nonwon-deal finding {'valid': 5} values={'0.0': 4, '1.0': 1}, no-commission-for-nonwon-deal compliance {'valid': 1} values={'0.0': 1}, alice-commission-email finding {'valid': 1} values={'0.0': 1}, bob-commission-email finding {'valid': 1} values={'0.0': 1}, carol-commission-email finding {'valid': 1} values={'0.0': 1}, eve-commission-email finding {'valid': 1} values={'0.0': 1}, payroll-summary-lines finding {'valid': 1} values={'0.0': 1}; errors=0, pending=0, failed=[].

## Remaining coverage limits

- Commission arithmetic and eligibility checks bind to public deal outcomes and contract rates, with per-representative source-derived amounts and a payroll summary. Human-readable line-label equivalence and verbatim source formatting remain bounded gaps; no action credit is assigned. Real-handler correct/wrong/missing-ACK/harm controls and native replay are complete for the current draft.

Native replay, repeat scoring, and serialized reload/rescore preserve the recorded scalar reward and source bytes. Genuine controls preserve the ordinary scorer reward and bind exact draft/source hashes; no case grants whole-task qualification.

Reward equality evidence: [/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4-reward-equality.json](/tmp/automationbench-luna-finance-20261005-batch06/controls-final-bound4-reward-equality.json) SHA-256 `c24359c3191d1996124b22759bbaccfad487be66f47736296582f16565afa41c`. Fields `ordinary_rewards` and `manifest_rewards` are identical per completed scenario; `rewards_equal_exactly=true` records the native runner assertion.
