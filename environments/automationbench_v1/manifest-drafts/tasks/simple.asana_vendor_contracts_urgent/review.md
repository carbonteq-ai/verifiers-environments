# simple.asana_vendor_contracts_urgent

Status: **not_qualified**. Historical partial score: 1.0; it is retained as context only.

Native replay: 2 expressed checks; no scorer errors; ordinary reward map and source bytes unchanged; rescore and wire reload matched latest complete findings. Public prompt and normalized initial input match the recorded task exactly.

Synthetic controls: 3 real-handler variants using the bound public prompt and initial state. See review.json for tool arguments, raw handler results, ACK receipts, per-check values, and current-source fingerprints.

Expressed obligations: 2; gaps: 0; shared system prompt rules out of scope: 2.

Artifacts: draft SHA-256 c583cd36dbb13ea689cda2ec8cf60787bdb1f4fa7096f861f362ab18842b6b7b; episode SHA-256 d9d0f9066112283c30f95ba92721710c39a7e5543f2dca4af6d0a2f9fca70a31; full controls /tmp/automationbench-luna-simple-batch12-20261005/controls_full_v2.json (6b45c90c9611aef32c07e61a37f7701a2231e2a99256aa72e3d414f5450799fd); earlier summary-only controls preserved at /tmp/automationbench-luna-simple-batch12-20261005/controls.json.

## Revision 2026-10-12 (shard 2 eval validation)

request.tag is tag_urgent (the id the prompt names and the add-tag call passes). Replayed on the Luna episode with the step-credit reader (outcome counts in manifest-validation/shard2-results.json). draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `959580b9ea00ffb468049ec89f53df32220792b9a48028d7202649f4e6f3ecd9`.

Edits in this review:
- added harm guard: no duplicate creation of the same record

Luna replay (step-credit reader): 2 of 2 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Luna full pass: every required goal met, no harm; empty run meets nothing.
