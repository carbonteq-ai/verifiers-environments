# Review: sales.slack_deal_notification

Original Luna score: **0.6666666666666666**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `5aaecc98910836d5182ad2995eff4b16e55b0969660b1019bd7cd6f35363b91d`  
Episode SHA-256: `6f3d234ebbb14307d72d14fd13d8d3fdf9900ef0ae466862a4b72c40b59e0ee1`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 2.

## Native replay

Errors: 0; Fresh current-contract result compared with reloaded episode rescore: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 6 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Policy-read controls.** Correct/wrong-source/missing-ACK variants for both competing format messages returned 0 on correct and wrong-source fixtures, with abstention on missing ACK. The source authority conflict and Slack/opportunity output remain unqualified.

Coverage: 6 in scope, 2 expressed, 4 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
