# sales.zoom_regional_webinar_coordinator

Original retained reference outcome: official_zero, score 0.0 (preserved). This remains a partial outcome-only draft with no action credit.

The prompt names Global Product Update, regional-sales destination, and requests regional policy processing.
Sources: task_evidence.prompt[1].content; google_sheets.rows on ws_thresholds; Zoom registrants for meeting 9001.

Current draft SHA256: `ff886056d2cebc3943c49e807c08a727c72606e5c76bf6073e5b90d240247602`. Native scored archive: `/tmp/automationbench-luna-sales-batch08-20261005/sales.zoom_regional_webinar_coordinator.scored-episode.json`.
Native replay/reload/rescore parity=True; scalar rewards unchanged=True; source bytes unchanged=True; current source fingerprints stable=True.

Component controls use the full original prompt, assertion catalog and tool catalog. Actual reward maps and complete check outcomes are in `review.json`.
- positive: handler checks [('registration_summary', 'valid', 1.0, 'obligation_witnessed_required_effect'), ('coverage', 'valid', 1.0, 'obligation_scope_closed')]; ordinary/manifest reward maps equal=True.
- adverse: handler checks [('registration_summary', 'valid', 0.0, 'obligation_required_effect_missing'), ('coverage', 'valid', 1.0, 'obligation_scope_closed')]; ordinary/manifest reward maps equal=True.
- missing_ack: handler checks [('registration_summary', 'abstained', None, 'obligation_effect_scope_unavailable'), ('coverage', 'abstained', None, 'obligation_scope_unavailable')]; ordinary/manifest reward maps equal=True.

Task remains unqualified; unsupported public obligations are listed as gaps.
