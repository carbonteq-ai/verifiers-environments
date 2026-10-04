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

Snapshot 2026-10-04 (rounds 4–5): 45 of the 105-task sample drafted (finance 5, hr 5, marketing 8, operations 6, sales 7, simple 7, support 7); 454 of 468 in-scope obligations expressed (132 out of scope). 36 tasks at full coverage, 5 of them installed after independent qualification review (`tests/test_qualified_manifests.py`); 44 at 80% or more.

Gaming. A random spot-check of 3 unreviewed full-coverage drafts found 11 of 14 attempts succeeded (`tasks/<task>/spot-check.md`), mostly hedging (several candidate values on one line) or harm guards limited to one channel or name. After engine round 4, `sole: true` was swept onto goal amount checks, each change kept only if the Luna replay did not get worse: 29 of 39 checks kept it. The 10 reverted checks legitimately put two amounts on one line. Guard `alternatives` (mechanism 22) is available but not yet applied to the drafts. Treat an unreviewed full-coverage draft as gameable until it has been reviewed. `known_gaming` in each review.json lists the gaming paths authors recorded but did not close.

Jira task data. The HelpScout triage task named Jira project SUP but declared no projects, so with strict project validation no agent could create the issues it requires. Like the earlier Gorgias FIN repair, it was fixed in the AutomationBench fork, which now declares SUP; the vendored copy is byte-identical. Old Luna episodes still carry the pre-repair starting state, so simulator runs seeded from those episodes cannot create Jira issues in these two tasks. Seed Jira alternatives from the current task data.

| Task | Expressed / in scope | Gaps | Status | Notes |
|---|---|---:|---|---|
| `finance.deferred_revenue_tracking` | 13 / 13 | 0 | qualified candidate | spot-checked |
| `finance.escrow_tracking` | 8 / 8 | 0 | installed (qualified) |  |
| `finance.expense_split_allocation` | 16 / 16 | 0 | qualified candidate |  |
| `finance.monthend_journal_entries` | 10 / 10 | 0 | qualified candidate | spot-checked |
| `finance.payment_reconciliation` | 14 / 14 | 0 | qualified candidate |  |
| `hr.airtable_learning_path_assignment` | 9 / 9 | 0 | installed (qualified) |  |
| `hr.benefits_open_enrollment_processing` | 12 / 12 | 0 | qualified candidate |  |
| `hr.break_schedule_processing` | 12 / 12 | 0 | qualified candidate |  |
| `hr.buddy_assignment` | 13 / 13 | 0 | qualified candidate |  |
| `hr.exit_interview_scheduling` | 8 / 9 | 1 | not qualified |  |
| `marketing.ad_platform_audit` | 17 / 17 | 0 | qualified candidate | spot-checked |
| `marketing.brand_mention_analysis` | 11 / 11 | 0 | qualified candidate | 1 known gaming |
| `marketing.content_repurpose` | 22 / 22 | 0 | qualified candidate |  |
| `marketing.editorial_calendar` | 13 / 14 | 1 | not qualified |  |
| `marketing.email_blast_suppression` | 12 / 13 | 1 | not qualified | 1 known gaming |
| `marketing.lead_enrichment` | 13 / 13 | 0 | qualified candidate | 1 known gaming |
| `marketing.newsletter_sponsor_invoicing` | 14 / 14 | 0 | qualified candidate | 1 known gaming |
| `marketing.social_content_calendar` | 15 / 15 | 0 | qualified candidate |  |
| `operations.calendly_equipment_inspection` | 11 / 11 | 0 | installed (qualified) |  |
| `operations.chatgpt_feedback_analysis` | 7 / 7 | 0 | not qualified |  |
| `operations.docusign_contractor_offboard` | 12 / 12 | 0 | qualified candidate |  |
| `operations.fleet_vehicle_maintenance` | 10 / 10 | 0 | qualified candidate |  |
| `operations.trello_vendor_hold_email` | 10 / 10 | 0 | qualified candidate |  |
| `operations.zoom_training_setup` | 13 / 13 | 0 | installed (qualified) |  |
| `sales.calendly_no_show_followup` | 8 / 8 | 0 | qualified candidate |  |
| `sales.create_contact_for_account` | 7 / 7 | 0 | qualified candidate | 1 known gaming |
| `sales.deal_escalation` | 8 / 8 | 0 | qualified candidate | 2 known gaming |
| `sales.docusign_void_resend` | 7 / 7 | 0 | qualified candidate | 2 known gaming |
| `sales.multi_hop_lookup` | 6 / 6 | 0 | qualified candidate | 1 known gaming |
| `sales.slack_channel_for_new_account` | 6 / 7 | 1 | not qualified |  |
| `sales.zoom_calendar_conflict` | 9 / 9 | 0 | qualified candidate | 1 known gaming |
| `simple.email_hs_create_contact` | 10 / 10 | 0 | qualified candidate | 1 known gaming |
| `simple.email_sf_contact_account_update` | 7 / 7 | 0 | qualified candidate | 1 known gaming |
| `simple.email_sf_contact_assistant_update` | 7 / 7 | 0 | qualified candidate | 1 known gaming |
| `simple.email_zendesk_ack_reply` | 5 / 5 | 0 | installed (qualified) |  |
| `simple.mailchimp_email_request` | 5 / 5 | 0 | qualified candidate | 1 known gaming |
| `simple.slack_dm_meeting_reminder` | 8 / 8 | 0 | qualified candidate | 1 known gaming |
| `simple.trello_urgent_support_card` | 4 / 5 | 1 | not qualified | 1 known gaming |
| `support.gorgias_inventory_routing` | 19 / 20 | 1 | not qualified |  |
| `support.gorgias_refund_processing` | 9 / 9 | 0 | qualified candidate | 1 known gaming |
| `support.helpcrunch_engagement_scoring` | 5 / 11 | 6 | not qualified |  |
| `support.helpscout_hubspot_deal_alerts` | 9 / 9 | 0 | qualified candidate | 1 known gaming |
| `support.helpscout_jira_bugs` | 7 / 8 | 1 | not qualified | 1 known gaming |
| `support.zendesk_gdpr_purge` | 7 / 8 | 1 | not qualified | 2 known gaming |
| `support.zoho_account_health` | 6 / 6 | 0 | qualified candidate | 1 known gaming |
