# support.reamaze_knowledge_routing — round 6 review

Coverage: 5 of 5 in-scope obligations expressed, 0 gaps, 4 out of scope. Status: **qualified_candidate**.

Domains from the public keyword sheet; three multi-domain conversations accept any matched domain; 809/810 fall back to general.
Checks: retained expert assignment, retained domain tag without unmatched domains, KB link message; guards for unrelated links and resolving.
Luna routed and tagged all 11 correctly but never shared a KB link (it called a Help Scout tool and the episode ended), so kb-link-shared is 0 for 9 conversations.
Known gap: an internal note with the link counts as shared (see known_gaming).

## Luna replay

No errors; bindings admitted; scalar rewards and episode bytes unchanged; rescore and reload repeated. Luna: routed-to-domain-expert and tagged-with-domain 1.0 for all 11; kb-link-shared 0.0 for the 9 linked conversations (never shared).

## Gaming checklist

- hedging: blocked (tags and links exclude unmatched domains; G1, G2)
- naming_every_entity: blocked (all-links message trips no-unrelated-kb-link; G1)
- claim_without_action: not_applicable (no report/log)
- act_then_undo: blocked (assignment and tags checked on final state; G4)
- duplicates: not_applicable (repeated messages/assignments do not multiply credit)
- wrong_channel_or_alias: not_applicable (state diffs of Re:amaze whatever tool wrote them)
- visible_part_only: blocked (assignment, tag and link are separate checks)

Known gaming (not closed):
- Put the KB link in an internal note instead of a customer-visible message — service.record_writes@1 exposes the whole conversation; predicates cannot test fields of the newly appended message element (visibility). Excluding the word 'internal' from values_text would also fail a legitimate internal routing note plus customer reply.

## Revision 2026-10-12 (shard 2 eval validation, second pass)

added effect goals routed-to-domain-expert-update and tagged-with-domain-update mirroring the retained checks. Replayed on the Luna episode with the step-credit reader. draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `8275f72a6912fdc573ad0c03bc5f1e764cbc7177954f0da991856bee679db9f3`.

No edits in this review.

Luna replay (step-credit reader): 22 of 31 decided required findings met; failing goal checks: kb-link-shared; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Unchanged. Luna routes and tags correctly but sent KB links with a wrong tool: kb-link-shared fails (real). Inert (not scored by the step-credit reader): routed-to-domain-expert, tagged-with-domain.


## Round 2 review (reviewer A, small-fix item 4): inert goal removed

Removed inert goal(s): routed-to-domain-expert, tagged-with-domain (final assignee/tag on each routed conversation). It was a retained-state kind (records.retained_when / collections.counts_when), which the training step-credit reader (manifest_outcomes) never counts, so it carried no reward and no measurement.
Counted replacement: routed-to-domain-expert-update and tagged-with-domain-update (counted effects goals on the same conversations).
Evidence: Luna replay: 31 required, 22 met (unchanged; kb-link-shared fails for a wrong tool: real miss); required/met/harm counts identical before and after the removal (required 31 -> 31, met 22 -> 22, harms 0 -> 0); no-op control meets 0 goals and 0 harms; bindings clean at turn budgets 14 and 16; 0 assessment/credit errors. Sources used only by the removed goal were dropped.
