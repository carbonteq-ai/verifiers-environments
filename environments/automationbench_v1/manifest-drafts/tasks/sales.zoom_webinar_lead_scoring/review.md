# Review: sales.zoom_webinar_lead_scoring

Original Luna score: **0.8571428571428571**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `42fe7357686d76d0efadbbf2be96aabe8d82d82732a755c11a527996e16234db`  
Episode SHA-256: `9f3156663e30868917a1cf767d1823883cb699abdb55bba17245d78431317383`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 3.

## Native replay

Errors: 0; Same-instance rescore equal: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 9 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Policy-read controls with failed source check.** Correct/wrong-source/missing-ACK variants were run for scoring rules, rating thresholds, and email override. Thresholds and override checks passed; Scoring Rules returned 0 for both correct and wrong-source variants, and abstained for missing ACK. No lead-score/action outputs were simulated.

Coverage: 5 in scope, 3 expressed, 2 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
