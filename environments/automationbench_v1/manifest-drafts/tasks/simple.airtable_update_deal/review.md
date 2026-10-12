# simple.airtable_update_deal

Component-only public contract. Whole-task status: **not qualified**. Original recorded reference score: 1.0 (recorded_full_score); this is preserved, not used to set the requirements.

Coverage: 1 expressible action components, 2 public obligations unavailable, 2 out of scope. Draft SHA-256: `be87d56c7974b27eb59c72bd6ae16490ce3599f7dbac0ac94f05fe03cc04aed6`.

## Replay

- `won-deal-create-action`: valid=1.0 (obligation_witnessed_required_effect); original scalar unchanged, reload snapshot and rescore matched.

## Limits

- Airtable and Asana action-log witnesses are not persisted external record/task outcomes.
- Jira INFRA create is blocked by the public initial environment lacking that project; no project or successful issue was fabricated.
- The control reward-map equality uses empty-assertion component fixtures; it is not benchmark-score parity. The actual retained native replay separately preserves its original reward map.
- These are component manifests only; training eligibility/action credit/whole-task qualification are not granted.

Native/control module fingerprints stayed unchanged during the final run (`ad19a666ff603276197cecb0bec58f061ae941d6cb305a39e90f08ae11b8c2ae` snapshot). Raw controls, dispatch/return envelopes, ACKs and scored WireEpisode links: `/tmp/automationbench-luna-simple-b11-20261005/controls/simple.airtable_update_deal.json`.

## Revision 2026-10-12 (shard 2 eval validation)

rebound from the whole-prompt binding to the user message (prompt[1].content). Replayed on the Luna episode with the step-credit reader (outcome counts in manifest-validation/shard2-results.json). draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `2191048d55a1c400f4b469c7d0aeb6c7bb113f9b6e34df89455465c1cba34352`.

Edits in this review:
- added harm guard: no duplicate creation of the same record

Luna replay (step-credit reader): 1 of 1 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Luna full pass: every required goal met, no harm; empty run meets nothing.
