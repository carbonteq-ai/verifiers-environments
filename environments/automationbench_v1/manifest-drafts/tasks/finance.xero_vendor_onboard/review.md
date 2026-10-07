# finance.xero_vendor_onboard (round 6)

Status: **not qualified**, 1/5 in-scope obligations expressed (4 gaps; 5 out of scope).

Correct behaviour from public data: none of the four requests should be created.
- CloudNine already exists, and changing its email needs a change-request form.
- GlobalShip has no email, and Apex's tax ID is "PENDING".
- Redstone is FLAGGED for OFAC in the sanctions sheet.

The only positive action is to confirm in the approved request's thread.

Expressed: `approved-request-confirmed-in-thread`. Which request needs a reply is decided by a rule (its text says "Approved"). Credit is withheld when the reply also names a rejected request, which matches the system rule not to narrate rejected items.

Gaps (other:non_id_record_identity). No create, duplicate or contact-detail update in Xero is observable. `service.record_writes@1` and `final.records@1` require an `id` field, and every Xero collection uses `<kind>_id` (defect D-r6-2). The guard conditions are ready to drop in once the adapter accepts `contact_id`.

Defect D-r6-1: Slack effect scope never closes when the public Slack state has no `users` list. A correct reply scores 1, but a missing, top-level or wrong-thread reply is unknown instead of 0. Reproducer: `dbg_slack2.py`.

Luna replied correctly in the CloudNine thread and left Xero unchanged: the check scores 1 and coverage abstains. Replay is clean.

Out of scope: payment terms (no such field exists), "Supplier" type (no new vendor qualifies), and rejection explanations (conflict with the system rule).


## Current-byte validation addendum (2026-10-05)

The exact current draft was `0462cf2761bfcf79ba3cc5004b56812a3855e1e5ae2ea0c6e27494eb41723789`; the historical review draft hash above remains preserved as a prior revision. Fresh replay used native candidate modules at `/home/hammad/projects/verifiers-credit-candidate-20261003/verifiers/v1/__init__.py` and `/home/hammad/projects/verifiers-credit-candidate-20261003/verifiers/v1/episode.py`. It matched the public pack and retained episode, produced 6 terminal complete batches with no assessment or credit errors, and preserved findings and scalar rewards across same-trace rescore and wire reload/rescore. Source fingerprints were identical before and after. Full evidence: `/tmp/finance-current-byte-validation-luna-20261005-06/xero_vendor_onboard-candidate-native.json` (SHA-256 `cda0f9042d3e4314642c5a75e6eee600560628f596bab22d146770258986ca11`). Earlier installed-runtime run is retained at `/tmp/finance-current-byte-validation-luna-20261005-02/finance_xero_vendor_onboard.json` and is not used as candidate-loader proof. This is retained-development validation only; the prior reference score and review conclusions remain unchanged, and it grants no qualification or eligibility.
