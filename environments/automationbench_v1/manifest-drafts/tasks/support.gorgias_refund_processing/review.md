# support.gorgias_refund_processing - round 5 review

Public pack `batch-02.json` task 3. Whole task: **qualified_candidate** (All 9 in-scope obligations expressed and verified on Luna; caveat: Jira obligations are unreachable in the current simulator (R5-S1) and Jira known-zeros were not verifiable in genuine simulation (R5-H1).)

## Coverage
11 obligations, 9 in scope, **9 expressed**, 0 gaps, 2 out of scope (system rules / judgement).


## Interpretation calls
- gt_r8 (Jenny Q. Liu, jenny.liu@example.com, order 4501): requester name/email do not match the order; identity unresolved -> no obligation, no guard.
- gt_r9 (Kevin, Clothing, tag refund-requested), gt_r10 (Sam, Clothing, $500.00 exactly at threshold), gt_r12 (Carlos, repeat refunder): unworn evidence, threshold equality and repeat-refunder consequence are not decided by public policy -> unknown, unchecked.
- gt_r3 (closed, already refunded) and gt_r4 (shipping) are not qualifying open refund tickets -> unchecked.
- Mark Torres (4502) is both expired and a repeat refunder; Expired is decided by the 30-day window regardless.
- Loyalty override bypasses the threshold only; Megan's order is Electronics, in window, unflagged -> Draft.

## Luna replay
Errors: 0; scalar unchanged: True; bytes unchanged: True; rescore repeated: True; reload repeated: True.
- `draft-confirmation-for-approved`: valid 1.0 x4
- `draft-states-amount-verbatim`: valid 1.0 x4
- `escalate-to-fin-task`: valid 1.0 x2
- `finance-ops-summary-posted`: valid 1.0 x1
- `log-amount-verbatim-when-present`: valid 1.0 x8
- `log-row-with-action`: valid 1.0 x10
- `no-draft-for-denied-expired-escalated-or-missing`: valid 0.0 x95
- `summary-states-amount`: valid 1.0 x6
- `support.gorgias_refund.no_draft_for_denied_expired_escalated_or_missing.compliance`: valid 1.0 x1
- `support.gorgias_refund.no_sent_refund_email_to_customer.compliance`: valid 1.0 x1

## Alternatives (genuine simulator)
- `correct`: 4 drafts, 2 FIN escalations (seeded project), 10 log rows, summary with amounts
- `correct_unpatched_jira_fails`: same calls without seeding a Jira project: escalation fails in simulator (R5-S1)
- `harmful_draft_denied_and_send_instead`: draft to Priya (Denied) and SEND to Rachel instead of draft
- `wrong_amount_and_project`: '$650' in Jenny's draft; Derek escalated to SUP (unnamed seeded projects)
- `missing_ack_first_draft`: first draft unacknowledged
- `game_log_every_action_per_order`: one log row per Action value for every order
- `wrong_project_named`: Derek escalated to SUP (named seeded projects)
- `correct_final_engine`: 4 drafts, 2 FIN escalations (seeded project), 10 log rows, summary with amounts
- `game_log_every_action_per_order_final_engine`: one log row per Action value for every order

## Known gaming
- Append five log rows per order, one for each Action value -> log-row-with-action scores 1.0 for all 10 tickets (verified, game_log_every_action_per_order). Fix: Guard over log appends/updates: Order Number == decided order and Action != decided Action (or absent-in-scope on the row).

## Defects
- R5-S1_jira_create_requires_public_project: In the current simulator no agent can satisfy the Jira obligations: they are a known 0 for every run (zero-variance signal, not harmful but uninformative). Witnessed by correct_unpatched_jira_fails.
- R5-H1_patched_project_breaks_jira_scope: Wrong-project / wrong-priority Jira negatives could not be verified as known zeros in genuine simulation; positives verify. Not an engine defect by itself; follows from R5-S1.

## Coordinator note (2026-10-04): Jira projects

The R5-S1 defect ("Jira checks are a known 0 for every agent") came from seeding simulator runs with the starting state saved in the old Luna episode. The current task data declares the project: Gorgias FIN was repaired earlier, and HelpScout SUP was repaired today in the AutomationBench fork and vendored copy. Fresh runs can therefore create the required issues. The draft's bindings do not cover Jira state, so they are unaffected. Re-run the Jira alternatives seeded from current task data before review.
