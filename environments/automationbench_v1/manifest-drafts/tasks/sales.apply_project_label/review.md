# Review: sales.apply_project_label

Original Luna score: **1.0**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `00f244773dddedb66fd32c91c0da98fc6d5032245d2145c4f89e7f6d8b7635df`  
Episode SHA-256: `422c1f4b2a183bf3064d8d31fb7cc634c2e298ca5c87b5339f7d57bb6ff23855`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 1.

## Native replay

Errors: 0; Fresh current-contract result compared with reloaded episode rescore: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 18 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. The isolated rehydration took 252.658 s; scoring took 8.549 s before serialization and 9.515 s after reload.

## Control scope

**Retained full action controls.** Retained correct application, by-name/decoy labeling, harmful VP direction and substring matching, self-correction, label removal after confirmation, claim-only and hedged-count gaming, and missing label/send ACKs. In the label-then-remove variant, the historical create effect remains witnessed while the separate removal prohibition also fires; keep those findings separate and do not equate the historical goal witness with final-state success.

Coverage: 8 in scope, 8 expressed, 0 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
