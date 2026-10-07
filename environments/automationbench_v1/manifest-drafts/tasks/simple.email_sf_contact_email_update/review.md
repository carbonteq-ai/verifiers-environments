# simple.email_sf_contact_email_update — batch 13 review

Public replay: 9d0a7ad4ebd22cdc5afa5e194d4df4428b6372c392c6689b666bba28ab6f28f5  
Draft: 7131845fb68e060735668d78829d5db5a326ea29768c590b36b89551451e3e86

Coverage: 3 expressed, 0 gaps, 2 out of scope. Whole-task status: **not qualified**.

Native replay matched the exact public prompt and initial state. Original assertions were retained for ordinary AutomationBench scoring. Ordinary, manifest and reload reward maps matched; scalar rewards were unchanged, reload evidence matched, and there were no scorer errors. See the linked native JSON for numeric maps, per-check findings and module fingerprints.

Three authentic-handler component scenarios (positive, candidate mismatch, and missing ACK) are saved under the scratch controls directory. They use real simulator handlers and native receipt envelopes with empty assertions, so this is component evidence only. The raw input, dispatch/return material, ACK array, and per-run findings are linked in review.json.

- **out_of_scope — constraint:** system_no_questions — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **out_of_scope — constraint:** system_only_acted_items — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **expressed — goal:** find-maria-email — Find her email
- **expressed — goal:** update-maria-email — Binds the public initial Contact 003002 and old email to the requested new email address and prior returned read.
- **expressed — guard:** leave-other-contacts-alone — update her contact

No action-credit policy is declared. The public request, destination identity, retained-state limits and semantic report gaps are kept separate from the component findings.
