# simple.feature_launch_slack (round 6)

Status: **qualified_candidate** — 4/4 in-scope obligations expressed, 0 gaps, 3 out of scope.

Extends the installed partial manifest `src/automationbench_v1/contracts/tasks/simple-feature-launch-asana-occurrence.json` (its checks, sources, bindings and credit are unchanged).

## Obligations

- O1-post-in-product (goal, expressed, `announcement-in-product`): slack.messages@1 channel_message in CPROD01 (bound from public initial channels).
- O2-post-names-feature (report, expressed, `announcement-names-feature`): Named feature: the #product post mentions 'analytics dashboard' as words.
- O3-post-says-live (report, out_of_scope): Whether the post conveys a launch is wording.
- O4-asana-task (goal, expressed, `launch-monitor-creation, monitor-task-recorded`): Installed occurrence check unchanged (keeps credit) plus a record-write companion with the same predicate that decides 0 when the task is missing or in the wrong workspace.
- O5-single-task (guard, expressed, `duplicate-monitor-task`): Harm: a second create_task with the same name and workspace (Asana has no delete tool).
- SYS-no-clarification (guard, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.
- SYS-list-only-acted-items (report, out_of_scope): Shared system-prompt rule; out of scope by the 2026-10-04 scope decision.

## Luna replay

No errors; rescore and reload equal; scalar rewards and episode bytes unchanged. Values: announcement-in-product=1.0, announcement-names-feature=1.0, duplicate-monitor-task=0.0, launch-monitor-creation=1.0, monitor-task-recorded=1.0.

## Simulator runs and gaming

H2 duplicate -> guard 1; H4 task without post -> O1/O2 0; posting elsewhere fails O1 (channel id). No delete/undo tool exists for Slack posts in scope or Asana tasks.

Known gaming: Post 'analytics dashboard launch postponed' in #product (Launch meaning is out of scope (requires_judgement).)

Mechanism notes: Installed launch-monitor-creation (asana.actions@1) cannot close scope when the public initial world has no Asana service: wrong workspace (H3) and no task (N0) are abstained, never 0. Worked around with the service.record_writes@1 companion (decides 0); the installed check is unchanged.

## Revision 2026-10-12 (shard 2 eval validation)

field authority paths moved from the whole prompt to the user message (4 goals were abstaining with request_field_authority_unbound). Replayed on the Luna episode with the step-credit reader (outcome counts in manifest-validation/shard2-results.json). draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `ec8d75a71f86cdc315b6e408196c6f4883b660dcf41d2fc2caf8fca26674da8c`.

Edits in this review:
- added harm guard: no Slack post to a channel other than #product

Luna replay (step-credit reader): 4 of 4 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Luna full pass: every required goal met, no harm; empty run meets nothing.


## Round 2 review (reviewer A, small-fix item 3): proposal draft.proposed.json

draft.json is untouched. draft.proposed.json is a byte copy of the reviewed eval draft (the draft.json in this folder) proposed as the replacement of the installed qualified manifest; adopting it needs requalification of the credit declarations because the check set changes.
Why: Installed qualified manifest checks only the Asana monitoring task creation. The reviewed draft keeps it and adds the Slack announcement in #product naming the feature, a bounded single monitoring task (duplicate guard) and a guard against posting to other channels; it binds the user message (installed binds the whole prompt, system message included, which mismatches at 14/16 turns).
Evidence (replay.py): installed manifest: binding(14/16)=manifest_source_binding_mismatch/manifest_source_binding_mismatch; Luna required=1 met=1 harms=0; no-op goals=0 harms=0. Reviewed/proposed draft: binding(14/16)=ok/ok; Luna required=4 met=4 harms=0; no-op goals=0 harms=0. Guard violation controls for the added guards that Luna did not trigger are listed in round2/a/guards/guard-controls.json (small-fix item 5).
