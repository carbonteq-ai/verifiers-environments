# Review: sales.unreliable_label_account_review

Original Luna score: **0.8571428571428571**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `abbe12c047a04ea2da23d85fdd55f8c8c7d8575f995873cf93115e600bc73c5f`  
Episode SHA-256: `4518d91511687641d4199bfd4c9fedcb7502f9e8175671da248e0abbb4b3f786`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 2.

## Native replay

Errors: 0; Same-instance rescore equal: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 6 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Policy-read controls with failed source check.** Correct/wrong-source/missing-ACK variants were run for Criteria and Activity reads. Activity-read check passed on correct source; Criteria check returned 0 on both correct and wrong-source variants, and abstained for missing ACK. Therefore Criteria policy-read instrumentation is not validated. No account classification/email action controls were run.

Coverage: 5 in scope, 2 expressed, 3 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
