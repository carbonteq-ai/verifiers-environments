# simple.email_sf_contact_department_update — batch 13 review

Public replay: 609a9bf3d7d1fac2fa49b80367e1a3787d54e6da4e3ce505aa6a15ef8b2eca6f  
Draft: 2922ebbfd88cbaaf6dd21ce016ec31b75982ee51a2622d2fe56ebeb187a12ea6

Coverage: 3 expressed, 0 gaps, 2 out of scope. Whole-task status: **not qualified**.

Native replay matched the exact public prompt and initial state. Original assertions were retained for ordinary AutomationBench scoring. Ordinary, manifest and reload reward maps matched; scalar rewards were unchanged, reload evidence matched, and there were no scorer errors. See the linked native JSON for numeric maps, per-check findings and module fingerprints.

Three authentic-handler component scenarios (positive, candidate mismatch, and missing ACK) are saved under the scratch controls directory. They use real simulator handlers and native receipt envelopes with empty assertions, so this is component evidence only. The raw input, dispatch/return material, ACK array, and per-run findings are linked in review.json.

- **out_of_scope — constraint:** system_no_questions — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **out_of_scope — constraint:** system_only_acted_items — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **expressed — goal:** find-amir-email — Find the email
- **expressed — goal:** update-amir-department — Binds the public initial Contact 003009, changed department field, value Product Management, and prior returned read.
- **expressed — guard:** leave-other-contacts-alone — update his department

No action-credit policy is declared. The public request, destination identity, retained-state limits and semantic report gaps are kept separate from the component findings.
