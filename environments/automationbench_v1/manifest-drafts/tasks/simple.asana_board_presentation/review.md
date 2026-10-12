# simple.asana_board_presentation

Component-only public contract. Whole-task status: **not qualified**. Original recorded reference score: 1.0 (recorded_full_score); this is preserved, not used to set the requirements.

Coverage: 1 expressible action components, 1 public obligations unavailable, 2 out of scope. Draft SHA-256: `09613ba3b5b2e7e89fef4b3f2a3c1253aebbb41f16a0d2e24fe7b6c62322c676`.

## Replay

- `board-presentation-task-create-action`: valid=1.0 (obligation_witnessed_required_effect); original scalar unchanged, reload snapshot and rescore matched.

## Limits

- Airtable and Asana action-log witnesses are not persisted external record/task outcomes.
- Jira INFRA create is blocked by the public initial environment lacking that project; no project or successful issue was fabricated.
- The control reward-map equality uses empty-assertion component fixtures; it is not benchmark-score parity. The actual retained native replay separately preserves its original reward map.
- These are component manifests only; training eligibility/action credit/whole-task qualification are not granted.

Native/control module fingerprints stayed unchanged during the final run (`ad19a666ff603276197cecb0bec58f061ae941d6cb305a39e90f08ae11b8c2ae` snapshot). Raw controls, dispatch/return envelopes, ACKs and scored WireEpisode links: `/tmp/automationbench-luna-simple-b11-20261005/controls/simple.asana_board_presentation.json`.

## Revision 2026-10-12 (shard 2 eval validation)

rebound from the whole-prompt binding to the user message (prompt[1].content); field authority moved to the initial-state evidence or an ISO date spelled out in the prompt. Replayed on the Luna episode with the step-credit reader (outcome counts in manifest-validation/shard2-results.json). draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `edada553dfb7e1c37289f090f0f11f655befb70154443bca0b2dd7caff867f75`.

Edits in this review:
- added harm guard: no duplicate creation of the same record

Luna replay (step-credit reader): 1 of 1 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Luna full pass: every required goal met, no harm; empty run meets nothing.
