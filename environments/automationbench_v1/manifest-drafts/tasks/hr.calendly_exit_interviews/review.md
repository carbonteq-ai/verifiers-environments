# hr.calendly_exit_interviews: batch06 partial review

Original Luna score: 0.000000 (preserved); this is partial component evidence, not qualification.

Coverage: 2 expressed checks; 2 explicit gap(s); 2 shared system-prompt rules out of scope.

## Native replay

- No scorer errors; finding result repeats after rescore and wire reload: True/True.
- Original scalar rewards and source episode bytes unchanged: True/True.
- Findings are retained from the latest terminal assessment per run_id.

## Genuine-handler controls

- 3 scenarios; all ordinary-task vs manifest scalar reward maps equal: True; errors: 0.
- Gap: bamboohr-departure-record-closure (other:persisted_target_state): The task asks to close BambooHR records, but the available genuine handler only logs a requested action and the captured public target has no persisted BambooHR terminal update.
- Gap: recent-hr-updates-before-email (required_read_ordering): The prompt requires checking recent HR updates; the draft binds departure notes but does not prove the relevant Gmail update inventory was reviewed before each email.

No whole-task qualification, action credit, or downstream eligibility is claimed.
