# support.zendesk_customer_sentiment

Public-only manifest authoring for the evaluation-reserved split. This is partial component coverage; no recorded trajectory or hidden benchmark outcome was inspected.

Draft SHA-256: `feeab61d8993d70ed84e98deb9af975a040cf5c88199f17ed1d9ea0d3e5dbd07`.
Public pack SHA-256: `2cbf3c7869d34ff5dbdc85f62db54c5de7f490ba19f0429fa64fc46fb14093cc`. Public input SHA-256: `d90b2abb8b7fb548863a84e7713e1f6495c730cdb0f6459023dbee2c57ae2e6e`.
Normalized public initial-state SHA-256: `889cb39438f1d2215c3071c39244ca634b3be64120c8929a32ee575df39ed3e1` using [public_state.py](/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1/src/automationbench_v1/public_state.py).

Recorded replay: `unavailable_no_recorded_reference`. Ordinary hidden benchmark baseline: `unavailable_not_consulted`. Training eligibility: `not_granted`. Whole-task status: `not_qualified`.

## Expressed public obligations

| Obligation | Status | Check / reason |
|---|---|---|
| customer-health-summary-channel-and-reference | expressed | post-customer-health-batch-summary |
| system-no-clarification | out_of_scope | out_of_scope |
| system-acted-items-only | out_of_scope | out_of_scope |
| sentiment-classification-and-actions | gap | requires_judgement |
| complete-sentiment-report-facts | gap | report_fact_coverage |

## Genuine-handler component controls

| Check | Correct | Harm / alternative | Missing ACK |
|---|---|---|---|
| `post-customer-health-batch-summary` | 1× valid 1.0 (obligation_witnessed_required_effect) | 1× valid 0.0 (obligation_required_effect_missing) | 1× abstained None (obligation_effect_scope_unavailable) |

Controls: 3 actual-handler synthetic executions, 0 assessment errors, 3/3 dump/reload/rescore finding-parity passes and 3/3 synthetic empty-assertion reward-map parity passes.
The reward-map comparison is harness-only. The original benchmark baseline remains unavailable. All drafts declare `credit: []`; outcome evidence and action credit remain separate.

## Limits

- No subjective sentiment label or routing choice is encoded as ground truth.
- The synthetic correct/harm/missing-ACK alternatives exercise only the listed component obligations; they do not establish full-task coverage or a reference-trajectory replay.
- Missing-ACK effect checks abstain when the handler result is not acknowledged; fresh retained-object checks may still establish outcome from terminal state, with no action credit.
- The public-only harness empty-assertion reward map is not the original benchmark baseline; that comparison remains unavailable and no held-out assertion was read.

Source-module and handler-file fingerprints, exact handler arguments/results, receipt-bound terminal findings, and current draft hash are recorded in `review.json`.
