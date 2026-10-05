# marketing.vendor_management — public-only component review

This frozen assignment remains reserved in `reward_test`; only the public prompt, initial state, and tool catalog were used.

Draft SHA-256: `1b145ed108e5f2ef11d6eb80973921eb726df48dde5f1016d3eedf36b0c70250`. Public pack SHA-256: `4b62e3c5a202bdb1e3f78ad86480b951911f47cf5839d693e96d15c9f8e33303`; public input SHA-256: `0fe967c207759d2d2a0a6d13dbf889dda9088228905fe2c5dd3be45c1cf8c8ba`.

Obligations reviewed: 6; expressed: 3; gaps: 1; out of scope: 2.

The route controls now witness one exact low-spend Slack route and one exact high-spend procurement email. The wrong-route email is caught by the harm guard; omitting the action ACK abstains. Candidate source reads were qualified: the sheet returned 7 rows with annual_spend/vendor/expiry_date/notes/service/auto_renew, and Gmail returned the message policy body and identity fields.

The previous false positive/negative controls used `$50000`/`$75000` while the authored matcher requested decimal_string. The current matcher uses usd_string, which recognizes those genuine amount strings. The earlier artifacts remain in validation history and are superseded.

Current raw controls, ACKs, snapshots, exact task inputs, serialized/reloaded wire episodes, and current source inventory are in `/tmp/automationbench-luna-marketing-batch09-20261005/vendor_amount_format_controls.json` (SHA-256 `1d7d70b4e199dc15be65f289bd295f964a78167789f2f00005092254d7e904b5`). Ordinary/manifest and reload reward maps and findings match; no assessment errors.

The remaining no-action and full vendor-disposition obligations remain gaps. No task qualification is inferred.
