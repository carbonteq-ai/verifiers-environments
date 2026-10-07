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
