# marketing.engagement_optimization — partial component review

Reference score retained: 0.0; original outcome remains unsolved.
Current draft SHA-256: `071cd84d1abc94a0a529daee8b67b3c52443711c633e48b5ae2a1589b7e5f3ad`
Source episode SHA-256: `69e45ec95e02573ebeee15a1652bb7a0cacdae68c7fa01cbffa505b173ae89d0`
Public pack SHA-256: `46a9cc5f0f6e669ea4ed3fa38726fa8d99ce3c9f14d0b40caab03b185f1f5ba8`

Native replay: exact public prompt/state retained; same-trace rescore and scored serialize/reload/fresh rescore agree; original score/episode bytes unchanged; 0 assessment/credit errors.
Real-handler controls: correct, alternative, harmful, missing_ack; independent ordinary reward maps equal manifest reward maps for every recorded scenario.
Checks authored: 3; qualification: not granted.

Remaining documented gaps: engagement-lift-percentage-point-field, top-slot-quantity-per-platform, excluded-item-notification-silence.

## Round 2 (reviewer C)

- Verdict: ready (luna-agreement); Luna partial credit 0.0; draft changed vs. last commit: True.
- Restricted the best-slot schedule and Slack-notify goals to the two core platforms LinkedIn and Twitter (the draft also demanded LinkedIn Live, Twitter Spaces and LinkedIn Newsletter rows, which the official says are different platforms and must not appear in the schedule) and added harm no-schedule-for-variant-platforms; the schedule goal now also requires a non-empty engagement_lift. Kept the harm for scheduling the paid-boost, 2024-pilot, on-hold-legal and anomaly-week observations. Bindings also rewritten (user-message rebinding / unused system binding dropped / stale hash refreshed).
- Luna replay: 0/2 required goal instances met, harms none; no-op control: goals met 0, harms 0; the draft binds at 14 and 16 turns.
- Synthetic positive control (real handlers): goals 4/4, official fraction 0.833, harms fired none.
- Draft SHA-256 refreshed to `7f32c11760b7ed9ae7a5e39332d48221b5aab849b8f87375979a296a63102ea2`.
