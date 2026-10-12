# simple.email_airtable_lead — batch 13 review

Public replay: 40b2ce0b1d0ef00a885d4800b5649cacb68229835d977681fc80dba89774e2e2  
Draft: 60b7a43ee60b3a38b1ef63b67b0e72788211b9953e590afda19eeac0fdcf3c17

Coverage: 2 expressed, 1 gaps, 2 out of scope. Whole-task status: **not qualified**.

Native replay matched the exact public prompt and initial state. Original assertions were retained for ordinary AutomationBench scoring. Ordinary, manifest and reload reward maps matched; scalar rewards were unchanged, reload evidence matched, and there were no scorer errors. See the linked native JSON for numeric maps, per-check findings and module fingerprints.

Three authentic-handler component scenarios (positive, candidate mismatch, and missing ACK) are saved under the scratch controls directory. They use real simulator handlers and native receipt envelopes with empty assertions, so this is component evidence only. The raw input, dispatch/return material, ACK array, and per-run findings are linked in review.json.

- **out_of_scope — constraint:** system_no_questions — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **out_of_scope — constraint:** system_only_acted_items — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **expressed — goal:** read-source-email — read the email
- **expressed — goal:** create-airtable-lead — The action log was matched on base/table, sender name/email, inquiry topic and prior full-body read.
- **gap — goal:** durable-airtable-row — The real handler records the requested Airtable action but does not expose a persisted Airtable record collection. In `src/automationbench_v1/contracts/record_writes.py`, the admitted Airtable collection here is the action log; there is no candidate-bound persisted row inventory in this capture. A typed row source plus acknowledged stable identity is needed. Reuse: related Simple Airtable tasks in adjacent batches.

No action-credit policy is declared. The public request, destination identity, retained-state limits and semantic report gaps are kept separate from the component findings.

## Round 2 review (reviewer A)

Verdict: ready.

Changes: every goal comparison on a possibly absent effect field is now guarded by `present` so an omitted field is a decided miss instead of an abstention (abstained goals drop out of the training denominator: a call that omits the field would have scored 0/0). Inquiry-topic goal clause made tolerant of the Airtable column name (the prompt never names it): any of Inquiry Topic/Topic/Inquiry/Subject/Interest/Notes/Message that is present and mentions the topic; omitted topic is a decided miss. Added harm lead-created-in-wrong-table.

Evidence: Luna full pass (official 1.0): every counted goal met, no harm; no-op: 0 goals met, 0 harms; binding None at turn budgets 14 and 16; no assessment or credit errors. Synthetic controls (one-field-wrong, omitted-field, wrong-target, missing call) are in round2/a/simple/controls.json: every goal control leaves the targeted goal unmet and every guard control fires its harm (non-violating variants do not fire it).

Official-assertion differences: Official assertion checks only fields.Name; goals also require Email and the inquiry topic (prompt states both) and that the email was read first.

Notes: Column names Name and Email are assumed (Name is the official one); Email column name is a convention, not prompt text.

Gaps: Airtable column names other than the listed topic aliases and Email.
