# support.helpcrunch_usage_alerts

Original Luna reference remains **official_partial** at 0.6153846153846154; this review preserves that partial evidence and does not qualify the whole task.

The draft expresses 20 of 22 reviewed obligations; unresolved gaps: window-count-general, low-alert-completeness. Whole-task status: `not_qualified`.

Native replay: native replay passed; prompt-bound public initial state matched the retained episode, serialization/reload rescore findings matched, scores and episode bytes were unchanged. Finding statuses: {'inapplicable': 24, 'valid': 47, 'abstained': 1}.

Four minimized public-initial component controls (correct, harmful, missing acknowledgement, false-fact exploratory) exercised genuine simulator handlers with no execution errors. They are not original-trajectory replays and do not establish complete task coverage; detailed per-check outcomes and limitations are in `review.json`.

No action credit is assigned. Passing components and unchanged partial scalar are not whole-task qualification or downstream eligibility.

## Revision 2026-10-12 (shard 2 eval validation, second pass)

low-task-* checks use per_candidate (task subject matching shared text was undecidable). Replayed on the Luna episode with the step-credit reader. draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `14a7d95398176be3fc1d81fadfc51602b438a04c525106e9a7ba02a0166662e8`.

Edits in this review:
- removed hc_u14 goals (earliest event 2026-01-31 is within 7 days of 2026-02-07 so recently-onboarded exclusion applies; official assertions agree); added 3 harm guards (alert email/SF task to non-low or exempt customers; usage tag on recently onboarded)

Luna replay (step-credit reader): 11 of 21 decided required findings met; failing goal checks: low-email-hc_u02, low-email-hc_u04, low-email-hc_u11, low-email-hc_u12, low-email-hc_u13, tag-hc_u01, tag-hc_u03, tag-hc_u05, tag-hc_u08, tag-hc_u09; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

hc_u14 goals removed (earliest event 2026-01-31 is within 7 days of 2026-02-07, so excluded). Luna tagged only low-usage and omitted counts in the emails: real misses.
