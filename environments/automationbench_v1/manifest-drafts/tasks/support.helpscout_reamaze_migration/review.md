# support.helpscout_reamaze_migration — round 6

Public pack `batch-10.json` task 7. Luna episode sha256 `c40d961f…`. Whole task: **qualified candidate** (10 / 10 in-scope expressed; 0 gap; 3 out of scope).

**Draft** (10 checks). Population: HelpScout conversations; customers, status map and category map are lookups.
- Goals per active conversation (mig_hs1, mig_hs2, mig_hs3, mig_hs8): Re:amaze conversation with the subject and customer email (not deleted later), mapped status, mapped category (default general), customer message verbatim, internal 'migrated' note joined to the migration, and a #migration-status post naming the subject or customer, joined to the migration.
- Guards: closed/spam migrated, closed/spam marked migrated, double migration, closed/spam subjects in the post.

**Luna replay.** No errors; scalars and episode bytes unchanged; rescore and reload repeat (round-6 engine). Luna migrated mig_hs1-3 correctly (all goals 1) but missed the active mig_hs8, so its six goals are 0; its post names Raj Mehta, which no longer credits mig_hs8 because naming is joined to the migration. Luna also migrated the two pending conversations under the wrong customers (Yuki, Raj instead of Sam Johnson, Lily Chen); pending is neutral, so this is not scored. No guard fires.

**Simulator runs.** Correct (with or without pending): every goal 1, no guard. Harmful: all four guards fire; hs8 under the wrong customer scores 0 on customer/status/category. Missing ACK on the first create: every migration check abstains (a missed write could have been a delete). Notes and post without migration: 0. Public replies instead of notes: note check 0.

**Known gaming (2).** Customer name covers several conversations; only the first thread is checked (all public conversations have one).
