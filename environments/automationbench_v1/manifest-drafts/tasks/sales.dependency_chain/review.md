# Review: sales.dependency_chain

Original Luna score: **1.0**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `b097eb88ed49ecd2ff80afdd3dec108f9536fa10799e17ac3e52ce40b03648f7`  
Episode SHA-256: `ab3e0e30bc22c3377f43de7934ddd09eda5c5cf616777a00dd7f85121d907530`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 2.

## Native replay

Errors: 0; Same-instance rescore equal: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 6 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Policy-read controls.** Correct email and rate-sheet reads, wrong email source, and missing email ACK were tested. These controls do not score hierarchy, amount calculation, contact selection, or sent-mail output. The exact public rate-policy content is bound; source-read tests do not qualify its use.

Coverage: 5 in scope, 2 expressed, 3 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
