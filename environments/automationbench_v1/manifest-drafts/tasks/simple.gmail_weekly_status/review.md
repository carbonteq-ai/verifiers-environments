# simple.gmail_weekly_status — batch16 review

Checks exact recipient/subject and same-line customer-onboarding-dashboard/80% progress. The Salesforce completion statement and next-week plan are out of scope, so this is only a partial task check.

**Source and outcome.** Original recorded reward: `[{'name': 'partial_credit', 'score': 1.0, 'weight': 1.0}]`; episode `de551a15fea74c793682423c21ac78c5c7e562703275862c599deceeb955c97e` remains at SHA-256 `40dd7004dfde816ba2ecd0e9f9ef6434e26c7730ba1fe971b4d879913f818796`. The full public prompt and initial snapshot match the retained episode and pack. Current draft SHA-256: `a0b974f2037777b744ecba8264ee45b71b62b247ee3c857fd834cc9eb8f41d18`; public source-context SHA-256: `44bdf96db078350e453c3031a2edc21b6e80969ed3d745d200e8e65a34aa9274`. The retained native replay, serialized archive and reload/rescore preserve `partial_credit=1.0`; checks are outcome-only and no action credit or qualification is granted.

**Declared coverage.** Expressed checks: `requested_subject_delivered`, `dashboard_included`, `dashboard_progress_pair`, `wrong_recipient`. Coverage is partial where semantic or source-capture gaps are listed in `review.json`.

**Validation.** Native schema admission passed. Retained episode score, candidate findings and reload/rescore were recorded at [`/tmp/automationbench-luna-simple-batch16-20261005/archives/simple.gmail_weekly_status.json`](/tmp/automationbench-luna-simple-batch16-20261005/archives/simple.gmail_weekly_status.json); archive SHA-256 `abdd1647cacf4e094b168dac0bd6d74352fe4f929494e46e697eb587af21c267`. Four genuine-handler controls (positive, omission, missing ACK and wrong entity) include actual reward maps, raw dispatch/return receipts, ACK materials and full task context under `/tmp/automationbench-luna-simple-batch16-20261005/controls`; scored wire episodes are separately saved under `/tmp/automationbench-luna-simple-batch16-20261005/controls/scored_archives` with per-archive SHA-256 values in `review.json`. All control/reload findings and reward maps matched; source inventory was stable (`59a23c931845d6021e6253315a79ff779ce8215f3635264546b3b6dcd4d425b9`).

**Known limits.** No action credit, training eligibility or whole-task qualification. The completed Salesforce integration and next-week QA/bug-fix plan are status-summary statements whose paraphrased/negated meaning needs semantic review; exact 80% dashboard progress is checked.

## Round 2 review (reviewer A)

Verdict: ready.

Changes: Rewritten bound to the user message (replay.py --write-rebound) so it binds at 14 and 16 turn budgets; every goal comparison on a possibly absent effect field is now guarded by `present` so an omitted field is a decided miss instead of an abstention (abstained goals drop out of the training denominator: a call that omits the field would have scored 0/0). Added goals send-salesforce-integration (API integration + Salesforce) and send-next-week-focus (QA testing + bug fixes), the two prompt-stated updates that had no goal. Wrong-recipient harm no longer requires the exact subject.

Evidence: Luna full pass (official 1.0): every counted goal met, no harm; no-op: 0 goals met, 0 harms; binding None at turn budgets 14 and 16; no assessment or credit errors. Synthetic controls (one-field-wrong, omitted-field, wrong-target, missing call) are in round2/a/simple/controls.json: every goal control leaves the targeted goal unmet and every guard control fires its harm (non-violating variants do not fire it).

Official-assertion differences: Official assertion needs Salesforce + 'onboarding dashboard'; goals add subject, 80%, QA testing/bug fixes (prompt-stated).
