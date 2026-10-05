# simple.zoom_team_retro — Simple23 review

The original development reference records `[{'name': 'partial_credit', 'score': 1.0, 'weight': 1.0}]`. It remains a development observation, not a qualification decision. The draft checks only the deterministic output components listed here: meeting_created, meeting_datetime, meeting_duration, wrong_host.

The draft binds the assigned public prompt and initial state. Current draft SHA-256: `5d9a3b99393b98dedad64cca10d40b365aa1a543e165707a91677b385df6f9e0`; public input SHA-256: `1119b391b1dc6c6193b1a6babe8c9eedbf6d66fbaf6de5346a4a5b3286034cac`; retained episode SHA-256: `628bed3a7c30351ce146cbb08401708c9714735d3c94101a4c6bcb21e5b482c3`. Native replay preserved the original scalar map, then serialized, reloaded and rescored the episode with identical findings.

Four genuine-handler controls ran with the full public prompt, initial state, original assertion catalog and tool list: positive, omission, wrong entity, and missing acknowledgement. Actual handler inputs/results/ACKs and separate scored archives are linked from `review.json`; ordinary, manifest and reload reward maps agree. Source inventories were unchanged.

**Remaining gaps:** timezone_instant_interpretation: The check establishes civil date and wall-clock values only. The prompt does not say whether EST means a fixed UTC offset or the Eastern regional timezone with daylight-saving transitions; Zoom stores start_time and timezone separately. Bind a public timezone policy before claiming UTC/instant equivalence.

No action credit, training eligibility or whole-task qualification is granted. The system-prompt conversation rules are recorded as out of scope for deterministic task checks.
