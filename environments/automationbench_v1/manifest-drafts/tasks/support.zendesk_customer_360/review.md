# support.zendesk_customer_360 Luna partial manifest review

Luna official outcome: **official_partial**, score **0.833333**. The score is retained as recorded; it is not replaced by this draft's findings.

Coverage: **3/5** expressible task obligations; 2 gaps, 1 out of scope. Status: **not_qualified**.

Native replay: errors=0, rescore_equal=True, reload_equal=True, scalar_unchanged=True, episode_bytes_unchanged=True. Findings: crm-stats=valid:1.0, crm.stats=valid:1.0, crm.stats.coverage=valid:1.0, discrepancy-report=valid:1.0, discrepancy.report=valid:1.0, discrepancy.report.coverage=valid:1.0, organization-enrichment=valid:1.0, organization.enrichment=valid:1.0, organization.enrichment.coverage=valid:1.0.

Original Luna assertion misses (inspection aid only; not used to define checks): zendesk_organization_has_tag, zendesk_organization_has_tag.


Synthetic simulator alternatives used genuine local handlers over the exact retained `task.data.initial_state` and returned tool arguments. They are focused tests of the expressed checks, not new model responses or whole-task qualifications.

- **correct** via `zendesk_update_organization` (operation 3): organization-enrichment: values=[1.0], statuses={'valid': 2}; discrepancy-report: values=[1.0], statuses={'valid': 2}; crm-stats: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **harm** via `zendesk_update_organization` (operation 3): organization-enrichment: values=[1.0], statuses={'valid': 2}; discrepancy-report: values=[1.0], statuses={'valid': 2}; crm-stats: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **missing_ack** via `zendesk_update_organization` (operation 3): organization-enrichment: values=[1.0], statuses={'valid': 2}; discrepancy-report: values=[1.0], statuses={'valid': 2}; crm-stats: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **gaming** via `zendesk_update_organization` (operation 3): organization-enrichment: values=[1.0], statuses={'valid': 2}; discrepancy-report: values=[1.0], statuses={'valid': 2}; crm-stats: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **duplicate** via `zendesk_update_organization` (operation 3): organization-enrichment: values=[1.0], statuses={'valid': 2}; discrepancy-report: values=[1.0], statuses={'valid': 2}; crm-stats: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.

