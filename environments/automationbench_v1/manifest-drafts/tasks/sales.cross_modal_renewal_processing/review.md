# Review: sales.cross_modal_renewal_processing

Original Luna score: **1.0**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `56057b62b04cccaf0f2ef5266a0f07cd43ffe03e45604344fab8b7eb5a5c8848`  
Episode SHA-256: `152946ff26f16d88a5ecf9e53ee8bbd79e7775280bf7b0d1dfb88e4cb86b1a7d`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 2.

## Native replay

Errors: 0; Same-instance rescore equal: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 6 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Policy-read controls.** Correct Gmail approval plus tracker reads, wrong Gmail source, and missing Gmail ACK were tested. The controls do not score account reconciliation, per-account messages, or the Slack summary.

Coverage: 5 in scope, 2 expressed, 3 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
