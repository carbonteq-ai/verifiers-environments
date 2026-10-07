# hr.asana_compliance_tasks: batch06 partial review

Original Luna score: 0.000000 (preserved); this is partial component evidence, not qualification.

Coverage: 5 expressed checks; 2 explicit gap(s); 2 shared system-prompt rules out of scope.

## Native replay

- No scorer errors; finding result repeats after rescore and wire reload: True/True.
- Original scalar rewards and source episode bytes unchanged: True/True.
- Findings are retained from the latest terminal assessment per run_id.

## Genuine-handler controls

- 0 scenarios; all ordinary-task vs manifest scalar reward maps equal: True; errors: 0.
- Gap: asana-task-destination (other:public_target_schema): No public Asana project/workspace target or returned task inventory is present; no task ID/destination may be invented.
- Gap: review-deadline-updates-before-create (required_read_ordering): The prompt requires reviewing all notes and recent deadline updates before creating tasks; no reliable public source/ordering witness for all updates is declared in the draft.

No whole-task qualification, action credit, or downstream eligibility is claimed.
