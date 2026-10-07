# simple.hs_update_deal_stage

Public-input contract only; historical score and misses are preserved. This draft does not grant qualification or action credit.

- Original retained score: 1.000 (recorded_full_score; official_full).
- Public pack SHA: `351938e9a861047b71d6b1f4eec63ddd9b5772bd586d6edaf4b5d0699dd2c379`; input SHA: `f0a7a47ac583659f34152398e864b3021205e271c7935178fe61cb5e7366acbe`.
- Draft SHA: `6a8db5d9d31b71c866a15792178b2a5148fd35b5f7c84d48e5d5633d5bf023a9`; 1 public obligations expressed; 2 checks; outcome-only.
- Native replay: errors=0; scalar/rescore/reload/source-bytes/public bindings all `True`.
- Synthetic controls: three actual-handler cases (correct/adverse/missing ACK), ordinary/manifest scalar equality and reload parity verified: `True`.
- Full raw controls and source fingerprints: `/tmp/automationbench-luna-simple-batch17-20261005/controls_full_v1.json`.
- Findings treat scope/completeness separately from goal values; a valid terminal outcome can coexist with missing ACK and abstained action evidence.
