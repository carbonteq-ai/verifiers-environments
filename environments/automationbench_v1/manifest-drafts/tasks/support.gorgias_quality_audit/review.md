# support.gorgias_quality_audit Luna partial manifest review

Luna official outcome: **official_partial**, score **0.888889**. The score is retained as recorded; it is not replaced by this draft's findings.

Coverage: **2/4** expressible task obligations; 2 gaps, 2 out of scope. Status: **not_qualified**.

Native replay: errors=0, rescore_equal=True, reload_equal=True, scalar_unchanged=True, episode_bytes_unchanged=True. Findings: full-scorecard-post=valid:1.0, full.scorecard.post=valid:1.0, full.scorecard.post.coverage=valid:1.0, individual-score-log=valid:1.0, individual.score.log=valid:1.0, individual.score.log.coverage=valid:1.0.

Original Luna assertion misses (inspection aid only; not used to define checks): gorgias_ticket_exists_with_subject, gorgias_ticket_exists_with_subject.


Synthetic simulator alternatives used genuine local handlers over the exact retained `task.data.initial_state` and returned tool arguments. They are focused tests of the expressed checks, not new model responses or whole-task qualifications.

- **correct** via `google_sheets_append_row` (operation 2): individual-score-log: values=[1.0], statuses={'valid': 2}; full-scorecard-post: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **harm** via `google_sheets_append_row` (operation 2): individual-score-log: values=[1.0], statuses={'valid': 2}; full-scorecard-post: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **missing_ack** via `google_sheets_append_row` (operation 2): individual-score-log: values=[1.0], statuses={'valid': 2}; full-scorecard-post: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **gaming** via `google_sheets_append_row` (operation 2): individual-score-log: values=[1.0], statuses={'valid': 2}; full-scorecard-post: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **duplicate** via `google_sheets_append_row` (operation 2): individual-score-log: values=[1.0], statuses={'valid': 2}; full-scorecard-post: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.

