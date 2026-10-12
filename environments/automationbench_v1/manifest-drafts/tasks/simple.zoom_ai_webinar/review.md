# simple.zoom_ai_webinar — Simple23 review

The original development reference records `[{'name': 'partial_credit', 'score': 1.0, 'weight': 1.0}]`. It remains a development observation, not a qualification decision. The draft checks only the deterministic output components listed here: meeting_created, meeting_datetime, meeting_duration, wrong_host.

The draft binds the assigned public prompt and initial state. Current draft SHA-256: `c46405e41e95c64a65b1153f08d372f69083987b73fc85e2ea9ed89a366c1772`; public input SHA-256: `7c93de08eb23d0444b3f788e6da03a793911c8fab00627e19fde44166a03ab57`; retained episode SHA-256: `70976d1a00e620a2d28d4487282225420a7ed595877f230c82b7035cd9294904`. Native replay preserved the original scalar map, then serialized, reloaded and rescored the episode with identical findings.

Four genuine-handler controls ran with the full public prompt, initial state, original assertion catalog and tool list: positive, omission, wrong entity, and missing acknowledgement. Actual handler inputs/results/ACKs and separate scored archives are linked from `review.json`; ordinary, manifest and reload reward maps agree. Source inventories were unchanged.

**Remaining gaps:** timezone_instant_interpretation: The check establishes civil date and wall-clock values only. The prompt does not say whether EST means a fixed UTC offset or the Eastern regional timezone with daylight-saving transitions; Zoom stores start_time and timezone separately. Bind a public timezone policy before claiming UTC/instant equivalence.

No action credit, training eligibility or whole-task qualification is granted. The system-prompt conversation rules are recorded as out of scope for deterministic task checks.

## Round 2 review (reviewer A)

Verdict: ready.

Changes: Rewritten bound to the user message (replay.py --write-rebound) so it binds at 14 and 16 turn budgets; every goal comparison on a possibly absent effect field is now guarded by `present` so an omitted field is a decided miss instead of an abstention (abstained goals drop out of the training denominator: a call that omits the field would have scored 0/0). Removed the meeting type==2 requirement (Luna's mapping of 'webinar-style'; the prompt never states a type, the '2' it matched was inside '2026').

Evidence: Luna full pass (official 1.0): every counted goal met, no harm; no-op: 0 goals met, 0 harms; binding None at turn budgets 14 and 16; no assessment or credit errors. Synthetic controls (one-field-wrong, omitted-field, wrong-target, missing call) are in round2/a/simple/controls.json: every goal control leaves the targeted goal unmet and every guard control fires its harm (non-violating variants do not fire it).

Official-assertion differences: Official assertion needs only the topic; goals also require host, 1:00 PM on 2026-03-15 and 90 minutes (prompt-stated).

Notes: EST is not checked: start_time must show 2026-03-15 and 1:00 PM as written; an agent that converts to UTC would miss the datetime goal.

Gaps: Timezone handling.
