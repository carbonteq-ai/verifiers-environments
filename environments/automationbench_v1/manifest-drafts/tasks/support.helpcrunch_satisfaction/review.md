# support.helpcrunch_satisfaction

Public-only manifest authoring for the evaluation-reserved split. This is partial component coverage; no recorded trajectory or hidden benchmark outcome was inspected.

Draft SHA-256: `f2426996d09d10f75895159e33c27b46a6e1389dc28b8fdbb204ab9af46924cc`.
Public pack SHA-256: `2cbf3c7869d34ff5dbdc85f62db54c5de7f490ba19f0429fa64fc46fb14093cc`. Public input SHA-256: `5d22ace8f624a959a7344e3fe5698ff9a2d89b7938d038b30573ab398a8e03e3`.
Normalized public initial-state SHA-256: `ed83d2857fa51e5bae578cfe3e163f63f93453e55fb36cfb738dbe2ca4ac8ebc` using [public_state.py](/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1/src/automationbench_v1/public_state.py).

Recorded replay: `unavailable_no_recorded_reference`. Ordinary hidden benchmark baseline: `unavailable_not_consulted`. Training eligibility: `not_granted`. Whole-task status: `not_qualified`.

## Expressed public obligations

| Obligation | Status | Check / reason |
|---|---|---|
| escalate-calculated-dissatisfaction | expressed | create-salesforce-dissatisfaction-task |
| do-not-escalate-satisfied | expressed | do-not-escalate-satisfied-customer |
| system-no-clarification | out_of_scope | out_of_scope |
| system-acted-items-only | out_of_scope | out_of_scope |
| all-customer-weighting-and-treatment | gap | cross_system_reconciliation |

## Genuine-handler component controls

| Check | Correct | Harm / alternative | Missing ACK |
|---|---|---|---|
| `create-salesforce-dissatisfaction-task` | 1× valid 1.0 (created_matching_fresh_object_retained) | 1× valid 0.0 (created_matching_fresh_object_absent) | 1× valid 1.0 (created_matching_fresh_object_retained) |
| `do-not-escalate-satisfied-customer` | 1× valid 1.0 (closed_declared_guard_scope_without_violation) | 1× valid 0.0 (witnessed_declared_guard_violation) | 1× abstained None (guard_compliance_scope_unavailable) |

Controls: 6 actual-handler synthetic executions, 0 assessment errors, 6/6 dump/reload/rescore finding-parity passes and 6/6 synthetic empty-assertion reward-map parity passes.
The reward-map comparison is harness-only. The original benchmark baseline remains unavailable. All drafts declare `credit: []`; outcome evidence and action credit remain separate.

## Limits

- Ordinary benchmark baseline and original run are unavailable and unconsulted.
- The synthetic correct/harm/missing-ACK alternatives exercise only the listed component obligations; they do not establish full-task coverage or a reference-trajectory replay.
- Missing-ACK effect checks abstain when the handler result is not acknowledged; fresh retained-object checks may still establish outcome from terminal state, with no action credit.
- The public-only harness empty-assertion reward map is not the original benchmark baseline; that comparison remains unavailable and no held-out assertion was read.

Source-module and handler-file fingerprints, exact handler arguments/results, receipt-bound terminal findings, and current draft hash are recorded in `review.json`.
