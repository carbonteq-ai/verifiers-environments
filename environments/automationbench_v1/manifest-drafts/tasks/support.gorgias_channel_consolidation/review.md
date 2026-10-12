# support.gorgias_channel_consolidation

Original Luna result remains `official_partial` with partial score `0.7272727272727273`. It is retained as an unsolved reference, not treated as the target policy answer.

This draft declares 5 expressible component checks and records 3 remaining public obligation gaps. Native replay: `{'assessment': [], 'credit': []}`; original reward scalar unchanged: `True`; episode bytes unchanged: `True`; reload/rescore finding parity: `True`. Current replay findings, including misses and abstentions, are preserved in `review.json`.

Gaps: reply-link-log, closure-coverage, summary. Synthetic tests exercise genuine handlers but remain component controls; they do not qualify the whole task. No action credit is assigned. Whole-task status: `not_qualified`.

## Revision 2026-10-12 (shard 2 eval validation, second pass)

added counted close goals per exact-email cluster (Anna 2 of 3, Marco 1 of 2, Lee 1 of 2). Replayed on the Luna episode with the step-credit reader. draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `6ff01169e64f35243f8016ad6f3cfce4e727609b27c9577a6563817bf0e817b8`.

Edits in this review:
- removed inert retained_when goal held-tickets-remain-open (true before any action; not scored); added harm guard for consolidation-log rows naming held (g_211, g_212), different-email decoy (g_205, g_207) or unrelated tickets

Luna replay (step-credit reader): 4 of 4 decided required findings met; failing goal checks: none; harms fired: held-tickets-not-closed, no-log-row-for-held-or-decoy-tickets. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Closure goals use exact occurrence bounds (Anna 2, Marco 1, Lee 1) so closing the primary or too many fails. Luna closes the two held tickets g_211/g_212 and logs them: two real harm hits. Note-linking is not scored (primary choice is free). Inert retained_when goal one-open-exact-email-cluster is not read by the step-credit reader. Inert (not scored by the step-credit reader): one-open-exact-email-cluster.
