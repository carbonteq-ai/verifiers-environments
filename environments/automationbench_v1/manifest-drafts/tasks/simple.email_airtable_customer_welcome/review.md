# simple.email_airtable_customer_welcome (round 6)

Status: **qualified_candidate** — 6/6 in-scope obligations expressed, 0 gaps, 3 out of scope.

Extends the installed partial manifest `src/automationbench_v1/contracts/tasks/simple-customer-recipient-delivery.json` (its checks, sources, bindings and credit are unchanged).

## Obligations

- O1-read-onboarding-email (goal, expressed, `onboarding-email-read`): gmail.message_reads@1: a returned view of msg_3183 including its body.
- O2-read-before-acting (constraint, expressed, `read-before-record, read-before-welcome`): effect_joins timing 'before': the body read precedes the Customers record and the welcome send.
- O3-record-customer-name (goal, expressed, `customer-record-name`): Airtable createRecord/create_or_update_record with applicationId base_crm, tableName Customers, any field naming 'Lucas Grant' (field names are not prescribed); a later deleteRecord of that row voids it.
- O4-record-company (goal, expressed, `customer-record-company`): Same record also names 'Pinnacle Dynamics'.
- O5-welcome-to-customer (goal, expressed, `customer-recipient-delivery`): Installed check, unchanged: a send with lucas.grant@pinnacle.example.com in 'to'.
- O6-welcome-content (report, out_of_scope): Welcome wording is judgement.
- O7-single-customer-record (guard, expressed, `duplicate-customer-record`): Harm: a second Customers record naming Lucas Grant; not counted when either twin is deleted (self-correction).
- SYS-no-clarification (guard, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.
- SYS-list-only-acted-items (report, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.

## Luna replay

No errors; rescore and reload equal; scalar rewards and episode bytes unchanged. Values: customer-recipient-delivery=1.0, customer-record-company=1.0, customer-record-name=1.0, duplicate-customer-record=0.0, onboarding-email-read=1.0, read-before-record=1.0, read-before-welcome=1.0.

## Simulator runs and gaming

H6 create-then-delete -> O3/O4 0; H3 duplicate -> guard 1; C3/C4 duplicate then delete either -> no penalty; H4 welcome to the onboarding sender -> O5 0; H7 record before read -> O2 0.

Known gaming: Send an empty or unrelated email to lucas.grant@pinnacle.example.com (Welcome wording is out of scope (requires_judgement).); Change the record afterwards with airtable updateRecord (Airtable is an action log: updateRecord is a separate action whose target and fields are free-form; no update path was observed and not modelled.)
