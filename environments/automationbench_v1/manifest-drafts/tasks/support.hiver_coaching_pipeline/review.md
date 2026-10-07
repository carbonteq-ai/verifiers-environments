# support.hiver_coaching_pipeline

Public-only manifest authoring for the evaluation-reserved split. This is partial component coverage; no recorded trajectory or hidden benchmark outcome was inspected.

Draft SHA-256: `0b7e4a6c3b6a1374729facf8bf7d7a10987ffc6690e0b9b0b42b552e91447ee3`.
Public pack SHA-256: `2cbf3c7869d34ff5dbdc85f62db54c5de7f490ba19f0429fa64fc46fb14093cc`. Public input SHA-256: `4a9236f03bb1c95941b394879394dd927f5dd22f932d3718a9fb88dab535aab8`.
Normalized public initial-state SHA-256: `3994ddd59be28f3cd64bbb2e269b23a0f8eed1a692b10ffbde2c9cd86d49efed` using [public_state.py](/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1/src/automationbench_v1/public_state.py).

Recorded replay: `unavailable_no_recorded_reference`. Ordinary hidden benchmark baseline: `unavailable_not_consulted`. Training eligibility: `not_granted`. Whole-task status: `not_qualified`.

## Expressed public obligations

| Obligation | Status | Check / reason |
|---|---|---|
| coaching-recommendation-fiona | expressed | log-coaching-recommendation-fiona |
| manager-notice-name-rate | expressed | email-fiona-manager-with-name-and-rate |
| system-no-clarification | out_of_scope | out_of_scope |
| system-acted-items-only | out_of_scope | out_of_scope |
| complete-roster-evaluation | gap | cross_population_aggregation |

## Genuine-handler component controls

| Check | Correct | Harm / alternative | Missing ACK |
|---|---|---|---|
| `log-coaching-recommendation-fiona` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |
| `email-fiona-manager-with-name-and-rate` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |

Controls: 6 actual-handler synthetic executions, 0 assessment errors, 6/6 dump/reload/rescore finding-parity passes and 6/6 synthetic empty-assertion reward-map parity passes.
The reward-map comparison is harness-only. The original benchmark baseline remains unavailable. All drafts declare `credit: []`; outcome evidence and action credit remain separate.

## Limits

- Hiver exposes read-only tools in this simulator; no assignment or conversation write handler was found. This task only requires recommendation output, so no Hiver write is asserted.
- The synthetic correct/harm/missing-ACK alternatives exercise only the listed component obligations; they do not establish full-task coverage or a reference-trajectory replay.
- Missing-ACK effect checks abstain when the handler result is not acknowledged; fresh retained-object checks may still establish outcome from terminal state, with no action credit.
- The public-only harness empty-assertion reward map is not the original benchmark baseline; that comparison remains unavailable and no held-out assertion was read.

Source-module and handler-file fingerprints, exact handler arguments/results, receipt-bound terminal findings, and current draft hash are recorded in `review.json`.
