# simple.zoom_daily_standup — Simple23 review

The original development reference records `[{'name': 'partial_credit', 'score': 1.0, 'weight': 1.0}]`. It remains a development observation, not a qualification decision. The draft checks only the deterministic output components listed here: meeting_created, meeting_datetime, wrong_host.

The draft binds the assigned public prompt and initial state. Current draft SHA-256: `a5e7679aa4c8b004f17fe04ebaa37f39516dd34434b4c13792d77d10b5a7e326`; public input SHA-256: `11cc66aaa1487c5ff7deaacb44a61cff5bb45b98ae5fe357a9e856e750ace271`; retained episode SHA-256: `f62f1a402ec1b80539f4f7c6d1263fea7e2326189027e377a37cbf5589e9778c`. Native replay preserved the original scalar map, then serialized, reloaded and rescored the episode with identical findings.

Four genuine-handler controls ran with the full public prompt, initial state, original assertion catalog and tool list: positive, omission, wrong entity, and missing acknowledgement. Actual handler inputs/results/ACKs and separate scored archives are linked from `review.json`; ordinary, manifest and reload reward maps agree. Source inventories were unchanged.

**Remaining gaps:** timezone_instant_interpretation: The check establishes civil date and wall-clock values only. The prompt does not say whether EST means a fixed UTC offset or the Eastern regional timezone with daylight-saving transitions; Zoom stores start_time and timezone separately. Bind a public timezone policy before claiming UTC/instant equivalence.; weekday_recurrence: `zoom_create_meeting` has no recurrence argument and retained Zoom Meeting has no recurrence field. A single create cannot prove Monday–Friday recurrence; exact handler/model/hash repro is linked in the scratch evidence.

No action credit, training eligibility or whole-task qualification is granted. The system-prompt conversation rules are recorded as out of scope for deterministic task checks.
