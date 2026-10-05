# operations.airtable_gmail_visitor_followup — public-only review

Draft SHA-256: `6b2d91ddf2f1ca5ec7cf5eecfc99a83ac88870ec4fe55407e7110fc0e17edc5e`. Public input SHA-256: `fa8f4bcde652885baa482b5411fed5a6747c5432be85ac32c183c451e17f5532`.
Control artifact SHA-256: `20b9b8a452f4cbe313571b68234d19dfbe4235baacc2f3aeafa2585aa29076c7` (56727168 bytes); 4 fresh genuine-handler scenarios retain raw arguments, results, receipts, ACKs, and unique serialized wire files with verified hashes.

Coverage: 3 expressed components, 1 explicit gaps; no qualification or eligibility grant.

## Expressed checks and gaps

- **F1 (expressed)** Latest topical front-desk NDA message is selected; selected message is read before action. Check: `selected-nda-email-read`.
- **F2 (expressed)** Airtable visitor record receives NDA completion comment. Check: `comment-record-for-selected-visitor`.
- **F3 (expressed)** Host receives email notification with verbatim source values. Check: `host-notification-for-selected-visitor`.
- **F4 (gap)** Comment and notification must preserve source values verbatim; current checks do not fully prohibit paraphrased or extra unsupported values.

## Validation

All 4 scenarios have exact current-draft hashes, ordinary and manifest reward maps, scalar noninterference results, and verified wire-file hashes. Each serialized episode was reloaded and rescored; findings match, as do separate same-trace rescores. Source inventories are unchanged: `{'/home/hammad/projects/verifiers-credit-candidate-20261003': True, '/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1': True}`. The full raw evidence and paths are in `review.json` and the linked control artifact.

The earlier control artifact and its recorded results remain in `validation_history`. Its shared wire paths were overwritten by later runs, so original wire bytes are unavailable; current evidence uses new unique per-scenario paths. Frozen public inputs and original benchmark scores remain unchanged. No task qualification or training eligibility is claimed.
