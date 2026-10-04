# Review: sales.five_level_conditional

Original Luna score: **1.0**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `1dbb2be66c4ca116cdba3681964965e5bfde9e782f6baed152900ec4da0bba91`  
Episode SHA-256: `1654908fac779ce85d7942973c5894c1e5216c668c17244f9465a2bcefe1322b`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 1.

## Native replay

Errors: 0; Same-instance rescore equal: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 3 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Policy-read controls.** Correct workflow sheet, wrong source, and missing-ACK variants test only the policy-read check. No conditional-stage/output behavior was simulated or qualified.

Coverage: 3 in scope, 1 expressed, 2 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
