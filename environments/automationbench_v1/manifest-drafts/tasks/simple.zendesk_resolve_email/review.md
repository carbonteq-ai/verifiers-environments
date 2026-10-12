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

## Re-review (shard 3)

Supersedes the earlier statement that no harm guard is asserted: guards are wrong-recipient. Goals re-derived from the prompt and task data. Luna replay: 2/2 required goals met, 0 harms. No-op control (prompt, no tool calls): 0 goals met, 0 harms. Verdict: eval-ready.

Edit: Added ticket-status-solved effect goal (zendesk_update_ticket, ZD-501 -> solved) because the retained-state goal is not read by manifest_outcomes.

Note: Retained/created-and-retained goals (where present) are not read by manifest_outcomes (no retained finding is produced in replay); the acknowledged-effect goal carries the requirement. Initial values differ from the requested ones, so a no-op cannot satisfy them.


## Round 2 review (reviewer A, small-fix item 3): proposal draft.proposed.json

draft.json is untouched. draft.proposed.json is a byte copy of the reviewed eval draft (the draft.json in this folder) proposed as the replacement of the installed qualified manifest; adopting it needs requalification of the credit declarations because the check set changes.
Why: Installed qualified manifest uses records.retained_when for ticket ZD-501 solved, which the step-credit reader does not count. The reviewed draft adds counted goals (ticket update to solved, resolution email to the customer) and a wrong-recipient guard; the installed check was identical in intent.
Evidence (replay.py): installed manifest: binding(14/16)=manifest_source_binding_mismatch/manifest_source_binding_mismatch; Luna required=0 met=0 harms=0; no-op goals=0 harms=0. Reviewed/proposed draft: binding(14/16)=ok/ok; Luna required=2 met=2 harms=0; no-op goals=0 harms=0. Guard violation controls for the added guards that Luna did not trigger are listed in round2/a/guards/guard-controls.json (small-fix item 5).
