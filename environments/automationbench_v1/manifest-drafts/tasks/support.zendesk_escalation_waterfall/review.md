# support.zendesk_escalation_waterfall

Public-only manifest authoring for the evaluation-reserved split. This is partial component coverage; no recorded trajectory or hidden benchmark outcome was inspected.

Draft SHA-256: `ce7e985e571f8af41f56143650ef37c99872df357f740ee24d9670ff12d3a88d`.
Public pack SHA-256: `2cbf3c7869d34ff5dbdc85f62db54c5de7f490ba19f0429fa64fc46fb14093cc`. Public input SHA-256: `ec0e4dc9b6177ffc7ccdb8b194a958d85da3c3e8acd4d9c552a1944cf5a58e3b`.
Normalized public initial-state SHA-256: `93f8fa2196669ec25ae0629b763631b620a80b32df355de1c72e4df94f5a6bc2` using [public_state.py](/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1/src/automationbench_v1/public_state.py).

Recorded replay: `unavailable_no_recorded_reference`. Ordinary hidden benchmark baseline: `unavailable_not_consulted`. Training eligibility: `not_granted`. Whole-task status: `not_qualified`.

## Expressed public obligations

| Obligation | Status | Check / reason |
|---|---|---|
| advance-known-tier1-review-ticket | expressed | advance-tier1-ticket-to-tier2 |
| log-escalation-transition | expressed | log-tier1-to-tier2-transition |
| do-not-exceed-max-tier | expressed | do-not-escalate-at-max-tier |
| system-no-clarification | out_of_scope | out_of_scope |
| system-acted-items-only | out_of_scope | out_of_scope |
| ready-cooldown-and-new-ticket-population | gap | policy_ambiguity |
| all-tier-routing-and-report | gap | cross_system_reconciliation |

## Genuine-handler component controls

| Check | Correct | Harm / alternative | Missing ACK |
|---|---|---|---|
| `advance-tier1-ticket-to-tier2` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |
| `log-tier1-to-tier2-transition` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |
| `do-not-escalate-at-max-tier` | 1× valid 1.0 (closed_declared_guard_scope_without_violation) | 1× valid 0.0 (witnessed_declared_guard_violation) | 1× abstained None (guard_compliance_scope_unavailable) |

Controls: 9 actual-handler synthetic executions, 0 assessment errors, 9/9 dump/reload/rescore finding-parity passes and 9/9 synthetic empty-assertion reward-map parity passes.
The reward-map comparison is harness-only. The original benchmark baseline remains unavailable. All drafts declare `credit: []`; outcome evidence and action credit remain separate.

## Limits

- No arbitrary cooldown duration was inferred from the public date values.
- The synthetic correct/harm/missing-ACK alternatives exercise only the listed component obligations; they do not establish full-task coverage or a reference-trajectory replay.
- Missing-ACK effect checks abstain when the handler result is not acknowledged; fresh retained-object checks may still establish outcome from terminal state, with no action credit.
- The public-only harness empty-assertion reward map is not the original benchmark baseline; that comparison remains unavailable and no held-out assertion was read.

Source-module and handler-file fingerprints, exact handler arguments/results, receipt-bound terminal findings, and current draft hash are recorded in `review.json`.
