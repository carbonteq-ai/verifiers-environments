# support.zoho_desk_customer_journey Luna partial manifest review

Luna official outcome: **official_partial**, score **0.909091**. The score is retained as recorded; it is not replaced by this draft's findings.

Coverage: **2/4** expressible task obligations; 2 gaps, 2 out of scope. Status: **not_qualified**.

Native replay: errors=0, rescore_equal=True, reload_equal=True, scalar_unchanged=True, episode_bytes_unchanged=True. Findings: account-summary=valid:1.0, account.summary=valid:1.0, account.summary.coverage=valid:1.0, journey-log=valid:1.0, journey.log=valid:1.0, journey.log.coverage=valid:1.0.

Original Luna assertion misses (inspection aid only; not used to define checks): google_sheets_row_exists, gmail_message_not_sent.


Synthetic simulator alternatives used genuine local handlers over the exact retained `task.data.initial_state` and returned tool arguments. They are focused tests of the expressed checks, not new model responses or whole-task qualifications.

- **correct** via `google_sheets_add_row` (operation 2): journey-log: values=[1.0], statuses={'valid': 2}; account-summary: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **harm** via `google_sheets_add_row` (operation 2): journey-log: values=[1.0], statuses={'valid': 2}; account-summary: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **missing_ack** via `google_sheets_add_row` (operation 2): journey-log: values=[1.0], statuses={'valid': 2}; account-summary: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **gaming** via `google_sheets_add_row` (operation 2): journey-log: values=[1.0], statuses={'valid': 2}; account-summary: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **duplicate** via `google_sheets_add_row` (operation 2): journey-log: values=[1.0], statuses={'valid': 2}; account-summary: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.

