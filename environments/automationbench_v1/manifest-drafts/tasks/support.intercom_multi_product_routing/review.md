# support.intercom_multi_product_routing

Public-only manifest authoring for the evaluation-reserved split. This is partial component coverage; no recorded trajectory or hidden benchmark outcome was inspected.

Draft SHA-256: `49e9bc6fc1faf9ef44945b88098545cdf1797167270f290e6d7a26591b3645cf`.
Public pack SHA-256: `2cbf3c7869d34ff5dbdc85f62db54c5de7f490ba19f0429fa64fc46fb14093cc`. Public input SHA-256: `12a3ebc7e126d650292d598163ad607b1666251825a4deb294fe70d816076735`.
Normalized public initial-state SHA-256: `40783770444069d5d70e209907a33a00f8d09168d8e2812861fdd6648f956451` using [public_state.py](/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1/src/automationbench_v1/public_state.py).

Recorded replay: `unavailable_no_recorded_reference`. Ordinary hidden benchmark baseline: `unavailable_not_consulted`. Training eligibility: `not_granted`. Whole-task status: `not_qualified`.

## Expressed public obligations

| Obligation | Status | Check / reason |
|---|---|---|
| route-entitled-single-billing | expressed | tag-entitled-billing-conversation |
| no-single-product-tag-on-multiarea | expressed | no-single-product-tag-on-multi-product-case |
| system-no-clarification | out_of_scope | out_of_scope |
| system-acted-items-only | out_of_scope | out_of_scope |
| full-entitlement-routing-and-replies | gap | cross_system_reconciliation |

## Genuine-handler component controls

| Check | Correct | Harm / alternative | Missing ACK |
|---|---|---|---|
| `tag-entitled-billing-conversation` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |
| `no-single-product-tag-on-multi-product-case` | 1× valid 1.0 (closed_declared_guard_scope_without_violation) | 1× valid 0.0 (witnessed_declared_guard_violation) | 1× abstained None (guard_compliance_scope_unavailable) |

Controls: 6 actual-handler synthetic executions, 0 assessment errors, 6/6 dump/reload/rescore finding-parity passes and 6/6 synthetic empty-assertion reward-map parity passes.
The reward-map comparison is harness-only. The original benchmark baseline remains unavailable. All drafts declare `credit: []`; outcome evidence and action credit remain separate.

## Limits

- Only the two explicitly source-bound contact/company joins in these representative cases are asserted.
- The synthetic correct/harm/missing-ACK alternatives exercise only the listed component obligations; they do not establish full-task coverage or a reference-trajectory replay.
- Missing-ACK effect checks abstain when the handler result is not acknowledged; fresh retained-object checks may still establish outcome from terminal state, with no action credit.
- The public-only harness empty-assertion reward map is not the original benchmark baseline; that comparison remains unavailable and no held-out assertion was read.

Source-module and handler-file fingerprints, exact handler arguments/results, receipt-bound terminal findings, and current draft hash are recorded in `review.json`.
