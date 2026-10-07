# finance.vendor_statement_reconciliation

Official Luna partial_credit score: 1.0. Outcome score only; `credit` is empty.

Draft SHA-256: `d691b36a9c8a779c6e9ab30bfe84fe2bc2768287ab807bc2c28417b271c40fe6`. Native replay errors: 0; rescore/reload/scalar/episode bytes stable: True/True/True/True.

Coverage: 3 in-scope obligations; 3 expressed; 0 gaps; 1 system rules out of scope.

- **V1 expressed** — Reconcile the vendor statements we received against our AP records. Statement/AP lookup and matched-row comparisons select unresolved vendors; same-vendor mail is checked with the source balance and discrepancy.
- **V2 expressed** — email each vendor with unresolved items. Per-candidate acknowledged sends for the unresolved statement vendors.
- **V3 expressed** — Send the reconciliation summary to controller@company.example.com. Controller summary requires the unresolved vendors and source-derived balances.
- **O1 out_of_scope** — Do not ask clarifying questions; list only items acted on. Shared system communication rule is outside this batch’s qualification scope.

Whole-task status: **not_qualified**. The retained native episode was replayed with current source fingerprints, but no correct/harmful/missing-ACK or gaming simulator variants were run.

Batch02 native-handler controls (2026-10-05): correct/harm/missing-ACK/gaming variants were replayed through real handlers; all findings and digests are in review.json and /tmp/automationbench-luna-finance-20261004/batch02/sim_batch02.json. The correct case is not full qualification. Harm caught: finance_vendor_recon.no_resolved_vendor_email, finance_vendor_recon.no_resolved_vendor_email.compliance, settled_vendor_not_emailed; gaming caught: finance_vendor_recon.no_resolved_vendor_email, finance_vendor_recon.no_resolved_vendor_email.compliance, settled_vendor_not_emailed; missing-ACK abstentions: each_unresolved_vendor_emailed, finance_vendor_recon.controller_summary.coverage, finance_vendor_recon.no_resolved_vendor_email, finance_vendor_recon.no_resolved_vendor_email.compliance, finance_vendor_recon.unresolved_vendor_notified, finance_vendor_recon.unresolved_vendor_notified.coverage, settled_vendor_not_emailed.
