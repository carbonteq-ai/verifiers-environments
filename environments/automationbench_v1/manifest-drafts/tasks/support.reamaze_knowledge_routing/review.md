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
