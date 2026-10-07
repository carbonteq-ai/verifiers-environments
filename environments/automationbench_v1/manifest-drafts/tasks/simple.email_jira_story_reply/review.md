# simple.email_jira_story_reply

Public prompt: A customer sent feature feedback via email. Read the email, create a Jira story in the PROD project capturing the feedback, and reply to the customer thanking them for their input.

The draft binds the provided full prompt and native-normalized public initial state, then checks the expressed outcomes listed in review.json. The historical reference score (0.5) is preserved; it is not a qualification result.

All three genuine-handler component controls retain raw simulator materials, native scored wire episodes, receipt/ACK envelopes, reward maps, current draft hashes, and source-module hashes in the linked artifact. Correct and adverse findings are separated from scope-closure findings. The missing-ACK variant abstains on affected action/effect checks. The ordinary comparator has empty assertions and demonstrates harness scalar parity only; it is not the original benchmark baseline.

Known limitations: The correct-handler create is blocked on the exact public initial state: jira.projects is empty, and jira_create_issue(project=PROD, issuetype=Story, ...) returns success=false, jira_project_not_found; the create finding is known 0 in both positive and adverse controls. No synthetic project was seeded. The reply component is independently checked and discriminates correct from wrong recipient.

Whole-task status: **not qualified**. No action credit or eligibility is claimed.
