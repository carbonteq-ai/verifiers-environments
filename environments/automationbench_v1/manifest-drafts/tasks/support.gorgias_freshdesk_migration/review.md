# support.gorgias_freshdesk_migration

Reference outcome remains `official_partial` at score `0.2857142857142857`; this is partial evidence, not qualification.
Current draft SHA-256: `1b52ef9c9492a444d06abf2ed4667cf09242b91daec11023713395557a9f7ae9`. Whole-task status: `not_qualified`.
Native replay/reload: `passed`; public prompt and initial state matched; scalar rewards, episode bytes and findings were unchanged; errors: `0`.
Genuine-handler controls (correct/harm/missing-ACK) vs ordinary-task baseline: `passed`; see `review.json` and `/tmp/automationbench-luna-support-batch05-20261005/controls.json`.
Correct-control positive signals: support-gorgias_freshdesk_migration.exclude-archived-review.compliance, support-gorgias_freshdesk_migration.exclude-do-not-migrate.compliance, support-gorgias_freshdesk_migration.exclude-previous-migrated.compliance, support-gorgias_freshdesk_migration.migrate-gm_t1, support-gorgias_freshdesk_migration.migrate-gm_t1.coverage, support-gorgias_freshdesk_migration.migrate-gm_t11, support-gorgias_freshdesk_migration.migrate-gm_t11.coverage, support-gorgias_freshdesk_migration.migrate-gm_t13, support-gorgias_freshdesk_migration.migrate-gm_t13.coverage, support-gorgias_freshdesk_migration.migrate-gm_t2, support-gorgias_freshdesk_migration.migrate-gm_t2.coverage, support-gorgias_freshdesk_migration.migrate-gm_t5.
Harm-control zero-valued signals: support-gorgias_freshdesk_migration.exclude-archived-review, support-gorgias_freshdesk_migration.exclude-do-not-migrate, support-gorgias_freshdesk_migration.exclude-previous-migrated, support-gorgias_freshdesk_migration.no-legal-review-migration, support-gorgias_freshdesk_migration.no-legal-review-migration.compliance.
Unclosed public requirements retained as gaps: migration-log, full-eligibility-logic, complete-migration-policy-population.
Synthetic cases are component controls through real simulator handlers; they are not original trajectory replays.

## Round-2 review D (ready)

Draft SHA-256 now `76264062646cf33591318ae26230c15e17678d67bd917b2c0de992c7aac0b186`. The prompt requires tracking in the migration log but the draft had no log goal and its log source pointed at nonexistent ids (ss_migration_log / ws_migration_log). Fixed the source to ss_migration / ws_migration and added goal migration-log-row (a row whose Subject names each of the 8 migrated tickets) and harm no-log-row-for-excluded-ticket (t4, t10, t12, t14).

Evidence: Luna partly migrated (3 of 8 with the right priority + log + Slack): draft 12 of 17 required met; official passed the same three ticket assertions + log rows + Slack. Positive control (8 tickets with policy priorities, 8 log rows, Slack post) meets all, no harm.
