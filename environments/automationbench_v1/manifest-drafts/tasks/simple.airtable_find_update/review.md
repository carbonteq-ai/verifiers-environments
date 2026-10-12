# simple.airtable_find_update

Component-only public contract. Whole-task status: **not qualified**. Original recorded reference score: 1.0 (recorded_full_score); this is preserved, not used to set the requirements.

Coverage: 1 expressible action components, 2 public obligations unavailable, 2 out of scope. Draft SHA-256: `afbcbb878cd5d92b93cb34f25a4eaa1a2cf1decf540064492c22f37e758ba773`.

## Replay

- `vip-create-action`: valid=1.0 (obligation_witnessed_required_effect); original scalar unchanged, reload snapshot and rescore matched.

## Limits

- Airtable and Asana action-log witnesses are not persisted external record/task outcomes.
- Jira INFRA create is blocked by the public initial environment lacking that project; no project or successful issue was fabricated.
- The control reward-map equality uses empty-assertion component fixtures; it is not benchmark-score parity. The actual retained native replay separately preserves its original reward map.
- These are component manifests only; training eligibility/action credit/whole-task qualification are not granted.

Native/control module fingerprints stayed unchanged during the final run (`ad19a666ff603276197cecb0bec58f061ae941d6cb305a39e90f08ae11b8c2ae` snapshot). Raw controls, dispatch/return envelopes, ACKs and scored WireEpisode links: `/tmp/automationbench-luna-simple-b11-20261005/controls/simple.airtable_find_update.json`.

## Round 2 review (reviewer A)

Verdict: ready. Goal comparisons on possibly absent effect fields are now guarded by `present` (omitted field = decided miss, not an abstention). Cause of the baseline binding mismatch: draft bound the whole prompt (system message includes the turn budget), not data drift; initial state hash is identical. Rewrote via replay.py --write-rebound after replacing the unused/unstated existing_record_id field (now copied from the seeded findRecord record). Added harm `existing-contact-overwritten`. Luna replay: 1/1 goal, no harm; no-op: 0 goals, 0 harms; binding None at 14 and 16. Controls: update of rec_001 fires the harm, update of another row does not; Status=Active / wrong table leave the goal unmet. Gap: the find step is not expressible as a goal.
