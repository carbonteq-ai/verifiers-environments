# marketing.lead_scoring — partial component review

Original recorded score: 0.0; reference failure: `assertions_not_fully_satisfied`. The original reward/outcome remain unchanged.

Draft SHA-256: `026be454cddc7dc6fa299996271a739278fd782d9692109236f67380e24af167`. Public pack SHA-256: `b65b1288a974979b5cc7228e6369dfc9801f2daf51f8605e68981d70cf7fc879`. Public prompt and initial state match the pack exactly.
Native replay: same-trace rescore and newly-scored serialize/reload/rescore both match; benchmark scalar and source bytes unchanged; no assessment/credit errors.
Genuine handler controls: 4 scenarios, each with ordinary/manifest reward-map equality and unchanged benchmark scalar. See `/tmp/automationbench-luna-marketing-batch07-20261005/marketing_lead_scoring_controls.json`; scenario outcomes remain component evidence. Each action record includes handler, exact arguments, result, dispatch/return receipt digests and any write ACK.

Expressed components: latest-scoring-criteria, do-not-adopt-unapproved-threshold-or-recipient.
Remaining public gaps: exclude-test-competitor-and-acquired-competitor, recent-activity-definition.

Whole task status: not qualified.

Validation source module fingerprint: `b010f8e273a8d3cc352245cfe92e1f2aea0a1688f6355f944c34c9bdc7c482fd` before and `b010f8e273a8d3cc352245cfe92e1f2aea0a1688f6355f944c34c9bdc7c482fd` after; identical across 775 Python files.
