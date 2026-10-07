# Review: sales.create_important_draft

Original Luna score: **1.0**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `b735e4c85b860492d3894672b5a3afdeaa0ba857533438ddc4dc919dcfdf1362`  
Episode SHA-256: `a0b852d5ee29f5054a81743b749ad2666a28eb676470adb3975f60a587623fd1`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 1.

## Native replay

Errors: 0; Same-instance rescore equal: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 3 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

**Scratch outcome probe.** Native replay through `final.created_records@1` matched a fresh retained Gmail DRAFT; wrong-recipient control variants returned valid zero. This probe is scratch-only and outcome-only; it does not establish action credit or full task correctness.

**Remaining gaps.** The probe checks recipient, requested subject, and DRAFT status only. Approved figures, risk-deal reconciliation, source attribution, board format, action attribution, and a full missing-ACK draft control remain unverified.

## Control scope


Coverage: 3 in scope, 1 expressed, 2 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
