# simple.airtable_update_slack_notify

Component-only public contract. Whole-task status: **not qualified**. Original recorded reference score: 1.0 (recorded_full_score); this is preserved, not used to set the requirements.

Coverage: 2 expressible action components, 1 public obligations unavailable, 3 out of scope. Draft SHA-256: `1e70a550945f8bfc7606808ba1265621bb0dccd1c296481e59e40b9a14bde31c`.

## Replay

- `project-update-action`: valid=1.0 (obligation_witnessed_required_effect); original scalar unchanged, reload snapshot and rescore matched.
- `operations-channel-notification`: valid=1.0 (obligation_witnessed_required_effect); original scalar unchanged, reload snapshot and rescore matched.

## Limits

- Airtable and Asana action-log witnesses are not persisted external record/task outcomes.
- Jira INFRA create is blocked by the public initial environment lacking that project; no project or successful issue was fabricated.
- The control reward-map equality uses empty-assertion component fixtures; it is not benchmark-score parity. The actual retained native replay separately preserves its original reward map.
- These are component manifests only; training eligibility/action credit/whole-task qualification are not granted.

Native/control module fingerprints stayed unchanged during the final run (`ad19a666ff603276197cecb0bec58f061ae941d6cb305a39e90f08ae11b8c2ae` snapshot). Raw controls, dispatch/return envelopes, ACKs and scored WireEpisode links: `/tmp/automationbench-luna-simple-b11-20261005/controls/simple.airtable_update_slack_notify.json`.

## Round 2 review (reviewer A)

Verdict: ready. Goal comparisons on possibly absent effect fields are now guarded by `present` (omitted field = decided miss, not an abstention). Baseline binding mismatch = whole-prompt binding (system message carries the turn budget), not data drift; fixed by narrowing channel_id authority to the initial slack channels and rewriting via replay.py --write-rebound (binding None at 14 and 16). Added a done/completed text requirement to the notification goal and harm `wrong-project-completed`. Luna replay 2/2 goals, no harm; no-op 0/2, 0 harms. Controls: all goal one-field-wrong variants go unmet; guard fires for another row set to Completed and not for a different status.
