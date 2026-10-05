# simple.zoom_meeting_email_invite — Simple23 review

The original development reference records `[{'name': 'partial_credit', 'score': 1.0, 'weight': 1.0}]`. It remains a development observation, not a qualification decision. The draft checks only the deterministic output components listed here: meeting_created, meeting_datetime, meeting_duration, meeting_invite, wrong_host, wrong_invite_recipient.

The draft binds the assigned public prompt and initial state. Current draft SHA-256: `88d294e9442351fce97a8f779a40755b9fc3c511417c1751720625fbdfceaaad`; public input SHA-256: `1fa1fd5d75163434740d608c779c9777890df2e9e6afe0fd68506685870a424d`; retained episode SHA-256: `9a948f95d4ee9df43c9108201d5b6f5cdc78f66391297be74b63050c585f8501`. Native replay preserved the original scalar map, then serialized, reloaded and rescored the episode with identical findings.

Four genuine-handler controls ran with the full public prompt, initial state, original assertion catalog and tool list: positive, omission, wrong entity, and missing acknowledgement. Actual handler inputs/results/ACKs and separate scored archives are linked from `review.json`; ordinary, manifest and reload reward maps agree. Source inventories were unchanged.

**Remaining gaps:** timezone_source: The initial Zoom user record has no timezone setting. The check establishes civil date and wall clock only; there is no public rule to infer an instant or service timezone.

No action credit, training eligibility or whole-task qualification is granted. The system-prompt conversation rules are recorded as out of scope for deterministic task checks.
