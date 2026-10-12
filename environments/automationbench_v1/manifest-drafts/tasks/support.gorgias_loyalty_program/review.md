# support.gorgias_loyalty_program

Reference outcome remains `official_partial` at score `0.23076923076923078`; this is partial evidence, not qualification.
Current draft SHA-256: `b6088b9b80799e8a8ed604b2dda30ce42c6208e3b25c0c2d41217b90df52f4e7`. Whole-task status: `not_qualified`.
Native replay/reload: `passed`; public prompt and initial state matched; scalar rewards, episode bytes and findings were unchanged; errors: `0`.
Genuine-handler controls (correct/harm/missing-ACK) vs ordinary-task baseline: `passed`; see `review.json` and `/tmp/automationbench-luna-support-batch05-20261005/controls.json`.
Correct-control positive signals: support-gorgias_loyalty_program.batch-reference-email, support-gorgias_loyalty_program.batch-reference-email.coverage, support-gorgias_loyalty_program.batch-reference-summary, support-gorgias_loyalty_program.batch-reference-summary.coverage, support-gorgias_loyalty_program.log-customer-ada.strong.coverage, support-gorgias_loyalty_program.log-customer-cole.brennan.coverage, support-gorgias_loyalty_program.log-customer-leo.marsh.coverage, support-gorgias_loyalty_program.log-customer-mei.lin.coverage, support-gorgias_loyalty_program.log-customer-nina.cruz.coverage, support-gorgias_loyalty_program.log-customer-raj.anand.coverage, support-gorgias_loyalty_program.log-customer-sara.voss.coverage, support-gorgias_loyalty_program.log-customer-tom.hall.coverage.
Harm-control zero-valued signals: support-gorgias_loyalty_program.loyalty-answer-g_601.
Unclosed public requirements retained as gaps: returns-points-policy, business-customer-history-ambiguity, reward-redemption-side-effect, reward-accounting-and-fulfillment.
Synthetic cases are component controls through real simulator handlers; they are not original trajectory replays.

## Round-2 review D (ready)

Draft SHA-256 now `d832d066586604d3efacf46c1d94f7ecf6252f187dcaaa9f298355a9d0faf117`. Draft covered replies for only 5 of the 10 loyalty tickets and its 8 log-customer goals could never be required (population was the task request, which has no email, so required=0). Added reply goals for g_604 (250, Silver, return), g_605 (150, Bronze), g_608 (200), g_609 ($25), g_610 (free shipping); g_602 accepts '1850' or '1,850'; replaced the 8 broken log goals by one per-ticket goal loyalty-log-row (g_601-g_608, Customer Email appended to ss_loyalty Loyalty Log).

Evidence: Luna: 21 required findings, 10 met (team email, batch-reference email, 8 log rows) vs official 6 scored passes + 20 failed; agreement on emails/logs/Slack/replies. Positive control (10 Gorgias agent replies, 8 log rows, team email, Slack to C_LOYAL) meets all 14 goals, bench 1.0, no harm. No harm guards (prompt names no prohibited action).
