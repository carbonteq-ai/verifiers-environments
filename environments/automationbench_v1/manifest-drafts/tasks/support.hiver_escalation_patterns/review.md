# support.hiver_escalation_patterns

Public-only manifest authoring for the evaluation-reserved split. This is partial component coverage; no recorded trajectory or hidden benchmark outcome was inspected.

Draft SHA-256: `f99ea7c5cd9ba160b6d1f15c40e77f97cbac210049268c089e22ea5f7afff3a3`.
Public pack SHA-256: `2cbf3c7869d34ff5dbdc85f62db54c5de7f490ba19f0429fa64fc46fb14093cc`. Public input SHA-256: `2d8dd6cdad76ef0a9f81aa179e47a9b9e6698fedc9d8afc856d4c56aefe43e91`.
Normalized public initial-state SHA-256: `2eed3d96b15e7b753295d74b0ddf60e2473b6b5d0726ebe134cbd5e386b966ff` using [public_state.py](/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1/src/automationbench_v1/public_state.py).

Recorded replay: `unavailable_no_recorded_reference`. Ordinary hidden benchmark baseline: `unavailable_not_consulted`. Training eligibility: `not_granted`. Whole-task status: `not_qualified`.

## Expressed public obligations

| Obligation | Status | Check / reason |
|---|---|---|
| auth-failure-count | expressed | log-exact-auth-pattern-occurrences |
| threshold-jira-issue | expressed | create-threshold-auth-jira-issue |
| exact-pattern-count-report | expressed | post-auth-exact-count |
| system-no-clarification | out_of_scope | out_of_scope |
| system-acted-items-only | out_of_scope | out_of_scope |
| all-pattern-qualifying-counts | gap | cross_system_aggregation |

## Genuine-handler component controls

| Check | Correct | Harm / alternative | Missing ACK |
|---|---|---|---|
| `log-exact-auth-pattern-occurrences` | 1× valid 1.0 (obligation_occurrence_count_verified) | 1× valid 0.0 (obligation_occurrence_count_exceeded) | 1× abstained None (obligation_occurrence_count_unavailable) |
| `create-threshold-auth-jira-issue` | 1× valid 1.0 (created_matching_fresh_object_retained) | 1× valid 0.0 (created_matching_fresh_object_absent) | 1× valid 1.0 (created_matching_fresh_object_retained) |
| `post-auth-exact-count` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |

Controls: 9 actual-handler synthetic executions, 0 assessment errors, 9/9 dump/reload/rescore finding-parity passes and 9/9 synthetic empty-assertion reward-map parity passes.
The reward-map comparison is harness-only. The original benchmark baseline remains unavailable. All drafts declare `credit: []`; outcome evidence and action credit remain separate.

## Limits

- The task requires exact thresholds/counts; occurrence bounds are outcome-only and have no action credit.
- The synthetic correct/harm/missing-ACK alternatives exercise only the listed component obligations; they do not establish full-task coverage or a reference-trajectory replay.
- Missing-ACK effect checks abstain when the handler result is not acknowledged; fresh retained-object checks may still establish outcome from terminal state, with no action credit.
- The public-only harness empty-assertion reward map is not the original benchmark baseline; that comparison remains unavailable and no held-out assertion was read.

Source-module and handler-file fingerprints, exact handler arguments/results, receipt-bound terminal findings, and current draft hash are recorded in `review.json`.
