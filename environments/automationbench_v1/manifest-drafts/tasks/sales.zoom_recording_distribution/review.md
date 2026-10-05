# sales.zoom_recording_distribution

Original retained reference outcome: official_zero, score 0.0 (preserved). This remains a partial outcome-only draft with no action credit.

The discovery policy says internal attendees only, no external prospect email, and create a note on the related opportunity with recording URL.
Sources: task_evidence.initial.google_sheets.rows on ws_dist_rules; Zoom mtg_disc_001; Salesforce opportunity 006xx000004TSS1.

Current draft SHA256: `04e56d797f8f518f966706bc7cb33a2cecfdfafcf00f1b0ce62a7dec09d3bd02`. Native scored archive: `/tmp/automationbench-luna-sales-batch08-20261005/sales.zoom_recording_distribution.scored-episode.json`.
Native replay/reload/rescore parity=True; scalar rewards unchanged=True; source bytes unchanged=True; current source fingerprints stable=True.

Component controls use the full original prompt, assertion catalog and tool catalog. Actual reward maps and complete check outcomes are in `review.json`.
- positive: handler checks [('compliance', 'valid', 1.0, 'closed_declared_guard_scope_without_violation'), ('discovery_recording_logged', 'valid', 1.0, 'obligation_witnessed_required_effect'), ('coverage', 'valid', 1.0, 'obligation_scope_closed'), ('discovery_recording_note', 'valid', 1.0, 'obligation_occurrence_count_verified'), ('coverage', 'valid', 1.0, 'obligation_scope_closed')]; ordinary/manifest reward maps equal=True.
- adverse: handler checks [('no_external_discovery_distribution', 'valid', 1.0, 'witnessed_declared_prohibited_effect'), ('compliance', 'valid', 0.0, 'witnessed_declared_guard_violation'), ('discovery_recording_logged', 'valid', 0.0, 'obligation_required_effect_missing'), ('coverage', 'valid', 1.0, 'obligation_scope_closed'), ('discovery_recording_note', 'valid', 0.0, 'obligation_occurrence_count_below_minimum'), ('coverage', 'valid', 1.0, 'obligation_scope_closed')]; ordinary/manifest reward maps equal=True.
- missing_ack: handler checks [('compliance', 'abstained', None, 'guard_compliance_scope_unavailable'), ('discovery_recording_logged', 'abstained', None, 'obligation_effect_scope_unavailable'), ('coverage', 'abstained', None, 'obligation_scope_unavailable'), ('discovery_recording_note', 'abstained', None, 'obligation_occurrence_count_unavailable'), ('coverage', 'abstained', None, 'obligation_scope_unavailable')]; ordinary/manifest reward maps equal=True.

Task remains unqualified; unsupported public obligations are listed as gaps.
