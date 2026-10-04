# simple.zendesk_resolve_email (round 6)

Status: **qualified_candidate** — 2/2 in-scope obligations expressed, 0 gaps, 3 out of scope.

Extends the installed partial manifest `src/automationbench_v1/contracts/tasks/simple-zendesk-retained-status.json` (its checks, sources, bindings and credit are unchanged).

## Obligations

- O1-ticket-solved (goal, expressed, `requested-ticket-solved`): Installed check, unchanged: final ZD-501 status is 'solved' (records.retained_when@1), with its credit. Reopening or closing instead of solving is 0.
- O2-resolution-email-to-customer (goal, expressed, `resolution-email-to-customer`): gmail.messages@1 send with the prompt address in 'to'. Order relative to the status update is free.
- O3-email-is-a-resolution-notice (report, out_of_scope): Whether the body explains the resolution is wording; no exact fact is required.
- SYS-no-clarification (guard, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.
- SYS-list-only-acted-items (report, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.

## Luna replay

No errors; rescore and reload equal; scalar rewards and episode bytes unchanged. Values: requested-ticket-solved=1.0, resolution-email-to-customer=1.0.

## Simulator runs and gaming

H1 (email claims resolved, status untouched) -> solved 0; H2 (solve then reopen) -> retained 0; H4 closed instead of solved -> 0. Only one ticket exists and no action is prohibited, so duplicates and channel guards do not apply.

Known gaming: Send an unrelated or empty email to elena.voss@retail.example.com (Resolution wording is out of scope (requires_judgement).)
