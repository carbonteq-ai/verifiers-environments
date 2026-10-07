# sales.zoom_meeting_roi_analysis

Original retained reference outcome: official_zero, score 0.0 (preserved). This remains a partial outcome-only draft with no action credit.

The current #sales-ops policy sets $10,000 per meeting hour and names sales-ops@company.example.com for the summary.
Sources: task_evidence.initial.slack.messages[msg_roi_policy].text.

Current draft SHA256: `931629ff9590f92de72f39d55fd5de7a5b9db7da4e597b86234ecaf8518d527a`. Native scored archive: `/tmp/automationbench-luna-sales-batch08-20261005/sales.zoom_meeting_roi_analysis.scored-episode.json`.
Native replay/reload/rescore parity=True; scalar rewards unchanged=True; source bytes unchanged=True; current source fingerprints stable=True.

Component controls use the full original prompt, assertion catalog and tool catalog. Actual reward maps and complete check outcomes are in `review.json`.
- positive: handler checks [('summary_recipient', 'valid', 1.0, 'obligation_witnessed_required_effect'), ('coverage', 'valid', 1.0, 'obligation_scope_closed')]; ordinary/manifest reward maps equal=True.
- adverse: handler checks [('summary_recipient', 'valid', 0.0, 'obligation_required_effect_missing'), ('coverage', 'valid', 1.0, 'obligation_scope_closed')]; ordinary/manifest reward maps equal=True.
- missing_ack: handler checks [('summary_recipient', 'abstained', None, 'obligation_effect_scope_unavailable'), ('coverage', 'abstained', None, 'obligation_scope_unavailable')]; ordinary/manifest reward maps equal=True.

Task remains unqualified; unsupported public obligations are listed as gaps.
