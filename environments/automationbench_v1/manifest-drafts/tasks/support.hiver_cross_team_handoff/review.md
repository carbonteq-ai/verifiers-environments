# support.hiver_cross_team_handoff

Public-only manifest authoring for the evaluation-reserved split. This is partial component coverage; no recorded trajectory or hidden benchmark outcome was inspected.

Draft SHA-256: `fbb3924b8112fe4e2d6b1f531c579dd74b77ba8939b559d69123ea2c81eeaf2e`.
Public pack SHA-256: `2cbf3c7869d34ff5dbdc85f62db54c5de7f490ba19f0429fa64fc46fb14093cc`. Public input SHA-256: `add1d15b643ae1ed40b772fef0b86e4d26b148f788e4d59141955427e24a4be4`.
Normalized public initial-state SHA-256: `c249e0b6b615bbb975f92718f3d5a0d62248458235e662d2a4d3a2898bede6a1` using [public_state.py](/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1/src/automationbench_v1/public_state.py).

Recorded replay: `unavailable_no_recorded_reference`. Ordinary hidden benchmark baseline: `unavailable_not_consulted`. Training eligibility: `not_granted`. Whole-task status: `not_qualified`.

## Expressed public obligations

| Obligation | Status | Check / reason |
|---|---|---|
| handoff-log-row | expressed | log-public-finance-handoff-candidate |
| reach-finance-lead | expressed | email-finance-lead-with-batch-reference |
| handoff-channel-notice | expressed | announce-handoff-batch-reference |
| system-no-clarification | out_of_scope | out_of_scope |
| system-acted-items-only | out_of_scope | out_of_scope |
| route-hiver-conversation | gap | handler_unavailable |
| all-handoff-candidates-and-ambiguous-rules | gap | cross_system_reconciliation |

## Genuine-handler component controls

| Check | Correct | Harm / alternative | Missing ACK |
|---|---|---|---|
| `log-public-finance-handoff-candidate` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |
| `email-finance-lead-with-batch-reference` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |
| `announce-handoff-batch-reference` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |

Controls: 9 actual-handler synthetic executions, 0 assessment errors, 9/9 dump/reload/rescore finding-parity passes and 9/9 synthetic empty-assertion reward-map parity passes.
The reward-map comparison is harness-only. The original benchmark baseline remains unavailable. All drafts declare `credit: []`; outcome evidence and action credit remain separate.

## Limits

- No Hiver write handler is present in ALL_TOOLS; finding is simulator capability, not an engine schema claim.
- The synthetic correct/harm/missing-ACK alternatives exercise only the listed component obligations; they do not establish full-task coverage or a reference-trajectory replay.
- Missing-ACK effect checks abstain when the handler result is not acknowledged; fresh retained-object checks may still establish outcome from terminal state, with no action credit.
- The public-only harness empty-assertion reward map is not the original benchmark baseline; that comparison remains unavailable and no held-out assertion was read.

Source-module and handler-file fingerprints, exact handler arguments/results, receipt-bound terminal findings, and current draft hash are recorded in `review.json`.
