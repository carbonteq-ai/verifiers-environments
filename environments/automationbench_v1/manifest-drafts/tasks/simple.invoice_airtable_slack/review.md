# simple.invoice_airtable_slack

Public-input contract only; historical score and misses are preserved. This draft does not grant qualification or action credit.

- Original retained score: 1.000 (recorded_full_score; official_full).
- Public pack SHA: `351938e9a861047b71d6b1f4eec63ddd9b5772bd586d6edaf4b5d0699dd2c379`; input SHA: `626cb998b3f67dbbc826f637fd25d46f74245b31439dd4841a4f2e7ef69f1066`.
- Draft SHA: `b2eb8ebdd1c7253c57df895ef17ee49d96c1b9782a6f6bf82db9cc3e65ed81a9`; 3 public obligations expressed; 3 checks; outcome-only.
- Native replay: errors=0; scalar/rescore/reload/source-bytes/public bindings all `True`.
- Synthetic controls: three actual-handler cases (correct/adverse/missing ACK), ordinary/manifest scalar equality and reload parity verified: `True`.
- Full raw controls and source fingerprints: `/tmp/automationbench-luna-simple-batch17-20261005/controls_full_v1.json`.
- Findings treat scope/completeness separately from goal values; a valid terminal outcome can coexist with missing ACK and abstained action evidence.

Evidence limit: Public initial state has Airtable bases=[] and no base/table schema. The simulator retains this operation under airtable.actions.createRecord; the goal verifies the acknowledged action payload's base, table and fields, plus the Slack message. It does not assert a separate provider-style table-row inventory that the public input and simulator state do not expose.
