# sales.zoom_crm_meeting

Original retained reference outcome: official_zero, score 0.0 (preserved). This remains a partial outcome-only draft with no action credit.

The task requests a West Division demo; msg_zoom_001 names that division and its senior leadership.
Sources: task_evidence.prompt[1].content; task_evidence.initial.gmail.messages[0].body_plain; Salesforce accounts and contacts.

Current draft SHA256: `ea9351b834162c8536249906a24856e0e79c54ba976ec4cb915774e7648cf910`. Native scored archive: `/tmp/automationbench-luna-sales-batch08-20261005/sales.zoom_crm_meeting.scored-episode.json`.
Native replay/reload/rescore parity=True; scalar rewards unchanged=True; source bytes unchanged=True; current source fingerprints stable=True.

Component controls use the full original prompt, assertion catalog and tool catalog. Actual reward maps and complete check outcomes are in `review.json`.
- positive: handler checks [('west_demo_meeting', 'valid', 1.0, 'obligation_occurrence_count_verified'), ('coverage', 'valid', 1.0, 'obligation_scope_closed')]; ordinary/manifest reward maps equal=True.
- adverse: handler checks [('west_demo_meeting', 'valid', 0.0, 'obligation_occurrence_count_below_minimum'), ('coverage', 'valid', 1.0, 'obligation_scope_closed')]; ordinary/manifest reward maps equal=True.
- missing_ack: handler checks [('west_demo_meeting', 'abstained', None, 'obligation_occurrence_count_unavailable'), ('coverage', 'abstained', None, 'obligation_scope_unavailable')]; ordinary/manifest reward maps equal=True.

Task remains unqualified; unsupported public obligations are listed as gaps.
