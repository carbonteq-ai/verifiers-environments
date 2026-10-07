# support.hiver_workload_forecast Luna partial manifest review

Luna official outcome: **official_partial**, score **0.933333**. The score is retained as recorded; it is not replaced by this draft's findings.

Coverage: **2/4** expressible task obligations; 2 gaps, 1 out of scope. Status: **not_qualified**.

Native replay: errors=0, rescore_equal=True, reload_equal=True, scalar_unchanged=True, episode_bytes_unchanged=True. Findings: forecast-alice-row=valid:1.0, forecast.alice.row=valid:1.0, forecast.alice.row.coverage=valid:1.0, overload-alert=valid:1.0, overload.alert=valid:1.0, overload.alert.coverage=valid:1.0.

Original Luna assertion misses (inspection aid only; not used to define checks): gmail_message_sent_to.


Synthetic simulator alternatives used genuine local handlers over the exact retained `task.data.initial_state` and returned tool arguments. They are focused tests of the expressed checks, not new model responses or whole-task qualifications.

- **correct** via `google_sheets_add_row` (operation 4): forecast-alice-row: values=[1.0], statuses={'valid': 2}; overload-alert: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **harm** via `google_sheets_add_row` (operation 4): forecast-alice-row: values=[0.0], statuses={'valid': 2}; overload-alert: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **missing_ack** via `google_sheets_add_row` (operation 4): forecast-alice-row: values=none, statuses={'abstained': 2}; overload-alert: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **gaming** via `google_sheets_add_row` (operation 4): forecast-alice-row: values=[0.0], statuses={'valid': 2}; overload-alert: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **duplicate** via `google_sheets_add_row` (operation 4): forecast-alice-row: values=[1.0], statuses={'valid': 2}; overload-alert: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.

