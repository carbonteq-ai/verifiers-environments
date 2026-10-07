# hr.docusign_policy_acknowledgment — component review

- Public batch: batch04 HR index 3; pack SHA-256 `29539f3639ae9402772aceaf1dddc62b3b571aba8976936e664d41ae7f48a902`.
- Draft SHA-256 `9ab9dc6ece7a7cbd4628226ef6dd067ac2c2db2c732f2da6101cf733ca472a93`; source episode SHA-256 `0a2e404254a99ebccf6abf8a07c8f42aacf11c6d8386ac0550f64fb1388ebce6`.
- Original recorded score retained: `{'partial_credit': {'score': 0.6, 'weight': 1.0}}`. This is partial reference evidence, not qualification.
- Coverage: 2 expressed, 1 gaps, 0 explicitly out of scope (3 reviewed). Gap categories: `{'other:underdetermined_tracker_transition': 1}`.
- Native replay: no errors; rescore/reload consolidated results repeated; original scalar and episode bytes unchanged. Reload batch partition differs.
- Genuine simulator controls: 3 executed; unavailable controls: 0.
  - `positive-unsigned-signer-sent-envelope`: hr.policy_ack_signed_status_changed.compliance: status=valid value=1.0 reason=closed_declared_guard_scope_without_violation; hr.policy_ack_envelope_for_already_signed.compliance: status=valid value=1.0 reason=closed_declared_guard_scope_without_violation; hr.policy_ack_envelope_sent: status=valid value=1.0 reason=created_matching_fresh_object_retained; hr.policy_ack_envelope_sent.coverage: status=valid value=1.0 reason=created_scope_closed
  - `harm-already-signed-recipient`: hr.policy_ack_signed_status_changed.compliance: status=valid value=1.0 reason=closed_declared_guard_scope_without_violation; hr.policy_ack_envelope_for_already_signed: status=valid value=1.0 reason=witnessed_declared_prohibited_effect; hr.policy_ack_envelope_sent.coverage: status=valid value=1.0 reason=created_scope_closed
  - `gaming-created-not-sent`: hr.policy_ack_signed_status_changed.compliance: status=valid value=1.0 reason=closed_declared_guard_scope_without_violation; hr.policy_ack_envelope_for_already_signed.compliance: status=valid value=1.0 reason=closed_declared_guard_scope_without_violation; hr.policy_ack_envelope_sent.coverage: status=valid value=1.0 reason=created_scope_closed
- Limitation `tracker-completion`: The public tracker contains Signed but no Sent/Envelope Status field, and sending an envelope does not mean the employee signed. The prompt says to update the tracker but supplies no field/value transition, so no status update can be inferred.

Whole-task status: **not qualified**. Source revisions: env HEAD `3d7ebc418d7e4c34390129847b517d55be5cdfda`, native HEAD `959da6381394942596cb15e0cbe78f4df8594c22`; see `review.json` for working-tree hashes.
