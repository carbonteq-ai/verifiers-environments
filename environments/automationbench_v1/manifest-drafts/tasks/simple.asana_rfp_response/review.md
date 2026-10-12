# simple.asana_rfp_response

Status: **not_qualified**. Historical partial score: 1.0; it is retained as context only.

Native replay: 1 expressed checks; no scorer errors; ordinary reward map and source bytes unchanged; rescore and wire reload matched latest complete findings. Public prompt and normalized initial input match the recorded task exactly.

Synthetic controls: 3 real-handler variants using the bound public prompt and initial state. See review.json for tool arguments, raw handler results, ACK receipts, per-check values, and current-source fingerprints.

Expressed obligations: 1; gaps: 0; shared system prompt rules out of scope: 2.

Artifacts: draft SHA-256 7571cecc7aeade7c0fb41b79115067afddb1909170f6293e141a0a4bea002812; episode SHA-256 5cb7c02e674f7398ab70dfb8e31fcd2699cba611a192cbec0d75afe4d18f7fdb; full controls /tmp/automationbench-luna-simple-batch12-20261005/controls_full_v2.json (6b45c90c9611aef32c07e61a37f7701a2231e2a99256aa72e3d414f5450799fd); earlier summary-only controls preserved at /tmp/automationbench-luna-simple-batch12-20261005/controls.json.

## Revision 2026-10-12 (shard 2 eval validation)

rebound from the whole-prompt binding to the user message (prompt[1].content). Replayed on the Luna episode with the step-credit reader (outcome counts in manifest-validation/shard2-results.json). draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `4c4433b72bb319bebaa3a46ebd62bfb51bd4880f33b66bce90831d125707ab61`.

Edits in this review:
- added harm guard: no duplicate creation of the same record

Luna replay (step-credit reader): 1 of 1 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Luna full pass: every required goal met, no harm; empty run meets nothing.
