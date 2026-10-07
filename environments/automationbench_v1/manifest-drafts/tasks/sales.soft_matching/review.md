# Review: sales.soft_matching

Original Luna score: **1.0**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `56df79e59a4e3313b000b74e9e9e370748cf9557905ee041492b1c64493c96d0`  
Episode SHA-256: `ea91593f6809f9091e6b7b98f37a57dbfa9609f432f81fe77ee069775d4426f4`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 1.

## Native replay

Errors: 0; Same-instance rescore equal: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 2 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Action controls.** Correct phone update, wrong-contact update, title-changing harm, and missing-ACK were tested. On missing ACK, the native terminal phone outcome remains 1 while action coverage abstains; this is outcome evidence, not proof of action attribution or token advantage.

Coverage: 4 in scope, 2 expressed, 2 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
