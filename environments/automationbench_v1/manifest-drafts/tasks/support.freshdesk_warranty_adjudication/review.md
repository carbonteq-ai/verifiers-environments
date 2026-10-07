# support.freshdesk_warranty_adjudication

Public-only manifest authoring for the evaluation-reserved split. This is partial component coverage; no recorded trajectory or hidden benchmark outcome was inspected.

Draft SHA-256: `e5391d769fee9642b5acb692d01237ad5412082f89e5d731091fa8cc1b5e916c`.
Public pack SHA-256: `2cbf3c7869d34ff5dbdc85f62db54c5de7f490ba19f0429fa64fc46fb14093cc`. Public input SHA-256: `615010be2888db4e990f411c6e4ce8123ca3ed7de5a5fab270f0435f58cb1184`.
Normalized public initial-state SHA-256: `4d8002d6a7fecc7ce5debb7a9bd975952726a9c395d614bf2e53b12d8cf86a42` using [public_state.py](/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1/src/automationbench_v1/public_state.py).

Recorded replay: `unavailable_no_recorded_reference`. Ordinary hidden benchmark baseline: `unavailable_not_consulted`. Training eligibility: `not_granted`. Whole-task status: `not_qualified`.

## Expressed public obligations

| Obligation | Status | Check / reason |
|---|---|---|
| warranty-ticket-update | expressed | tag-valid-warranty-ticket |
| warranty-decision-row | expressed | log-valid-warranty-claim |
| skip-nonclaim-ticket | expressed | do-not-process-general-ticket |
| system-no-clarification | out_of_scope | out_of_scope |
| system-acted-items-only | out_of_scope | out_of_scope |
| all-claim-adjudications | gap | cross_system_reconciliation |

## Genuine-handler component controls

| Check | Correct | Harm / alternative | Missing ACK |
|---|---|---|---|
| `log-valid-warranty-claim` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |
| `tag-valid-warranty-ticket` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |
| `do-not-process-general-ticket` | 1× valid 1.0 (closed_declared_guard_scope_without_violation) | 1× valid 0.0 (witnessed_declared_guard_violation) | 1× abstained None (guard_compliance_scope_unavailable) |

Controls: 9 actual-handler synthetic executions, 0 assessment errors, 9/9 dump/reload/rescore finding-parity passes and 9/9 synthetic empty-assertion reward-map parity passes.
The reward-map comparison is harness-only. The original benchmark baseline remains unavailable. All drafts declare `credit: []`; outcome evidence and action credit remain separate.

## Limits

- Summary to #warranty-ops remains unexpressed; wording must report only acted-on items and exclusions silently.
- The synthetic correct/harm/missing-ACK alternatives exercise only the listed component obligations; they do not establish full-task coverage or a reference-trajectory replay.
- Missing-ACK effect checks abstain when the handler result is not acknowledged; fresh retained-object checks may still establish outcome from terminal state, with no action credit.
- The public-only harness empty-assertion reward map is not the original benchmark baseline; that comparison remains unavailable and no held-out assertion was read.

Source-module and handler-file fingerprints, exact handler arguments/results, receipt-bound terminal findings, and current draft hash are recorded in `review.json`.
