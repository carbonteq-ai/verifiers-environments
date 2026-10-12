# support.helpscout_kb_feedback

Reference outcome remains `official_partial` at score `0.5238095238095238`; this is partial evidence, not qualification.
Current draft SHA-256: `353ff6a9c79fe3274e778c884d3f48fd37e2fe32ba1d72ecd371d826a11442ee`. Whole-task status: `not_qualified`.
Native replay/reload: `passed`; public prompt and initial state matched; scalar rewards, episode bytes and findings were unchanged; errors: `0`.
Genuine-handler controls (correct/harm/missing-ACK) vs ordinary-task baseline: `passed`; see `review.json` and `/tmp/automationbench-luna-support-batch05-20261005/controls.json`.
Correct-control positive signals: support-helpscout_kb_feedback.include-batch-reference, support-helpscout_kb_feedback.include-batch-reference.coverage, support-helpscout_kb_feedback.log-detailed-explanation, support-helpscout_kb_feedback.log-detailed-explanation.coverage, support-helpscout_kb_feedback.log-outdated-documentation, support-helpscout_kb_feedback.log-outdated-documentation.coverage, support-helpscout_kb_feedback.post-docs-team, support-helpscout_kb_feedback.post-docs-team.coverage.
Harm-control zero-valued signals: support-helpscout_kb_feedback.log-outdated-documentation.
Unclosed public requirements retained as gaps: jira-detailed, message-entity-names, classification-from-nested-threads.
Synthetic cases are component controls through real simulator handlers; they are not original trajectory replays.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `3b7fce7b3bd620b6d791a7fbbc915cbe27aa793c0d692ce993c4594804560e83`.

Edits in this review:
- dropped the invented Type literals from the two log goals (prompt names no Type values; log row keyed by Conversation ID); added DOCS Jira goals for the three detailed-explanation topics (prompt requires them); added harm guard for finding rows on conversations with no KB signal
- added goals that the two conversations mentioning outdated documentation (hs_kb02, hs_kb05) are flagged on the HelpScout conversation (tag or note), as the prompt asks to flag them separately from logging

Luna replay (step-credit reader): 7 of 9 decided required findings met; failing goal checks: flag-outdated-documentation-conversations; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Invented Type literals removed; Jira DOCS goals and flag goals added. Luna never tagged/noted the outdated-docs conversations (flag goals fail, real miss).
