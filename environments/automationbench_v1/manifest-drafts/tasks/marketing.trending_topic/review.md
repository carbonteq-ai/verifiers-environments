# marketing.trending_topic — public component review

Recorded official score: 0.0; original source outcome remains `assertions_not_fully_satisfied`. No qualification.

Draft SHA-256: `87c6eddb94145dbba5b38f91a6012a2d4e1728605c07db0e2289e92fbcd0e490`. Public pack SHA-256: `8f1c1c3e6351f82e06e6a1decce760b57cf57e14e18e903793fc6472b47a3451`. Exact prompt and initial state matched; no source binding was weakened.

Obligations: 6 (2 expressed, 3 gaps, 1 out of scope).

Native replay: native['same_trace_rescore_equal']=True; scored serialize/reload/fresh rescore: native['scored_serialize_reload_rescore_equal']=True; scorer errors: 0; scalar and episode bytes unchanged.

Genuine-handler scenario map: [handler_controls_batch08.json](/tmp/automationbench-luna-marketing-batch08-20261005/handler_controls_batch08.json) (SHA-256 `6f5ea78139ac1493caf8c8cb6128dc003c11aade9c3a6074a8f9575d51588fef`); 3 scenarios, all ordinary/manifest reward maps equal with zero assessment errors. Missing ACK abstains where an expressed obligation is tested.

Source code inventory: 775 module files hash-identical before and after replay (`b010f8e273a8d3cc352245cfe92e1f2aea0a1688f6355f944c34c9bdc7c482fd`).

Limitations and false-pass findings are recorded in review.json. This is partial component evidence only; it does not qualify the task.

## Round-2 review D (reject)

Draft SHA-256 now `2ea95c9d16611c6f00a4c3b1d4e812b02416990cb5af1214fe959fb9bfefd13b`. Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Rejected: official outcome and written policy disagree, and the draft has no required goal, so it cannot be validated against Luna or a positive control. Could be revived only by adding a Slack-notification goal (batch code TREND-20260127-Q1 in #marketing after reading the VP message) which would be a weak, easily gamed signal.
