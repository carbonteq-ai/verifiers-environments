# marketing.landing_page_alert — partial component review

Reference score retained: 0.2; original outcome remains unsolved.
Current draft SHA-256: `47599bbef28b95ad7db6d5678712b46319c2c77ae7fa664f229e097225164fbb`
Source episode SHA-256: `400bffc46b145e120c89253b5c3622991e90fd4fce3eeeff04ec8dfb347f7c09`
Public pack SHA-256: `46a9cc5f0f6e669ea4ed3fa38726fa8d99ce3c9f14d0b40caab03b185f1f5ba8`

Native replay: exact public prompt/state retained; same-trace rescore and scored serialize/reload/fresh rescore agree; original score/episode bytes unchanged; 0 assessment/credit errors.
Real-handler controls: correct, alternative, harmful, missing_ack; independent ordinary reward maps equal manifest reward maps for every recorded scenario.
Checks authored: 3; qualification: not granted.

Remaining documented gaps: none recorded.

## Round 2 (reviewer C)

- Verdict: ready (luna-agreement); Luna partial credit 0.2; draft changed vs. last commit: True.
- Bindings only: rebound the prompt binding to the user message and/or dropped the unused system-message binding (it hashes differently at the 14- and 16-turn loads); no check was changed.
- Luna replay: 1/3 required goal instances met, harms none; no-op control: goals met 0, harms 0; the draft binds at 14 and 16 turns.
- Synthetic positive control (real handlers): goals 4/4, official fraction 1.0, harms fired none.
- Draft SHA-256 refreshed to `080912871d02a888b9634745b72ee2ed46d3b014236bde1a027b79009c6b3be6`.
