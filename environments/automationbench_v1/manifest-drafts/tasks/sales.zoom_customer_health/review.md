# Review: sales.zoom_customer_health

Original Luna score: **0.8**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `b2a2e17a1426c157e0e5f103422df0fdd4f26a2ac33d81951670ad1e7b515a39`  
Episode SHA-256: `d25d004692b065d464db57ee5caad50d48a71c63c17c33ad541687e28b4b66b7`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 2.

## Native replay

Errors: 0; Fresh current-contract result compared with reloaded episode rescore: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 6 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Policy-read controls.** Correct scoring/threshold sheet reads, wrong-source decoys, and missing-ACK variants test only those source-read checks. Customer health calculation, record update, and alerts remain untested task outcomes.

Coverage: 5 in scope, 2 expressed, 3 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
