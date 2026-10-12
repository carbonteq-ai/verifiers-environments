# simple.email_sf_update_slack_notify

Public prompt: Riley Thompson just emailed confirming their new title. Update Riley's job title in Salesforce to 'VP of Operations', and let the #sales channel on Slack know about the update.

The draft binds the provided full prompt and native-normalized public initial state, then checks the expressed outcomes listed in review.json. The historical reference score (0.0) is preserved; it is not a qualification result.

All three genuine-handler component controls retain raw simulator materials, native scored wire episodes, receipt/ACK envelopes, reward maps, current draft hashes, and source-module hashes in the linked artifact. Correct and adverse findings are separated from scope-closure findings. The missing-ACK variant abstains on affected action/effect checks. The ordinary comparator has empty assertions and demonstrates harness scalar parity only; it is not the original benchmark baseline.

Known limitations: The prompt mentions an email, but the supplied public initial state has no Gmail message. No email-source read or relationship can be checked. Slack content is checked for name/title/channel, not broader explanatory quality.

Whole-task status: **not qualified**. No action credit or eligibility is claimed.

## Round-2 review D (ready)

Draft SHA-256 now `4fb899029dae55384cf8f75507fac3987bed2e61d2b2a09c40beb651f874ba1c`. Slack goal no longer requires the new title text in the post (prompt only says to tell #sales about the update; benchmark checks only the name); still needs first+last name, channel, and a matching Salesforce title update (join). Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Luna made no writes: 2 counted goals unmet = 2 failed assertions. Positive control (contact update 003201, Slack post to CSALES01 naming Riley Thompson) meets both, bench 1.0. The records.retained_when goal remains but is not counted by the training reader. No harm guards (single-record update task).
