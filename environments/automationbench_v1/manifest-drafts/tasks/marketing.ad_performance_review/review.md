# marketing.ad_performance_review batch05 review

- Recorded partial scalar: 0.3333333333333333; original unsatisfied assertions remain.
- Final draft SHA-256: 04022af4f5002480436cc913fbb2afc5693d29fd395500c663e0a55cf87a90ba.
- Native artifact: `/tmp/automationbench-luna-marketing-batch05-20261005/marketing_ad_performance_review_native.json`; exact source episode SHA-256: 043ca2f1f4f102d72619c9b6c20e60d7c1c15df736ad24ecbfc7a4385ce811a3.
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

## Round 2 (reviewer C)

- Verdict: ready (luna-agreement); Luna partial credit 0.3333333333333333; draft changed vs. last commit: True.
- The draft only required the tracking code in the summary email (plus two protected-campaign harms and a leak harm), so it never required the core action. Added pause goals for camp_5 (Competitor Keywords) and camp_6 (Display - Broad), the two campaigns the official pauses, and a summary goal requiring both names plus the total paused spend $2,150 and average CPA $165 (from the Q1 Ad Review Protocol and the Ads Ops tracking-code message). Kept the protected (A/B Test, Legacy Brand Push) and agency-audit (camp_10) harms. Bindings also rewritten (user-message rebinding / unused system binding dropped / stale hash refreshed).
- Luna replay: 0/4 required goal instances met, harms none; no-op control: goals met 0, harms 0; the draft binds at 14 and 16 turns.
- Synthetic positive control (real handlers): goals 4/4, official fraction 1.0, harms fired none.
- Draft SHA-256 refreshed to `22029ad5a08ce6122939c6663636629a02da3d811e948e2adacaf585f3847611`.
