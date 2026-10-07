# operations.hubspot_churn_prediction (round 6, ops-a)

Status: **qualified_candidate** - 12 of 12 in-scope obligations expressed, 0 gap(s), 3 out of scope.

## What the draft checks
- `excluded-contact-in-churn-workflow` (guard): migration-exclusion.
- `excluded-contact-in-churn-workflow` (guard): lifecycle-filter.
- `renewal-customer-outreach` (guard): renewal-outreach-hold.
- `high-risk-churn-watch-alert` (constraint): vip-override-high.
- `high-risk-churn-watch-alert` (goal): high-risk-alert.
- `high-risk-alert-after-config-read` (constraint): config-read-before-flagging.
- `high-risk-csm-task` (goal): high-risk-csm-task.
- `high-risk-churn-field` (goal): high-risk-field.
- `medium-risk-checkin-email` (goal): medium-risk-checkin-email.
- `medium-risk-churn-field` (goal): medium-risk-field.
- `non-high-contact-escalated` (guard): non-high-not-escalated.
- `low-risk-contact-emailed` (guard): low-risk-not-emailed.

## Evidence
- Luna replay: errors none, rescore/reload repeated True, scalars and bytes unchanged True.
- Luna non-pass checks: none.
- Simulator runs: no_config_read, correct, correct_selfcorrect_risk, harmful_migration_and_renewal, harmful_lead_flagged, gaming_shotgun_alert, gaming_risk_then_revert, wrong_tiers, wrong_channel, missing_ack_correct, inaction.

## Gaming checklist
- not_applicable: hedging, claim_without_action, duplicates; blocked: naming_every_entity, act_then_undo, wrong_channel_or_alias, visible_part_only (details in review.json gaming_notes).

## Known gaming
- churn_risk wrong -> right -> wrong (A-B-A cycle): Joins expose matched/none, not ordering among several later writes; same limitation as hr.break_schedule_processing.

## Interpretations and defects
- 'Each contact' for churn_risk = each flagged (high/medium) contact; a 'low' value on Lena is neither required nor penalised.
- Renewal hold covers customer-facing outreach only; an internal alert/CSM task/churn_risk for Marcus Tan is neither required nor penalised (ambiguous).
- 30+ days login = last_login_days_ago >= 30.
- initial.records@1 validates field paths against model attribute names but projects raw keys: HubSpotContact.lifecyclestage has validation_alias lifecycle_stage, so neither 'lifecycle_stage' (rejected) nor 'lifecyclestage' (absent in raw data) can be read. Fix: accept validation aliases (or project through the hydrated model).
- records.retained_when@1 / final.records@1 cannot read a key inside a dict field (properties.churn_risk): population_field_path_unsupported (the round-6 mapping-key projection applies to initial.records@1 only). Used record-write kept-value joins instead.
- Round-6 engine still rejects ['lifecycle_stage'] for initial.records@1 (it accepts ['properties','lifecyclestage'], which is not where the public data stores it).

## Fresh exact-draft native validation (2026-10-05)

The development episode was freshly rescored against draft SHA `e73d424f79afb46380d5879ee6362809790ab3792aab78d057a02d428f93aa5a` using the candidate Verifiers and AutomationBench source checkouts. The exact public prompt and normalized initial state bound with no mismatch. No scoring errors occurred; the original scalar reward map stayed {"partial_credit": "score=0.75 weight=1.0"}.

Rescore and serialized reload/rescore findings match. The unique complete-run finding index is [here](/tmp/automationbench-manifest-review-luna-20261005/candidate-verifiers/operations.hubspot_churn_prediction.finding-index.json) (SHA256 `b636ab584f27007b26b6af91768920e87218715a72596301ba04f59fa82485cb`); full scored wires are retained as three distinct artifacts: score 1 `/tmp/automationbench-manifest-review-luna-20261005/candidate-verifiers/operations.hubspot_churn_prediction.native-score1.full-wire.json` (SHA256 `c0f97f188759e90368dea46d5838322e39917d4569d5e01a17c4a2ed2c6ea3a7`), rescore `/tmp/automationbench-manifest-review-luna-20261005/candidate-verifiers/operations.hubspot_churn_prediction.native-score2.full-wire.json` (SHA256 `63aaa9b55547674791eab0d18529d0c768fab1efdea9b8b63b4ba0c2d83a13c4`), and reload/rescore `/tmp/automationbench-manifest-review-luna-20261005/candidate-verifiers/operations.hubspot_churn_prediction.native-reload-rescore.full-wire.json` (SHA256 `5456c8365610789c402ab4c9cfc0dcc48ccfb410fea03bace236c120e7c57960`). Counts in that index are evaluated candidate-run instances/statuses, not unique service entities.

The replay helper SHA256 is `3716926f399c95e2a6c5dfb86f613f9d808adab7003d773c3b06b19362a92318`; the post-run finding extractor SHA256 is `0ef2612ac9779dacad904efe138c30a1a303431d39a670bdef4d60a17864491a`. The first preflight attempt used installed Verifiers and is retained under `/tmp/automationbench-manifest-review-luna-20261005/first-run-installed-verifiers` as provenance drift, excluded from this result.

The environment and Verifiers source fingerprints were equal before and after the run (`80ebcf16e345e4a2ec6f96993045b139152cdbe8ed0b847b00aef62b019aa3b2`); the exact draft and episode hashes, import paths, and check-level finding counts are retained in `review.json`. Existing coverage, known limitations, and task status remain unchanged.
The historical lifecycle-alias mechanism note above is preserved. This replay uses current source; the draft still binds its lifecycle guard to the fixture-specific `cont_hs_205` identity rather than projecting `lifecycle_stage`.
