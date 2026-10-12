# simple.email_hubspot_deal_slack — batch 13 review

Public replay: c48f00c145d2a3a95e573f74469d89b1def97a28e206d3a367e4ed821633019e  
Draft: 84bcdfbc1e03a0a1538e3027132266e71fbed14358e8fd2f97d7f7279314a6a7

Coverage: 3 expressed, 0 gaps, 2 out of scope. Whole-task status: **not qualified**.

Native replay matched the exact public prompt and initial state. Original assertions were retained for ordinary AutomationBench scoring. Ordinary, manifest and reload reward maps matched; scalar rewards were unchanged, reload evidence matched, and there were no scorer errors. See the linked native JSON for numeric maps, per-check findings and module fingerprints.

Three authentic-handler component scenarios (positive, candidate mismatch, and missing ACK) are saved under the scratch controls directory. They use real simulator handlers and native receipt envelopes with empty assertions, so this is component evidence only. The raw input, dispatch/return material, ACK array, and per-run findings are linked in review.json.

- **out_of_scope — constraint:** system_no_questions — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **out_of_scope — constraint:** system_only_acted_items — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **expressed — goal:** read-partner-email — Read the email
- **expressed — goal:** create-named-deal — The retained HubSpot write check binds deal name, exact numeric amount and prior read.
- **expressed — goal:** notify-partnerships — notify the #partnerships Slack channel

No action-credit policy is declared. The public request, destination identity, retained-state limits and semantic report gaps are kept separate from the component findings.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `d7e3fdd3bd7e79290253d764e964c07d3436d557c9542eaf64c4f7215f9147ab`.

Edits in this review:
- added harm guard: no Slack post to a channel other than the requested one
- added harm guard: no duplicate creation of the same record

Luna replay (step-credit reader): 3 of 3 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Luna full pass: every required goal met, no harm; empty run meets nothing.
