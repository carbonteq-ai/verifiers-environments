# support.reamaze_feedback_sentiment

Original Luna reference remains **official_partial** at 0.6; this review preserves that partial evidence and does not qualify the whole task.

The draft expresses 15 of 17 reviewed obligations; unresolved gaps: mixed-sentiment, unresolved-completeness. Whole-task status: `not_qualified`.

Native replay: native replay passed; prompt-bound public initial state matched the retained episode, serialization/reload rescore findings matched, scores and episode bytes were unchanged. Finding statuses: {'inapplicable': 15, 'valid': 30}.

Four minimized public-initial component controls (correct, harmful, missing acknowledgement, false-fact exploratory) exercised genuine simulator handlers with no execution errors. They are not original-trajectory replays and do not establish complete task coverage; detailed per-check outcomes and limitations are in `review.json`.

No action credit is assigned. Passing components and unchanged partial scalar are not whole-task qualification or downstream eligibility.

## Revision 2026-10-12 (shard 2 eval validation)

tag-* goals accept sentiment_/sentiment-/sentiment: prefixed tags as well as the bare label. Replayed on the Luna episode with the step-credit reader (outcome counts in manifest-validation/shard2-results.json). draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `ed246c56afcbda3d6b11a6c0bf7fa698501589ac60716cb2462c3fac069563da`.

Edits in this review:
- negative-followup goal now accepts routing by assigning the conversation to the Followup_Email address OR emailing it (prompt only says route the concerning ones appropriately; official suite assigns); added harm guards for resolved conversations (rm_1209, rm_1210) and for routing positive ones to follow-up

Luna replay (step-credit reader): 18 of 18 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Routing accepts assignment to Followup_Email or an email to it (prompt only says route). Tag spellings accepted: sentiment_/sentiment-/sentiment: prefixes. rm_1208 (mixed) left unconstrained. Luna passes all.
