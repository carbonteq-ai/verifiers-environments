# Review: sales.create_draft_reply

Original Luna score: **1.0**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `2b20c9c6c181093345afb8633f25e8bb47f9c5649ce23728f536918e59dac4cb`  
Episode SHA-256: `7b34f97905a606ddd695a62bffb281a1606344e4f022ec079a9bd7db1bf5e7de`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 1.

## Native replay

Errors: 0; Same-instance rescore equal: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 3 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

**Scratch outcome probe.** Native replay through `final.created_records@1` matched a fresh retained Gmail DRAFT; wrong-thread and removed-draft control variants returned valid zero. This probe is scratch-only and outcome-only; it does not establish action credit or full task correctness.

**Remaining gaps.** The probe binds one initial candidate message, but it does not verify policy-derived largest-active-client selection or draft-body entity/count/template facts. No full missing-ACK draft control was run.


## Control scope


Coverage: 4 in scope, 1 expressed, 3 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
