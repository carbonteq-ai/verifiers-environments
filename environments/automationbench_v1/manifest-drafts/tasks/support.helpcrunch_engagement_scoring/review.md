# support.helpcrunch_engagement_scoring — batch-12 review v3

Pack `batch-03.json` task 0; Luna episode `c5168848…ed8f`. Whole task: **not qualified**.

**Coverage.** 15 obligations (v2's 14 plus H3b split out of H3), 11 task-specific. Expressed v1 4 → v2 4 →
v3 5. Gaps: 5 `other:per_member_child_aggregation` (H1 scores, H2c correct tier, H3 which customers get
events, H4b disengaged names, H5b dashboard rows), 1 `other:public_policy_ambiguity` (H4c amounts). Out of
scope 4.

**What v3 adds:** `change-event-uses-configured-name`: the change event must carry the ws_config
Engagement_Event value (engagement-assessed), read through a decided lookup.

**Luna replay**: alert 1, dashboard 1, change event 1, named event 1, tier tag present 8×1 and 3×0 (noise
customers untagged), no conflicting tags 11×1. Bindings verified, no errors, scalars and bytes unchanged,
rescore/reload repeated.

**Alternatives** (10 runs): v2 defects D1/D2 are fixed, so no alert, a wrong address and no change event are
now known 0 (v2: abstain). An event named 'tier-change' is a known 0 on the new check. Wrong tiers still
pass. Missing ACK abstains.

**What is still missing for per-customer scoring.** Mechanisms 6–8 do not help. Needed:
1. an aggregate evaluated per candidate over a child list of its record (`customers[].events`); today one
   aggregate is computed per check over a top-level population;
2. a per-child lookup of `event_name` into ws_scoring Points inside the aggregate value;
3. score = sum(points) + sum(points within 7 days), so no conditional operator is needed;
4. the total readable in `required_when`/selections, so the existing range selection over ws_tiers can
   publish the tier tag (works today on literals, `range_probe.py`);
5. for H2c, aggregates/selections in `records.retained_when@1`, or judging tags through update effects.

**Defects:** none new.
