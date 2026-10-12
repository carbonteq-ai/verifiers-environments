# simple.hs_create_contact

Public-input contract only; historical score and misses are preserved. This draft does not grant qualification or action credit.

- Original retained score: 1.000 (recorded_full_score; official_full).
- Public pack SHA: `351938e9a861047b71d6b1f4eec63ddd9b5772bd586d6edaf4b5d0699dd2c379`; input SHA: `f45a07fc75641b177c305a4e6164259bb2cb8f0ab9e77858e50bf2a69317688f`.
- Draft SHA: `dd46becc9117574a4efefce65589a89cd542188ae3fae21ba301df863fd3bd3f`; 1 public obligations expressed; 2 checks; outcome-only.
- Native replay: errors=0; scalar/rescore/reload/source-bytes/public bindings all `True`.
- Synthetic controls: three actual-handler cases (correct/adverse/missing ACK), ordinary/manifest scalar equality and reload parity verified: `True`.
- Full raw controls and source fingerprints: `/tmp/automationbench-luna-simple-batch17-20261005/controls_full_v1.json`.
- Findings treat scope/completeness separately from goal values; a valid terminal outcome can coexist with missing ACK and abstained action evidence.

## Re-review (shard 3)

Supersedes the earlier statement that no harm guard is asserted: guards are duplicate-contact. Goals re-derived from the prompt and task data. Luna replay: 1/1 required goals met, 0 harms. No-op control (prompt, no tool calls): 0 goals met, 0 harms. Verdict: eval-ready.

Note: Retained/created-and-retained goals (where present) are not read by manifest_outcomes (no retained finding is produced in replay); the acknowledged-effect goal carries the requirement. Initial values differ from the requested ones, so a no-op cannot satisfy them.
