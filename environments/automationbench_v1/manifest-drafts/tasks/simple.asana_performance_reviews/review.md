# simple.asana_performance_reviews

Status: **not_qualified**. Historical partial score: 1.0; it is retained as context only.

Native replay: 1 expressed checks; no scorer errors; ordinary reward map and source bytes unchanged; rescore and wire reload matched latest complete findings. Public prompt and normalized initial input match the recorded task exactly.

Synthetic controls: 3 real-handler variants using the bound public prompt and initial state. See review.json for tool arguments, raw handler results, ACK receipts, per-check values, and current-source fingerprints.

Expressed obligations: 1; gaps: 0; shared system prompt rules out of scope: 2.

Artifacts: draft SHA-256 1c2bdd9d4bd9080d401cbaf7eab833bef74382d9adaf080e0c7414e594e7ad03; episode SHA-256 5f4f0a59a64c98b37184fa3f8e3a1c7f558f19d02a2d208f5fb40fa74e049d4e; full controls /tmp/automationbench-luna-simple-batch12-20261005/controls_full_v2.json (6b45c90c9611aef32c07e61a37f7701a2231e2a99256aa72e3d414f5450799fd); earlier summary-only controls preserved at /tmp/automationbench-luna-simple-batch12-20261005/controls.json.

## Round 2 review (reviewer A)

Verdict: ready.

Changes: Rewritten bound to the user message (replay.py --write-rebound) so it binds at 14 and 16 turn budgets; every goal comparison on a possibly absent effect field is now guarded by `present` so an omitted field is a decided miss instead of an abstention (abstained goals drop out of the training denominator: a call that omits the field would have scored 0/0). Added harm task-in-wrong-workspace-or-project.

Evidence: Luna full pass (official 1.0): every counted goal met, no harm; no-op: 0 goals met, 0 harms; binding None at turn budgets 14 and 16; no assessment or credit errors. Synthetic controls (one-field-wrong, omitted-field, wrong-target, missing call) are in round2/a/simple/controls.json: every goal control leaves the targeted goal unmet and every guard control fires its harm (non-violating variants do not fire it).

Official-assertion differences: Official asana assertion has no project; the goal also pins project proj_people because the prompt states it.

Notes: Single counted goal (name, workspace, project, due date; exactly one create). No inert goals.
