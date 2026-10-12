# simple.email_sf_lead_rating_hot — public-input manifest review

The draft expresses 3 deterministic public obligations and records 0 explicit gap(s). It is outcome-only (`credit: []`) and remains **not qualified**.

The retained reference's historical score is 1.0 (`recorded_full_score`), but this draft does not treat that score as qualification. The pack and original episode were SHA-verified; the current native replay uses the exact public prompt and native-normalized initial state and preserves the episode bytes and historical reward map.

## Expressed obligations and gaps

- **read-email** (expressed): Find the email, then find his lead record in Salesforce and update his rating to Hot. — 
- **hot-rating** (expressed): update his rating to 'Hot' — Hot is explicit policy, not inferred from enthusiastic sentiment.
- **ben-target** (expressed): Ben Archer — The lead email identity is bound to public initial state; captured write requires same record ID and Hot value.

## Validation

Recorded native replay: [replay artifact](/tmp/automationbench-luna-simple-batch14-20261005/replay_all.json) (`de9cd36e157a2d7e8a402bc3164d0f9bbf83868460c3302e0cf733cb765e6632`), using [runner](/tmp/automationbench-luna-simple-batch14-20261005/replay_all.py) (`63a2ad6987fe9f4d3a3b5a1d5239c23680cf37b2682398ccfe32f9636c9cc990`). Prompt/initial bindings, scalar preservation, rescore idempotence, wire reload parity, and unchanged original episode bytes passed with zero errors.

Synthetic public-input component controls: [full raw controls](/tmp/automationbench-luna-simple-batch14-20261005/controls_full_v2.json) (`1377978d84e6e95d2ef22047bf37220d2b8086b588f823b4594731f88d13242a`), using [runner](/tmp/automationbench-luna-simple-batch14-20261005/controls_full.py) (`87983ecb81802728b4a5c62328dbfdaff5a5dfcb75b4022e1bf927ee07e71f7b`). Correct, harmful, and missing-ACK cases use genuine handlers and retain dispatch/return envelopes, ACKs, raw handler material, scored WireEpisodes, reward maps, findings, and pre/post source fingerprints. This is a component harness, not trajectory replay. Its ordinary task comparison uses empty assertions on the synthetic public fixture; hidden benchmark baseline parity is unavailable.

The full per-case findings and provenance hashes are in `review.json`. No credit, eligibility, or whole-task qualification is inferred.

## Revision 2026-10-12 (shard 2 eval validation)

rebound from the whole-prompt binding to the user message (prompt[1].content); field authority moved to the initial-state evidence or an ISO date spelled out in the prompt. Replayed on the Luna episode with the step-credit reader (outcome counts in manifest-validation/shard2-results.json). draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `5aff5526225b267ec378b86f5dd617033b51a942e0ef011a1af58406e2d48c68`.

Edits in this review:
- added harm guard: no Salesforce update to a record other than the target

Luna replay (step-credit reader): 2 of 2 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Luna full pass: every required goal met, no harm; empty run meets nothing. Inert (not scored by the step-credit reader): requested-record-field.


## Round 2 review (reviewer A, small-fix item 4): inert goal removed

Removed inert goal(s): requested-record-field (final lead rating == Hot). It was a retained-state kind (records.retained_when / collections.counts_when), which the training step-credit reader (manifest_outcomes) never counts, so it carried no reward and no measurement.
Counted replacement: write-requested-record (counted effects goal: update of the target lead with rating Hot, bounded to one) plus no-other-record-updated guard.
Evidence: Luna replay: 2/2 required met (unchanged), 0 harms; required/met/harm counts identical before and after the removal (required 2 -> 2, met 2 -> 2, harms 0 -> 0); no-op control meets 0 goals and 0 harms; bindings clean at turn budgets 14 and 16; 0 assessment/credit errors. Sources used only by the removed goal were dropped.
