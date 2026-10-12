# marketing.newsletter_unsubscribe_processing — partial component review

Original recorded score: 0.0; reference failure: `assertions_not_fully_satisfied`. The original reward/outcome remain unchanged.

Draft SHA-256: `20dd259428f4c9bcbd2947910409d8af92291d4bef7226fd41665f7e83bab37b`. Public pack SHA-256: `b65b1288a974979b5cc7228e6369dfc9801f2daf51f8605e68981d70cf7fc879`. Public prompt and initial state match the pack exactly.
Native replay: same-trace rescore and newly-scored serialize/reload/rescore both match; benchmark scalar and source bytes unchanged; no assessment/credit errors.
Genuine handler controls: 4 scenarios, each with ordinary/manifest reward-map equality and unchanged benchmark scalar. See `/tmp/automationbench-luna-marketing-batch07-20261005/marketing_newsletter_unsubscribe_processing_controls.json`; scenario outcomes remain component evidence. Each action record includes handler, exact arguments, result, dispatch/return receipt digests and any write ACK.

Expressed components: only-retracted-and-already-complete-excluded, do-not-follow-manager-keep-product-list.
Remaining public gaps: honor-compliance-across-all-lists, confirmation-and-log.

Whole task status: not qualified.

Validation source module fingerprint: `b010f8e273a8d3cc352245cfe92e1f2aea0a1688f6355f944c34c9bdc7c482fd` before and `b010f8e273a8d3cc352245cfe92e1f2aea0a1688f6355f944c34c9bdc7c482fd` after; identical across 775 Python files.

## Round-2 review D (ready)

Draft SHA-256 now `461e9c5e8344be5e708177a544034bb45c12d47c9cb16867c1d8614dee077161`. Draft had one goal (archived on any list) and one harm. Replaced by per-eligible-request goals: archived from list_newsletter, archived from list_product (via lookup on subscribers keyed email+list, so only requesters on the product list are required, matching the manager-vs-legal conflict resolved by the Slack compliance policy), confirmation email to the requester, compliance-log row in ss_log; added harms for email and log row on the retracted request alongside the existing archive harm. Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Luna replay: req 11 met 0, harms 0, noop clean; bindall []. Positive control (read sheet, 5 archives, 3 emails, 3 log rows) meets all four goals (3/2/3/3), no harm, benchmark 1.0. New source sub_by_list (key email+list_id) added for the lookup. Note: my draft backups are in d/h/orig.
