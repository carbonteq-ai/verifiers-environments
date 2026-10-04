# support.zendesk_intercom_company_sync Luna partial manifest review

Luna official outcome: **official_partial**, score **0.900000**. The score is retained as recorded; it is not replaced by this draft's findings.

Coverage: **2/4** expressible task obligations; 2 gaps, 1 out of scope. Status: **not_qualified**.

Native replay: errors=0, rescore_equal=True, reload_equal=True, scalar_unchanged=True, episode_bytes_unchanged=True. Findings: company-sync=valid:1.0, company.sync=valid:1.0, company.sync.coverage=valid:1.0, sync-recap=valid:1.0, sync.recap=valid:1.0, sync.recap.coverage=valid:1.0.

Original Luna assertion misses (inspection aid only; not used to define checks): intercom_company_exists, intercom_company_exists.


Synthetic simulator alternatives used genuine local handlers over the exact retained `task.data.initial_state` and returned tool arguments. They are focused tests of the expressed checks, not new model responses or whole-task qualifications.

- **correct** via `intercom_tag_company` (operation 3): company-sync: values=[1.0], statuses={'valid': 2}; sync-recap: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **harm** via `intercom_tag_company` (operation 3): company-sync: values=[1.0], statuses={'valid': 2}; sync-recap: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **missing_ack** via `intercom_tag_company` (operation 3): company-sync: values=[1.0], statuses={'valid': 2}; sync-recap: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **gaming** via `intercom_tag_company` (operation 3): company-sync: values=[1.0], statuses={'valid': 2}; sync-recap: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **duplicate** via `intercom_tag_company` (operation 3): company-sync: values=[1.0], statuses={'valid': 2}; sync-recap: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.

