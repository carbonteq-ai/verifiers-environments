# simple.email_hs_create_contact_inbound — batch 13 review

Public replay: 83d45570f55aabf6c650d0fdded77ac1357d2ebf1eb0d8b5ba8e36e2e7a829d7  
Draft: 85016ef6e1a6c0722327d54fd6944c2c718f07fcd3f5ff662f966ed9d942cf64

Coverage: 2 expressed, 0 gaps, 2 out of scope. Whole-task status: **not qualified**.

Native replay matched the exact public prompt and initial state. Original assertions were retained for ordinary AutomationBench scoring. Ordinary, manifest and reload reward maps matched; scalar rewards were unchanged, reload evidence matched, and there were no scorer errors. See the linked native JSON for numeric maps, per-check findings and module fingerprints.

Three authentic-handler component scenarios (positive, candidate mismatch, and missing ACK) are saved under the scratch controls directory. They use real simulator handlers and native receipt envelopes with empty assertions, so this is component evidence only. The raw input, dispatch/return material, ACK array, and per-run findings are linked in review.json.

- **out_of_scope — constraint:** system_no_questions — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **out_of_scope — constraint:** system_only_acted_items — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **expressed — goal:** read-inbound-email — Find the email from Liam Foster
- **expressed — goal:** create-hubspot-contact — Checks sender email, first/last name, company, job title and phone on actual contact-create evidence.

No action-credit policy is declared. The public request, destination identity, retained-state limits and semantic report gaps are kept separate from the component findings.
