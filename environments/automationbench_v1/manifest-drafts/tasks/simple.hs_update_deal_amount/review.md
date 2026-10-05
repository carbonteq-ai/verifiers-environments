# simple.hs_update_deal_amount

Public-input contract only; historical score and misses are preserved. This draft does not grant qualification or action credit.

- Original retained score: 1.000 (recorded_full_score; official_full).
- Public pack SHA: `351938e9a861047b71d6b1f4eec63ddd9b5772bd586d6edaf4b5d0699dd2c379`; input SHA: `a934a3ca0915891bd6a090e1bab5d6a3a73de4071f8fe2b57c9880082ca97733`.
- Draft SHA: `c8eb9a28315c0cd589750596a1bb6d61e9b845b95424920e2c66a8d8711470b6`; 1 public obligations expressed; 2 checks; outcome-only.
- Native replay: errors=0; scalar/rescore/reload/source-bytes/public bindings all `True`.
- Synthetic controls: three actual-handler cases (correct/adverse/missing ACK), ordinary/manifest scalar equality and reload parity verified: `True`.
- Full raw controls and source fingerprints: `/tmp/automationbench-luna-simple-batch17-20261005/controls_full_v1.json`.
- Findings treat scope/completeness separately from goal values; a valid terminal outcome can coexist with missing ACK and abstained action evidence.
