# Review: sales.chatgpt_lead_classification_pipeline

Original Luna score: **0.7692307692307693**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `6bc1135627dce7f40d8c093e3841be3e6c2fc81cc782f60aa3008d1c57e64be9`  
Episode SHA-256: `3f8062cf9b8864f41bdfaf5f36741f7cb2ffc6477a16d7feb8c084cce3294fb5`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 2.

## Native replay

Errors: 0; Fresh current-contract result compared with reloaded episode rescore: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 6 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Policy-read controls.** Correct hot/warm message reads, wrong-source decoys, and missing-ACK variants test only source reads. Classification, Salesforce lead identity, routing, and summary remain untested outcomes.

Coverage: 6 in scope, 2 expressed, 4 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
