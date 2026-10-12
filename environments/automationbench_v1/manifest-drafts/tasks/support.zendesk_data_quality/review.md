# support.zendesk_data_quality

Original Luna reference remains **official_partial** at 0.6666666666666666; this review preserves that partial evidence and does not qualify the whole task.

The draft expresses 5 of 9 reviewed obligations; unresolved gaps: missing-required-field-generic, email-report-facts. Whole-task status: `not_qualified`.

Native replay: native replay passed; prompt-bound public initial state matched the retained episode, serialization/reload rescore findings matched, scores and episode bytes were unchanged. Finding statuses: {'inapplicable': 3, 'valid': 10}.

Four minimized public-initial component controls (correct, harmful, missing acknowledgement, false-fact exploratory) exercised genuine simulator handlers with no execution errors. They are not original-trajectory replays and do not establish complete task coverage; detailed per-check outcomes and limitations are in `review.json`.

No action credit is assigned. Passing components and unchanged partial scalar are not whole-task qualification or downstream eligibility.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `434dc98fe844d82c289653f67b4595f03b3c9b9d89ecf364f3536b38f559bf1e`.

Edits in this review:
- report-counts used mode amount_reformatted, which only matches a number written differently from the source value (meant for guards), so a correct count could not satisfy it; switched to mode amount (standalone number equals 4 and 5); added harm guards for log rows and tags on compliant, exempt or solved tickets

Luna replay (step-credit reader): 11 of 11 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

report-counts used amount_reformatted (cannot match a correct count); fixed to amount. Luna passes all after the fix.
