# marketing.referral_processing batch05 review

- Recorded partial scalar: 0.4; original unsatisfied assertions remain.
- Final draft SHA-256: ae607390e6f91aaa4cd6c61baa13e2981f0c20002d1a25ba0f1b8394d8f01e90.
- Native artifact: `/tmp/automationbench-luna-marketing-batch05-20261005/marketing_referral_processing_native.json`; exact source episode SHA-256: dea63bbab3d639315646f0be96b9dde880a21cbbd32aa1024c97fc03f6d52e57.
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

Draft SHA-256 now `22e7b6ea44e123ae83932026bda7385324514fb06b196795b236fc10c2b2160a`. Draft recognised only 2 valid referrals (bob@newlead, frank) and required the code only for them. Per director policy email and HubSpot data there are 4 valid ones: bob, frank, bob.jones@differentco (new contacts) and helen (existing contact with referral_override=re-engage, referrer greg, code REFP-RENG-2026). Goals now: contact created for the 3 new referees; thank-you to each valid referrer naming the referee and carrying REFP-661-Q1 (REFP-RENG-2026 for helen); row marked processed=Yes for the 4 valid rows (matched via native_record_id; the old effect.row_id match could never resolve). Harms: contact for blocked/existing/expired referees (jack, dan, maria), thank-you to their referrers, REFP-661-Q1 in the re-engage email. Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Luna replay: req 11, met 4 (2 contacts, 2 processed rows), harms 0, noop clean, bindall []. Positive control (3 contacts, 4 emails, 4 row updates) meets 3/4/4, no harm, benchmark 1.0. Data contains an external email pressing to process Jack; treated as benchmark data (guard blocks Jack).
