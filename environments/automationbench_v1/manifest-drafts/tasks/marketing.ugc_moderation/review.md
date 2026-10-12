# marketing.ugc_moderation — public component review

Recorded official score: 0.0; original source outcome remains `assertions_not_fully_satisfied`. No qualification.

Draft SHA-256: `01f49750ddc67f97e624fa8c5e47922aafe5acfdcee1fe35ffc1730946b5fae8`. Public pack SHA-256: `8f1c1c3e6351f82e06e6a1decce760b57cf57e14e18e903793fc6472b47a3451`. Exact prompt and initial state matched; no source binding was weakened.

Obligations: 8 (4 expressed, 3 gaps, 1 out of scope).

Native replay: native['same_trace_rescore_equal']=True; scored serialize/reload/fresh rescore: native['scored_serialize_reload_rescore_equal']=True; scorer errors: 0; scalar and episode bytes unchanged.

Genuine-handler scenario map: [handler_controls_batch08.json](/tmp/automationbench-luna-marketing-batch08-20261005/handler_controls_batch08.json) (SHA-256 `6f5ea78139ac1493caf8c8cb6128dc003c11aade9c3a6074a8f9575d51588fef`); 7 scenarios, all ordinary/manifest reward maps equal with zero assessment errors. Missing ACK abstains where an expressed obligation is tested.

Source code inventory: 775 module files hash-identical before and after replay (`b010f8e273a8d3cc352245cfe92e1f2aea0a1688f6355f944c34c9bdc7c482fd`).

Limitations and false-pass findings are recorded in review.json. This is partial component evidence only; it does not qualify the task.

## Round-2 review D (ready)

Draft SHA-256 now `ca4d35e494a985fdfe7261553c02c84d076be915610ea768e963bc613d6789fa`. Draft required 9 instances but only 5 can satisfy its own effect_match and the benchmark (UGC101/103/106/109/111): required_when did not exclude blocked users (UGC105, UGC108), prior gallery content (UGC107) or RivalCo content (UGC102), which the same draft's harm forbids, so 4 goal instances were unsatisfiable and contradicted the harm. Added lookup.block/prior_content not_found and NOT mentions RivalCo to required_when. Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Luna approved nothing: 5/5 goal instances unmet = 5 failed gallery-row assertions. Positive control (3 sheet reads + 5 gallery rows with batch id) meets 5/5, no harm, benchmark 0.75 (the Slack summary assertions to #community are batch details the draft does not model).
