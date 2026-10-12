# support.helpscout_response_audit

Original Luna result remains `official_partial` with partial score `0.7142857142857143`. It is retained as an unsolved reference, not treated as the target policy answer.

This draft declares 5 expressible component checks and records 2 remaining public obligation gaps. Native replay: `{'assessment': [], 'credit': []}`; original reward scalar unchanged: `True`; episode bytes unchanged: `True`; reload/rescore finding parity: `True`. Current replay findings, including misses and abstentions, are preserved in `review.json`.

Gaps: per-reply-violation-cardinality, email-report-facts. Synthetic tests exercise genuine handlers but remain component controls; they do not qualify the whole task. No action credit is assigned. Whole-task status: `not_qualified`.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `226ee1c0aeff8fd0d85a8a54b71c7aee9c06cfefc70d0b0439565d33a8867006`.

Edits in this review:
- Violation Type cell now matched with a words mention instead of equality, so one combined row listing several violation types (as the prompt does not fix a row format) satisfies each type goal
- added harm guard: no violation row for conversations that are compliant (qa03, qa06, qa09), bot-only (qa04, qa07) or unanswered (qa10)
- added goals that the four conversations with violations (hs_qa01, hs_qa02, hs_qa05, hs_qa08) are flagged on the HelpScout conversation (tag or note), as the prompt asks to flag issues as well as log them

Luna replay (step-credit reader): 8 of 12 decided required findings met; failing goal checks: flag-violating-conversations; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Violation Type matched by mention so a combined row passes. Luna logs all violations correctly but never flags conversations (flag goals fail).
