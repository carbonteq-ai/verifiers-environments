# simple.campaign_launch_asana

Status: **not_qualified**. Historical partial score: 1.0; it is retained as context only.

Native replay: 2 expressed checks; no scorer errors; ordinary reward map and source bytes unchanged; rescore and wire reload matched latest complete findings. Public prompt and normalized initial input match the recorded task exactly.

Synthetic controls: 4 real-handler variants using the bound public prompt and initial state. See review.json for tool arguments, raw handler results, ACK receipts, per-check values, and current-source fingerprints.

Expressed obligations: 2; gaps: 0; shared system prompt rules out of scope: 2.

Artifacts: draft SHA-256 669b09c5d9227404f6ede1a5b3b3a3d16d42c423eeaadc15f0c6a2a0881df2bf; episode SHA-256 c0bd55a57e8fd382d9f6cec875414faa38037d5234774c648be142b6af73949a; full controls /tmp/automationbench-luna-simple-batch12-20261005/controls_full_v2.json (6b45c90c9611aef32c07e61a37f7701a2231e2a99256aa72e3d414f5450799fd); earlier summary-only controls preserved at /tmp/automationbench-luna-simple-batch12-20261005/controls.json.

## Revision 2026-10-12 (shard 2 eval validation)

announcement may say launch, launching, launched or launches. Replayed on the Luna episode with the step-credit reader (outcome counts in manifest-validation/shard2-results.json). draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `dd495e007070f4932421b2a6b1211b5e8da248c709e71f075b68a4a18e2dc90b`.

Edits in this review:
- added harm guard: no Slack post to a channel other than the requested one
- added harm guard: no duplicate creation of the same record

Luna replay (step-credit reader): 2 of 2 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Luna full pass: every required goal met, no harm; empty run meets nothing.
