# finance.vendor_insurance_verification

Native reference replay completed using the hash-verified retained episode. Serialize/reload/rescore findings matched; scalar rewards and episode source bytes were unchanged.

Official reference score remains 0.8333333333333334 (partial); this is not task qualification. No action credit is declared.

Declared results:
- `active-expiring-vendors-notified` (finding): inapplicable, value=None; obligation_not_required.
- `active-expiring-vendors-notified` (finding): valid, value=1.0; obligation_witnessed_required_effect.
- `active-expiring-vendors-notified` (scope): valid, value=1; obligation_scope_closed.
- `active-vendor-coverage-minimum-retained` (finding): inapplicable, value=None; retained_not_required.
- `active-vendor-coverage-minimum-retained` (finding): valid, value=1.0; retained_predicate_verified.
- `active-vendor-coverage-minimum-retained` (scope): valid, value=1; retained_scope_complete.
- `compliance-report-email` (finding): valid, value=1.0; obligation_witnessed_required_effect.
- `compliance-report-email` (scope): valid, value=1; obligation_scope_closed.
- `compliance-report-slack` (finding): valid, value=1.0; obligation_witnessed_required_effect.
- `compliance-report-slack` (scope): valid, value=1; obligation_scope_closed.
- `current-vendor-status-retained` (finding): inapplicable, value=None; retained_not_required.
- `current-vendor-status-retained` (finding): valid, value=1.0; retained_predicate_verified.
- `current-vendor-status-retained` (scope): valid, value=1; retained_scope_complete.
- `expired-active-vendor-marked-noncompliant` (finding): inapplicable, value=None; retained_not_required.
- `expired-active-vendor-marked-noncompliant` (finding): valid, value=0.0; retained_predicate_verified.
- `expired-active-vendor-marked-noncompliant` (scope): valid, value=1; retained_scope_complete.
- `inactive-vendor-not-named` (compliance): valid, value=1.0; closed_declared_guard_scope_without_violation.
- `inactive-vendor-not-named` (finding): valid, value=0.0; no_declared_prohibited_match.

Batch03 genuine-handler controls: correct-recorded/harm/missing-ACK/duplicate-last variants ran on native handlers (control SHA-256 379ddec6ba2544fc8048ac081ae299d9395c5458dcf1441d3bc2e1d8b91703d2); no assessment/credit errors and scalar unchanged. Harm changed checks: inactive-vendor-not-named/compliance, inactive-vendor-not-named/finding. Missing-ACK abstentions: active-expiring-vendors-notified, inactive-vendor-not-named. Duplicate-action delta: 0 findings. Recorded baseline is partial; whole-task status remains not qualified. Full findings/draft SHA/source fingerprint: review.json.
