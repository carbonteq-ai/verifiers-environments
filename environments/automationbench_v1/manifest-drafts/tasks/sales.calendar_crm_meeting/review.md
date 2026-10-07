# Review: sales.calendar_crm_meeting

Original Luna score: **1.0**. Whole-task status: **`not_qualified`**. Public obligations, current native findings, policy/content anchors, and source hashes are recorded in `review.json`.

Draft SHA-256: `52c9be7fe68e278e65f3c0043fdbba670226038c95f482f596debd0cb898cb89`  
Episode SHA-256: `25ae9984926a68a4d02cbe833ded5eea78eaee51bbe919531a8427442d3fd08e`  
Current effective source hashes: 9 file(s); exact digests are in `review.json`. Exact policy-content bindings: 3.

## Native replay

Errors: 0; Same-instance rescore equal: True; scored-episode reload equal: True (`passed`); reload batches equal: True; scalar unchanged: True; source episode bytes unchanged: True. Findings cover 9 check ID(s). Reload validated the serialized scored episode, rebuilt task/state only from reloaded task data, retained end state, and reloaded artifacts, then rescored. 

## Control scope

**Action controls.** Correct event, wrong alias, duplicate event, and missing-ACK variants were run against the measured event-create scope. These test selected task output only; they do not resolve the public-calendar slot gap. The finite candidate/duration/event fixture and interval/timezone limitations are at `/tmp/automationbench-luna-sales-20261004/slot-selection-reproducer.json`. Dates without explicit timezones remain unknown.

Coverage: 9 in scope, 6 expressed, 3 gaps, 2 shared system rules out of scope. Passing native checks and narrow simulator controls do not qualify the whole task.
