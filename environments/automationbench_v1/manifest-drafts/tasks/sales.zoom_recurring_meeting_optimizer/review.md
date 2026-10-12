# sales.zoom_recurring_meeting_optimizer

Original retained reference outcome: official_zero, score 0.0 (preserved). This remains a partial outcome-only draft with no action credit.

The prompt names MajorClient and asks to review the recurring meeting history and take appropriate action.
Sources: task_evidence.prompt[1].content; initial Zoom meetings/registrants and CRM account/opportunity records.

Current draft SHA256: `360a038f40447b977750bf4713f235e251aa3f5526486f8c39299a895699a7ab`. Native scored archive: `/tmp/automationbench-luna-sales-batch08-20261005/sales.zoom_recurring_meeting_optimizer.scored-episode.json`.
Native replay/reload/rescore parity=True; scalar rewards unchanged=True; source bytes unchanged=True; current source fingerprints stable=True.

Component controls use the full original prompt, assertion catalog and tool catalog. Actual reward maps and complete check outcomes are in `review.json`.
- positive: handler checks [('affected_account_named', 'valid', 1.0, 'obligation_witnessed_required_effect'), ('coverage', 'valid', 1.0, 'obligation_scope_closed')]; ordinary/manifest reward maps equal=True.
- adverse: handler checks [('affected_account_named', 'valid', 0.0, 'obligation_required_effect_missing'), ('coverage', 'valid', 1.0, 'obligation_scope_closed')]; ordinary/manifest reward maps equal=True.
- missing_ack: handler checks [('affected_account_named', 'abstained', None, 'obligation_effect_scope_unavailable'), ('coverage', 'abstained', None, 'obligation_scope_unavailable')]; ordinary/manifest reward maps equal=True.

Task remains unqualified; unsupported public obligations are listed as gaps.

## Round-2 review D (needs-fix)

Draft SHA-256 now `0d08b565351b32bc99c71b2d21ca8df289fc68e8e6b698b1d238a95e60f2c84d`. Added harm no-email-to-client-attendees (emailing any a-d@major.example.com; benchmark negatives for c@ and d@). Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Positive control (Slack post to #account-health naming MajorClient) meets the draft goal but benchmark partial credit is only 0.25. Needs data fix: add the account-health policy (what constitutes engagement risk and which of description/note/Slack/owner email to do) to the world or the prompt before outcome goals can be authored.
