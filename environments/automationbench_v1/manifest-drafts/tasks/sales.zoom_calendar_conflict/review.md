# Review: sales.zoom_calendar_conflict

Original Luna score: **1.0**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `72d05d68466fd3846317a3e55d40b721fd5fa6753ffe37e177c75070b3c90db7`  
Episode SHA-256: `709de064c1bfee8c2c3c66d37d7330c075bd051fd3c17d91b43ddff827056848`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 1.

## Native replay

Errors: 0; Fresh current-contract result compared with reloaded episode rescore: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 22 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Retained full action controls.** Retained alternatives include correct update, partner-injection harm, wrong-meeting rename, missing Zoom-update ACK, and reversed-role post-state gaming. In the reversed-role case the post-state checks all pass; current checks do not tie the intended winner/loser to the actual update and resulting state.

Coverage: 10 in scope, 10 expressed, 0 gaps, 4 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
