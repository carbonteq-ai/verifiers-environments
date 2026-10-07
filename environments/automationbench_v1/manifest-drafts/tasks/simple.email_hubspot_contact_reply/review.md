# simple.email_hubspot_contact_reply — batch 13 review

Public replay: 6d7272e58653a3da72b784283cef7536a6db579fc4381fd543f1fcdfc4757994  
Draft: 824c07547a8668da5808729a4624f03ced973b528687704b48971789c03ea66e

Coverage: 3 expressed, 1 gaps, 2 out of scope. Whole-task status: **not qualified**.

Native replay matched the exact public prompt and initial state. Original assertions were retained for ordinary AutomationBench scoring. Ordinary, manifest and reload reward maps matched; scalar rewards were unchanged, reload evidence matched, and there were no scorer errors. See the linked native JSON for numeric maps, per-check findings and module fingerprints.

Three authentic-handler component scenarios (positive, candidate mismatch, and missing ACK) are saved under the scratch controls directory. They use real simulator handlers and native receipt envelopes with empty assertions, so this is component evidence only. The raw input, dispatch/return material, ACK array, and per-run findings are linked in review.json.

- **out_of_scope — constraint:** system_no_questions — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **out_of_scope — constraint:** system_only_acted_items — Shared environment system-prompt policy; explicitly out of scope for qualification.
- **expressed — goal:** read-sales-inquiry — Read the email
- **expressed — goal:** create-sender-contact — create a new HubSpot contact for the sender
- **expressed — goal:** send-reply-to-sender — send a reply
- **gap — report:** thank-the-sender — Current send evidence binds only recipient and earlier read, not gratitude in the new body. In `src/automationbench_v1/contracts/predicates.py`, `Mentions` does not prove positive gratitude (negated mentions still match); add a deterministic semantic gratitude check or keep this meaning unavailable.

No action-credit policy is declared. The public request, destination identity, retained-state limits and semantic report gaps are kept separate from the component findings.
