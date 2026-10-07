# simple.email_sf_contact_city_update — batch 13 review

Public replay: 53fd40210357949d525957d3e98c1da6ef1adc1ba5adcd89a922eb7f6afded84  
Draft: 9c8112304f48e2caf4cfd25faab111109b60277101bdaba3f4795336255f6103

Coverage: 3 expressed, 0 gaps, 2 out of scope. Whole-task status: **not qualified**.

Native replay matched the exact public prompt and initial state. Original assertions were retained for ordinary AutomationBench scoring. Ordinary, manifest and reload reward maps matched; scalar rewards were unchanged, reload evidence matched, and there were no scorer errors. See the linked native JSON for numeric maps, per-check findings and module fingerprints.

Three authentic-handler component scenarios (positive, candidate mismatch, and missing ACK) are saved under the scratch controls directory. They use real simulator handlers and native receipt envelopes with empty assertions, so this is component evidence only. The raw input, dispatch/return material, ACK array, and per-run findings are linked in review.json.

- **out_of_scope — constraint:** system_no_questions — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **out_of_scope — constraint:** system_only_acted_items — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **expressed — goal:** find-lisa-email — Find the email
- **expressed — goal:** update-lisa-mailing-city — Binds the public initial Contact 003004, the changed mailing_city field, value Denver, and prior returned read.
- **expressed — guard:** leave-other-contacts-alone — update her mailing city

No action-credit policy is declared. The public request, destination identity, retained-state limits and semantic report gaps are kept separate from the component findings.
