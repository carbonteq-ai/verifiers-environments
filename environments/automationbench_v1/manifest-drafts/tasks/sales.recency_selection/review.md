# Review: sales.recency_selection

Original Luna score: **0.75**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `b4488fbe173abde45382b166c8649f7232cc76c2ad02453fd592203e35b2f2cd`  
Episode SHA-256: `a50f46d2f1673508019a178722dc1e2d2603bdf89f5ce825152de85afdc4c58f`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 1.

## Native replay

Errors: 0; Fresh current-contract result compared with reloaded episode rescore: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 3 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Policy-read controls.** Correct/wrong-source/missing-ACK variants test one selected recent-message read only. Full recency population reconciliation, contact resolution, and note/source linkage remain untested.

Coverage: 4 in scope, 1 expressed, 3 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
