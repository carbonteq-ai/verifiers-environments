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
