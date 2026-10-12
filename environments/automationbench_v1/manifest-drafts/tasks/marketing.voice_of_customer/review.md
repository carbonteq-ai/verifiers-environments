# marketing.voice_of_customer batch05 review

- Recorded partial scalar: 0.2692307692307692; original unsatisfied assertions remain.
- Final draft SHA-256: 61b6c09f399c4cdc718d6c6baf2b74832eedd799b0073a9aca35859de8f122d2.
- Native artifact: `/tmp/automationbench-luna-marketing-batch05-20261005/marketing_voice_of_customer_native.json`; exact source episode SHA-256: 708d0ea47ce2bb3e9956e5d36175c5e44d5a02b31abd70201f4f41bfdcdaabd0.
- Native errors: 0; source scalar/bytes unchanged: True/True.
- Same-trace rescore and scored serialize/reload/fresh-data rescore equal: True/True.
- Native assessment evidence does not grant causal action credit or whole-task qualification.
- Genuine-handler correct/alternative/harm/missing-ACK controls remain pending and are not claimed.
- Public goals, guards, constraints, reporting requirements, and unresolved gaps are enumerated in review.json.

## Native-handler controls

- A current-draft-hash-bound control artifact covers correct, permitted alternative, harmful, and missing-ACK cases using native simulator handlers.
- All four controls had zero assessment/credit errors: True; independent ordinary-scorer scalar parity: True; public prompt/initial-state transport preserved: True.
- Correct / alternative produced a positive expressed component: True / True; harmful fixture triggered an expressed guard: True.
- See review.json and the scratch artifact for per-check findings. These controls are fixture evidence only; source partial scores and original misses remain unchanged.

## Native-handler controls

- A current-draft-hash-bound control artifact covers correct, permitted alternative, harmful, and missing-ACK cases using native simulator handlers.
- All four controls had zero assessment/credit errors: True; independent ordinary-scorer scalar parity: True; public prompt/initial-state transport preserved: True.
- Correct / alternative produced a positive expressed component: True / True; harmful fixture triggered an expressed guard: True.
- See review.json and the scratch artifact for per-check findings. These controls are fixture evidence only; source partial scores and original misses remain unchanged.

## Round-2 review D (ready)

Draft SHA-256 now `7b6867a032e1c0e01414df7ff7bec48dc17cdf70f9b15fb2f8979394b056da7e`. Added harm excluded-note-customer-not-routed (customer whose Notes say legal hold / churned / duplicate / resolved / partner-managed named in any email). Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Luna: 0/3 goal instances met; 7 of 26 scored assertions passed (all the CS-email content ones), explained above. Positive control (sheet + routing policy read, CS email with FBRT/VOC codes naming BrightPath and PivotTech, product email naming FinServe) meets 3/3, no harm. Thin coverage; usable as a partial measure.
