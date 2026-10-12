# support.reamaze_campaign_tracking

Original Luna reference remains **official_partial** at 0.5714285714285714; this review preserves that partial evidence and does not qualify the whole task.

The draft expresses 7 of 10 reviewed obligations; unresolved gaps: expired-campaign-exclusion, full-attribution-population, summary-facts. Whole-task status: `not_qualified`.

Native replay: native replay passed; prompt-bound public initial state matched the retained episode, serialization/reload rescore findings matched, scores and episode bytes were unchanged. Finding statuses: {'valid': 14, 'inapplicable': 6}.

Four minimized public-initial component controls (correct, harmful, missing acknowledgement, false-fact exploratory) exercised genuine simulator handlers with no execution errors. They are not original-trajectory replays and do not establish complete task coverage; detailed per-check outcomes and limitations are in `review.json`.

No action credit is assigned. Passing components and unchanged partial scalar are not whole-task qualification or downstream eligibility.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `1e4a40a4d4baae0deeb53e0062e997ae0312e94dfcb4319746353ceaf22eeb36`.

Edits in this review:
- added goal that the #marketing-ops post names the three active campaigns; added harm guards for tracking rows on non-attributable conversations (expired campaign, no keyword, keyword only incidental) and for posting expired campaigns

Luna replay (step-credit reader): 8 of 8 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Tracking rows plus campaign-name summary and harm guards. Tagging conversations with the campaign is not required (prompt names no tag action); Luna meets all draft goals.
