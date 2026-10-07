# support.zendesk_sf_case_sync Luna partial manifest review

Luna official outcome: **official_partial**, score **0.812500**. The score is retained as recorded; it is not replaced by this draft's findings.

Coverage: **2/6** expressible task obligations; 4 gaps, 1 out of scope. Status: **not_qualified**.

Native replay: errors=0, rescore_equal=True, reload_equal=True, scalar_unchanged=True, episode_bytes_unchanged=True. Findings: salesforce-case=valid:1.0, salesforce.case=valid:1.0, salesforce.case.coverage=valid:1.0, sync-summary=valid:1.0, sync.summary=valid:1.0, sync.summary.coverage=valid:1.0.

Original Luna assertion misses (inspection aid only; not used to define checks): salesforce_case_exists, salesforce_case_exists, salesforce_collection_count_equals.


Synthetic simulator alternatives used genuine local handlers over the exact retained `task.data.initial_state` and returned tool arguments. They are focused tests of the expressed checks, not new model responses or whole-task qualifications.

- **correct** via `salesforce_case_create` (operation 26): salesforce-case: values=[1.0], statuses={'valid': 2}; sync-summary: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **harm** via `salesforce_case_create` (operation 26): salesforce-case: values=[1.0], statuses={'valid': 2}; sync-summary: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **missing_ack** via `salesforce_case_create` (operation 26): salesforce-case: values=[1.0], statuses={'valid': 2}; sync-summary: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **gaming** via `salesforce_case_create` (operation 26): salesforce-case: values=[1.0], statuses={'valid': 2}; sync-summary: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **duplicate** via `salesforce_case_create` (operation 26): salesforce-case: values=[1.0], statuses={'valid': 2}; sync-summary: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.

