# simple.email_sf_contact_onboard — public-input manifest review

The draft expresses 3 deterministic public obligations and records 0 explicit gap(s). It is outcome-only (`credit: []`) and remains **not qualified**.

The retained reference's historical score is 1.0 (`recorded_full_score`), but this draft does not treat that score as qualification. The pack and original episode were SHA-verified; the current native replay uses the exact public prompt and native-normalized initial state and preserves the episode bytes and historical reward map.

## Expressed obligations and gaps

- **read-email** (expressed): Read the email and create a Salesforce contact for them with the details from the email. — 
- **contact** (expressed): Casey Morgan, Senior Developer, casey.morgan@company.example.com — Fresh Salesforce contact retains name, email, title, and Acme account ID from public inputs.
- **company** (expressed): Use 'Acme Corp' as the company. — Bound to the unique public Acme Corp Salesforce account ID.

## Validation

Recorded native replay: [replay artifact](/tmp/automationbench-luna-simple-batch14-20261005/replay_all.json) (`de9cd36e157a2d7e8a402bc3164d0f9bbf83868460c3302e0cf733cb765e6632`), using [runner](/tmp/automationbench-luna-simple-batch14-20261005/replay_all.py) (`63a2ad6987fe9f4d3a3b5a1d5239c23680cf37b2682398ccfe32f9636c9cc990`). Prompt/initial bindings, scalar preservation, rescore idempotence, wire reload parity, and unchanged original episode bytes passed with zero errors.

Synthetic public-input component controls: [full raw controls](/tmp/automationbench-luna-simple-batch14-20261005/controls_full_v2.json) (`1377978d84e6e95d2ef22047bf37220d2b8086b588f823b4594731f88d13242a`), using [runner](/tmp/automationbench-luna-simple-batch14-20261005/controls_full.py) (`87983ecb81802728b4a5c62328dbfdaff5a5dfcb75b4022e1bf927ee07e71f7b`). Correct, harmful, and missing-ACK cases use genuine handlers and retain dispatch/return envelopes, ACKs, raw handler material, scored WireEpisodes, reward maps, findings, and pre/post source fingerprints. This is a component harness, not trajectory replay. Its ordinary task comparison uses empty assertions on the synthetic public fixture; hidden benchmark baseline parity is unavailable.

The full per-case findings and provenance hashes are in `review.json`. No credit, eligibility, or whole-task qualification is inferred.
