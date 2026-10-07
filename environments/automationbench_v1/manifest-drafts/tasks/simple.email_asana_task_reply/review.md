# simple.email_asana_task_reply — batch 13 review

Public replay: 243e6f0a29592fc2cc28246bd3421bda7c8fd97bc65e426402fb5005edc0df81  
Draft: e5ce9f546b82e743d01a4a9f91e251c91d7d03be560bef70705e09c613d24db7

Coverage: 3 expressed, 2 gaps, 2 out of scope. Whole-task status: **not qualified**.

Native replay matched the exact public prompt and initial state. Original assertions were retained for ordinary AutomationBench scoring. Ordinary, manifest and reload reward maps matched; scalar rewards were unchanged, reload evidence matched, and there were no scorer errors. See the linked native JSON for numeric maps, per-check findings and module fingerprints.

Three authentic-handler component scenarios (positive, candidate mismatch, and missing ACK) are saved under the scratch controls directory. They use real simulator handlers and native receipt envelopes with empty assertions, so this is component evidence only. The raw input, dispatch/return material, ACK array, and per-run findings are linked in review.json.

- **out_of_scope — constraint:** system_no_questions — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **out_of_scope — constraint:** system_only_acted_items — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **expressed — goal:** read-source-email — Read the email
- **expressed — goal:** create-product-team-task — The action record is matched to Product team, subject words and prior body read.
- **gap — goal:** durable-asana-task — The current task adapter exposes an Asana action record rather than a retained task object with a stable identity. In `src/automationbench_v1/contracts/record_writes.py`, this source records `actions.create_task`, not a retained Asana task object. Add a typed task creation and retained-task evidence source.
- **expressed — goal:** reply-to-sender — reply to the sender
- **gap — report:** confirmation-content — The current send check proves recipient and prior read, but not that the new message body confirms receipt. In `src/automationbench_v1/contracts/predicates.py`, `Mentions` explicitly treats presence as mention rather than positive assertion (negated mentions still match); a deterministic semantic confirmation operator is needed or this meaning stays unavailable.

No action-credit policy is declared. The public request, destination identity, retained-state limits and semantic report gaps are kept separate from the component findings.
