# Manifest draft ledger

Status of AutomationBench whole-task manifest drafts. Installed
manifests live in `src/automationbench_v1/contracts/tasks/` (catalog:
`contracts/catalog.json`); their original drafts are kept in `legacy/` for the
tests that compare installed bytes with the reviewed draft.

Each `tasks/<task_name>/` folder holds the latest `draft.json` (a full contract
that passes `load_contract`), `review.json` (obligations, Luna replay,
alternatives, gaps) and `review.md`. Authoring rules: `AUTHORING.md`.

Scope (plan Decision Log, 2026-10-04): system-prompt communication rules and
wording/judgement checks are out of scope; in-scope = deterministic
task-specific obligations. A task is a *qualified candidate* when every
in-scope obligation is expressed and verified on the recorded Luna episode
plus genuine-simulator alternatives. Candidates still need independent review
before installation.

Snapshot 2026-10-04 (rounds 4–6): 105 of the 105-task sample drafted (finance 15, hr 15, marketing 15, operations 15, sales 15, simple 15, support 15); 917 of 945 in-scope obligations expressed (327 out of scope). 87 tasks at full coverage, 5 of them installed after independent qualification review (`tests/test_qualified_manifests.py`); 101 at 80% or more.

Round 6 drafted the remaining 60 sample tasks, with the gaming checklist built into each draft (each review.json carries `gaming_checklist` and `known_gaming`). A backport pass applying round-6 fixes to earlier drafts was stopped partway to keep the CPU light. Some earlier drafts carry partial backport edits that their review.json may not reflect yet; re-verify those before review.

Luna subset. The full Luna run over 709 development tasks fully passed 222 (simple 153, HR 17, finance 17, operations 16, sales 10, marketing 9, support 0); the mean partial-credit score was 0.56. Only 23 of these 105 sample tasks are in that subset, and none of the 5 installed tasks is. The next authoring targets the 222 Luna-passed tasks (index: rl repo `docs/research/verifiers-assessment-qualification/luna-development-review-coverage.json`).

Gaming. A random spot-check of 3 unreviewed full-coverage drafts found 11 of 14 attempts succeeded (`tasks/<task>/spot-check.md`), mostly hedging (several candidate values on one line) or harm guards limited to one channel or name. After engine round 4, `sole: true` was swept onto goal amount checks, each change kept only if the Luna replay did not get worse: 29 of 39 checks kept it. The 10 reverted checks legitimately put two amounts on one line. Guard `alternatives` (mechanism 22) is available but not yet applied to the drafts. Treat an unreviewed full-coverage draft as gameable until it has been reviewed. `known_gaming` in each review.json lists the gaming paths authors recorded but did not close.

Jira task data. The HelpScout triage task named Jira project SUP but declared no projects, so with strict project validation no agent could create the issues it requires. Like the earlier Gorgias FIN repair, it was fixed in the AutomationBench fork, which now declares SUP; the vendored copy is byte-identical. Old Luna episodes still carry the pre-repair starting state, so simulator runs seeded from those episodes cannot create Jira issues in these two tasks. Seed Jira alternatives from the current task data.

| Task | Expressed / in scope | Gaps | Status | Notes |
|---|---|---:|---|---|
| `finance.contract_billing` | 4 / 4 | 0 | qualified candidate | 1 known gaming |
| `finance.deferred_revenue_tracking` | 13 / 13 | 0 | qualified candidate | spot-checked |
| `finance.escrow_tracking` | 8 / 8 | 0 | installed (qualified) |  |
| `finance.expense_split_allocation` | 16 / 16 | 0 | qualified candidate |  |
| `finance.invoice_reconciliation` | 7 / 7 | 0 | not qualified | 1 known gaming |
| `finance.monthend_journal_entries` | 10 / 10 | 0 | qualified candidate | spot-checked |
| `finance.payment_reconciliation` | 14 / 14 | 0 | qualified candidate |  |
| `finance.payment_terms_tracking` | 7 / 7 | 0 | qualified candidate | 1 known gaming |
| `finance.po_email_logging` | 7 / 7 | 0 | not qualified |  |
| `finance.prepaid_amortization` | 8 / 8 | 0 | qualified candidate | 1 known gaming |
| `finance.qb_sales_receipt_batch` | 9 / 9 | 0 | qualified candidate | 2 known gaming |
| `finance.sales_tax_remittance` | 4 / 4 | 0 | qualified candidate | 2 known gaming |
| `finance.subscription_billing` | 8 / 8 | 0 | qualified candidate | 1 known gaming |
| `finance.wave_client_statement` | 5 / 5 | 0 | qualified candidate |  |
| `finance.xero_vendor_onboard` | 1 / 5 | 4 | not qualified | 2 known gaming |
| `hr.airtable_learning_path_assignment` | 9 / 9 | 0 | installed (qualified) |  |
| `hr.bamboohr_promotion_update` | 6 / 6 | 0 | qualified candidate | 1 known gaming |
| `hr.benefits_open_enrollment_processing` | 12 / 12 | 0 | qualified candidate |  |
| `hr.break_schedule_processing` | 12 / 12 | 0 | qualified candidate |  |
| `hr.buddy_assignment` | 13 / 13 | 0 | qualified candidate |  |
| `hr.calendly_manager_office_hours` | 10 / 10 | 0 | qualified candidate |  |
| `hr.candidate_research_dossier` | 7 / 9 | 2 | not qualified | 1 known gaming |
| `hr.docusign_nda_collection` | 9 / 9 | 0 | qualified candidate | 1 known gaming |
| `hr.equipment_provisioning` | 10 / 10 | 0 | qualified candidate | 2 known gaming |
| `hr.exit_interview_scheduling` | 8 / 9 | 1 | not qualified |  |
| `hr.intern_cohort_onboarding` | 6 / 6 | 0 | qualified candidate | 1 known gaming |
| `hr.intern_program_coordination` | 8 / 8 | 0 | qualified candidate | 2 known gaming |
| `hr.job_posting_distribution` | 7 / 7 | 0 | not qualified |  |
| `hr.trello_recruiting_event_coordination` | 3 / 4 | 1 | not qualified | 1 known gaming |
| `hr.zoom_orientation_sessions` | 8 / 8 | 0 | qualified candidate | 2 known gaming |
| `marketing.ad_platform_audit` | 17 / 17 | 0 | qualified candidate | spot-checked |
| `marketing.brand_mention_analysis` | 11 / 11 | 0 | qualified candidate | 1 known gaming |
| `marketing.content_repurpose` | 22 / 22 | 0 | qualified candidate |  |
| `marketing.conversion_tracking` | 7 / 7 | 0 | qualified candidate |  |
| `marketing.editorial_calendar` | 13 / 14 | 1 | not qualified |  |
| `marketing.email_blast_suppression` | 12 / 13 | 1 | not qualified | 1 known gaming |
| `marketing.google_ads_high_intent_list_from_hubspot` | 4 / 4 | 0 | qualified candidate |  |
| `marketing.instagram_approved_asset_publish` | 7 / 7 | 0 | qualified candidate |  |
| `marketing.lead_enrichment` | 13 / 13 | 0 | qualified candidate | 1 known gaming |
| `marketing.linkedin_speaker_outreach` | 5 / 5 | 0 | qualified candidate |  |
| `marketing.newsletter_sponsor_invoicing` | 14 / 14 | 0 | qualified candidate | 1 known gaming |
| `marketing.product_launch_channel_plan` | 15 / 15 | 0 | qualified candidate |  |
| `marketing.social_content_calendar` | 15 / 15 | 0 | qualified candidate |  |
| `marketing.social_scheduling` | 11 / 13 | 2 | not qualified | 1 known gaming |
| `marketing.twitter_influencer_followup` | 5 / 5 | 0 | qualified candidate |  |
| `operations.asana_safety_walk_log` | 11 / 11 | 0 | qualified candidate | 1 known gaming |
| `operations.calendar_airtable_gmail_maintenance_notice` | 9 / 10 | 1 | not qualified |  |
| `operations.calendly_equipment_inspection` | 11 / 11 | 0 | installed (qualified) |  |
| `operations.canva_asset_management` | 9 / 10 | 1 | not qualified |  |
| `operations.chatgpt_feedback_analysis` | 7 / 7 | 0 | qualified candidate |  |
| `operations.docusign_contractor_offboard` | 12 / 12 | 0 | qualified candidate |  |
| `operations.facility_incident_triage` | 10 / 10 | 0 | qualified candidate | 1 known gaming |
| `operations.fleet_vehicle_maintenance` | 10 / 10 | 0 | qualified candidate |  |
| `operations.hubspot_churn_prediction` | 12 / 12 | 0 | qualified candidate | 1 known gaming |
| `operations.hubspot_lead_qualification` | 14 / 14 | 0 | qualified candidate | 2 known gaming |
| `operations.linkedin_abm_outreach` | 9 / 10 | 1 | not qualified | 2 known gaming |
| `operations.mailchimp_ecommerce_sync` | 11 / 11 | 0 | qualified candidate | 1 known gaming |
| `operations.salesforce_escalated_customer` | 12 / 12 | 0 | qualified candidate |  |
| `operations.trello_vendor_hold_email` | 10 / 10 | 0 | qualified candidate |  |
| `operations.zoom_training_setup` | 13 / 13 | 0 | installed (qualified) |  |
| `sales.apply_project_label` | 7 / 7 | 0 | qualified candidate | 1 known gaming |
| `sales.calendly_no_show_followup` | 8 / 8 | 0 | qualified candidate |  |
| `sales.call_transcription` | 7 / 7 | 0 | qualified candidate | 1 known gaming |
| `sales.chatgpt_proposal_customization` | 7 / 7 | 0 | qualified candidate | 2 known gaming |
| `sales.create_contact_for_account` | 7 / 7 | 0 | qualified candidate | 1 known gaming |
| `sales.deal_escalation` | 8 / 8 | 0 | qualified candidate | 2 known gaming |
| `sales.docusign_deal_workspace` | 8 / 8 | 0 | qualified candidate |  |
| `sales.docusign_void_resend` | 7 / 7 | 0 | qualified candidate | 2 known gaming |
| `sales.event_to_opportunity_pipeline` | 6 / 7 | 1 | not qualified | 2 known gaming |
| `sales.full_sales_cycle_orchestrator` | 10 / 10 | 0 | not qualified | 2 known gaming |
| `sales.linkedin_event_promotion` | 6 / 6 | 0 | qualified candidate |  |
| `sales.multi_hop_lookup` | 6 / 6 | 0 | qualified candidate | 1 known gaming |
| `sales.sheets_multi_channel_campaign_router` | 11 / 11 | 0 | qualified candidate | 2 known gaming |
| `sales.slack_channel_for_new_account` | 6 / 7 | 1 | not qualified |  |
| `sales.zoom_calendar_conflict` | 9 / 9 | 0 | qualified candidate | 1 known gaming |
| `simple.asana_sprint_section_task` | 6 / 6 | 0 | qualified candidate | 1 known gaming |
| `simple.email_airtable_customer_welcome` | 6 / 6 | 0 | qualified candidate | 2 known gaming |
| `simple.email_hs_create_contact` | 10 / 10 | 0 | qualified candidate | 1 known gaming |
| `simple.email_sf_contact_account_update` | 7 / 7 | 0 | qualified candidate | 1 known gaming |
| `simple.email_sf_contact_assistant_update` | 7 / 7 | 0 | qualified candidate | 1 known gaming |
| `simple.email_zendesk_ack_reply` | 5 / 5 | 0 | installed (qualified) |  |
| `simple.feature_launch_slack` | 4 / 4 | 0 | qualified candidate | 1 known gaming |
| `simple.gmail_invoice_email` | 6 / 6 | 0 | qualified candidate |  |
| `simple.hs_create_deal_with_contact` | 5 / 5 | 0 | qualified candidate |  |
| `simple.jira_accessibility_audit` | 2 / 2 | 0 | not qualified |  |
| `simple.mailchimp_email_request` | 5 / 5 | 0 | qualified candidate | 1 known gaming |
| `simple.slack_dm_meeting_reminder` | 8 / 8 | 0 | qualified candidate | 1 known gaming |
| `simple.trello_urgent_support_card` | 4 / 5 | 1 | not qualified | 1 known gaming |
| `simple.zendesk_resolve_email` | 2 / 2 | 0 | qualified candidate | 1 known gaming |
| `simple.zoom_calendar_sync` | 9 / 9 | 0 | qualified candidate |  |
| `support.gorgias_inventory_routing` | 19 / 20 | 1 | not qualified |  |
| `support.gorgias_refund_processing` | 9 / 9 | 0 | qualified candidate | 1 known gaming |
| `support.helpcrunch_engagement_scoring` | 5 / 11 | 6 | not qualified |  |
| `support.helpcrunch_zoho_desk_bridge` | 7 / 7 | 0 | qualified candidate | 1 known gaming |
| `support.helpscout_hubspot_deal_alerts` | 9 / 9 | 0 | qualified candidate | 1 known gaming |
| `support.helpscout_jira_bugs` | 7 / 8 | 1 | not qualified | 1 known gaming |
| `support.helpscout_reamaze_migration` | 10 / 10 | 0 | qualified candidate | 2 known gaming |
| `support.hiver_inbox_report` | 11 / 11 | 0 | qualified candidate |  |
| `support.intercom_auto_response_drafts` | 4 / 5 | 1 | not qualified | 1 known gaming |
| `support.intercom_demo_scheduling` | 12 / 12 | 0 | qualified candidate | 1 known gaming |
| `support.reamaze_cross_platform_dedup` | 11 / 11 | 0 | qualified candidate |  |
| `support.reamaze_knowledge_routing` | 5 / 5 | 0 | qualified candidate | 1 known gaming |
| `support.zendesk_gdpr_purge` | 7 / 8 | 1 | not qualified | 2 known gaming |
| `support.zendesk_hubspot_org_sync` | 16 / 16 | 0 | qualified candidate | 3 known gaming |
| `support.zoho_account_health` | 6 / 6 | 0 | qualified candidate | 1 known gaming |
