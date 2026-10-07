# support.intercom_freshdesk_escalation

Public-only manifest authoring for the evaluation-reserved split. This is partial component coverage; no recorded trajectory or hidden benchmark outcome was inspected.

Draft SHA-256: `af14d52957c92469f5502779f26cf4448446406e2b8c4a18296a8dddb4ed7a9a`.
Public pack SHA-256: `2cbf3c7869d34ff5dbdc85f62db54c5de7f490ba19f0429fa64fc46fb14093cc`. Public input SHA-256: `a3c18aa005d6c3f3dd4e401ef282b4864d7e8960b09d467321e1949198bd2fcd`.
Normalized public initial-state SHA-256: `041dc5970295d4127755952b813698bb1234b6c25853571507e5678e880dbbf7` using [public_state.py](/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1/src/automationbench_v1/public_state.py).

Recorded replay: `unavailable_no_recorded_reference`. Ordinary hidden benchmark baseline: `unavailable_not_consulted`. Training eligibility: `not_granted`. Whole-task status: `not_qualified`.

## Expressed public obligations

| Obligation | Status | Check / reason |
|---|---|---|
| create-l2-freshdesk-ticket | expressed | create-eligible-default-priority-freshdesk-ticket |
| tag-contact-after-escalation | expressed | tag-escalated-intercom-contact |
| report-escalation-channel | expressed | escalation-summary-channel |
| system-no-clarification | out_of_scope | out_of_scope |
| system-acted-items-only | out_of_scope | out_of_scope |
| eligible-escalation-population | gap | cross_system_reconciliation |
| conversation-action-record | gap | handler_or_linkage_unavailable |

## Genuine-handler component controls

| Check | Correct | Harm / alternative | Missing ACK |
|---|---|---|---|
| `create-eligible-default-priority-freshdesk-ticket` | 1× valid 1.0 (created_matching_fresh_object_retained) | 1× valid 0.0 (created_matching_fresh_object_absent) | 1× valid 1.0 (created_matching_fresh_object_retained) |
| `tag-escalated-intercom-contact` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |
| `escalation-summary-channel` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |

Controls: 9 actual-handler synthetic executions, 0 assessment errors, 9/9 dump/reload/rescore finding-parity passes and 9/9 synthetic empty-assertion reward-map parity passes.
The reward-map comparison is harness-only. The original benchmark baseline remains unavailable. All drafts declare `credit: []`; outcome evidence and action credit remain separate.

## Limits

- Only the public standard priority rule is asserted.
- The synthetic correct/harm/missing-ACK alternatives exercise only the listed component obligations; they do not establish full-task coverage or a reference-trajectory replay.
- Missing-ACK effect checks abstain when the handler result is not acknowledged; fresh retained-object checks may still establish outcome from terminal state, with no action credit.
- The public-only harness empty-assertion reward map is not the original benchmark baseline; that comparison remains unavailable and no held-out assertion was read.

Source-module and handler-file fingerprints, exact handler arguments/results, receipt-bound terminal findings, and current draft hash are recorded in `review.json`.
