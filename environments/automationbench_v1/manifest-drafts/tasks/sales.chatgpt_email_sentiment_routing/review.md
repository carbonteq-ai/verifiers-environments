# Review: sales.chatgpt_email_sentiment_routing

Original Luna score: **0.7272727272727273**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `128836e37d944df6274b5e9a11d4522d55233874fdff8a8aa3b5be99b6578af6`  
Episode SHA-256: `34da748ef35f8799d5258b810c19f8a41de6ca0e91db38c628f2165f2e18bd94`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 1.

## Native replay

Errors: 0; Fresh current-contract result compared with reloaded episode rescore: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 3 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Policy-read controls.** Correct/wrong-source/missing-ACK variants were run; the selected routing-sheet read returned 0 on the correct and wrong-source variants and abstained on missing ACK. No outcome is inferred for sentiment, lead creation, routing, or email.

Coverage: 4 in scope, 1 expressed, 3 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
