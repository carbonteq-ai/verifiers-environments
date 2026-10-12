# marketing.linkedin_company_update — partial component review

Original recorded score: 0.0; reference failure: `assertions_not_fully_satisfied`. The original reward/outcome remain unchanged.

Draft SHA-256: `dfa9e5d540887e52a4d9e9f0fcfdab687b4fcc4c6a81d488f8da4a80bc022eac`. Public pack SHA-256: `b65b1288a974979b5cc7228e6369dfc9801f2daf51f8605e68981d70cf7fc879`. Public prompt and initial state match the pack exactly.
Native replay: same-trace rescore and newly-scored serialize/reload/rescore both match; benchmark scalar and source bytes unchanged; no assessment/credit errors.
Genuine handler controls: 4 scenarios, each with ordinary/manifest reward-map equality and unchanged benchmark scalar. See `/tmp/automationbench-luna-marketing-batch07-20261005/marketing_linkedin_company_update_controls.json`; scenario outcomes remain component evidence. Each action record includes handler, exact arguments, result, dispatch/return receipt digests and any write ACK.

Expressed components: main-nimbus-linkedin-page, use-registration-not-presenter-link, audience-customer-support-leaders.
Remaining public gaps: current-event-details-and-content, read-current-guidelines.

Whole task status: not qualified.

Validation source module fingerprint: `b010f8e273a8d3cc352245cfe92e1f2aea0a1688f6355f944c34c9bdc7c482fd` before and `b010f8e273a8d3cc352245cfe92e1f2aea0a1688f6355f944c34c9bdc7c482fd` after; identical across 775 Python files.

## Round 2 (reviewer C)

- Verdict: ready (luna-agreement); Luna partial credit 0.0; draft changed vs. last commit: True.
- The whole-initial-state binding hash was stale after the LinkedIn schema renames (14- and 16-turn binding checks failed); re-bound to the current initial state (hash 562a5070...). Goal and harm unchanged: post on the main Nimbus page (li_nimbus) containing the event title, the registration link and 'customer support leaders', gated on reading the webinar confirmation email and the main company; harm for sharing the presenter link. Bindings also rewritten (user-message rebinding / unused system binding dropped / stale hash refreshed).
- Luna replay: 0/0 required goal instances met, harms none; no-op control: goals met 0, harms 0; the draft binds at 14 and 16 turns.
- Synthetic positive control (real handlers): goals 1/1, official fraction 1.0, harms fired none.
- Draft SHA-256 refreshed to `1f0ef06076a14e241d21f45a95a1d8bb2ef51b2e376f6cf4e6edd0bd2d52dd62`.
