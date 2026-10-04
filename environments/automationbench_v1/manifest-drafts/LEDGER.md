# Manifest draft ledger

Status of AutomationBench manifest drafts that are not yet installed. Installed
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

Snapshot 2026-10-04 (round 3): 20 tasks from the 105-task sample, 192 of 232 in-scope obligations expressed, 5 qualified candidates.

| Task | Expressed / in scope | Gaps | Status |
|---|---|---:|---|
| `finance.escrow_tracking` | 8 / 8 | 0 | qualified candidate |
| `hr.airtable_learning_path_assignment` | 9 / 9 | 0 | qualified candidate |
| `operations.calendly_equipment_inspection` | 11 / 11 | 0 | qualified candidate |
| `operations.zoom_training_setup` | 13 / 13 | 0 | qualified candidate |
| `simple.email_zendesk_ack_reply` | 5 / 5 | 0 | qualified candidate |
| `finance.deferred_revenue_tracking` | 12 / 13 | 1 | not qualified |
| `finance.expense_split_allocation` | 14 / 16 | 2 | not qualified |
| `finance.payment_reconciliation` | 12 / 14 | 2 | not qualified |
| `hr.break_schedule_processing` | 11 / 12 | 1 | not qualified |
| `hr.buddy_assignment` | 9 / 13 | 4 | not qualified |
| `hr.exit_interview_scheduling` | 7 / 9 | 2 | not qualified |
| `marketing.ad_platform_audit` | 13 / 15 | 2 | not qualified |
| `marketing.content_repurpose` | 19 / 22 | 3 | not qualified |
| `marketing.editorial_calendar` | 11 / 14 | 3 | not qualified |
| `marketing.social_content_calendar` | 14 / 15 | 1 | not qualified |
| `operations.chatgpt_feedback_analysis` | 4 / 7 | 3 | not qualified |
| `operations.trello_vendor_hold_email` | 7 / 10 | 3 | not qualified |
| `sales.calendly_no_show_followup` | 5 / 8 | 3 | not qualified |
| `sales.slack_channel_for_new_account` | 3 / 7 | 4 | not qualified |
| `support.helpcrunch_engagement_scoring` | 5 / 11 | 6 | not qualified |

History: round 1 expressed 41 obligations across the first ten tasks, round 2
84 (after mechanisms 1–5), round 3 reached the table above (mechanisms 6–8).
Mechanisms 9–16 were built after round 3 and are not yet used by these drafts.
Superseded draft versions, per-round replay tallies and notes are archived
machine-locally under the framework repo's
`.posttrain/state/verifiers-assessment-qualification/archive/batch-12/`.
