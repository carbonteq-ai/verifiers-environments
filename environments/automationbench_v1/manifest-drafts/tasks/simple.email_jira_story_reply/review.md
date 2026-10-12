# simple.email_jira_story_reply

Public prompt: A customer sent feature feedback via email. Read the email, create a Jira story in the PROD project capturing the feedback, and reply to the customer thanking them for their input.

The draft binds the provided full prompt and native-normalized public initial state, then checks the expressed outcomes listed in review.json. The historical reference score (0.5) is preserved; it is not a qualification result.

All three genuine-handler component controls retain raw simulator materials, native scored wire episodes, receipt/ACK envelopes, reward maps, current draft hashes, and source-module hashes in the linked artifact. Correct and adverse findings are separated from scope-closure findings. The missing-ACK variant abstains on affected action/effect checks. The ordinary comparator has empty assertions and demonstrates harness scalar parity only; it is not the original benchmark baseline.

Known limitations: The correct-handler create is blocked on the exact public initial state: jira.projects is empty, and jira_create_issue(project=PROD, issuetype=Story, ...) returns success=false, jira_project_not_found; the create finding is known 0 in both positive and adverse controls. No synthetic project was seeded. The reply component is independently checked and discriminates correct from wrong recipient.

Whole-task status: **not qualified**. No action credit or eligibility is claimed.

## Revision 2026-10-12 (shard 2 eval validation)

rebound; reply need not share the source thread id; accepts Thanks/Thank you; accepts the first name; story summary must mention CSV and export instead of the verbatim phrase. Replayed on the Luna episode with the step-credit reader (outcome counts in manifest-validation/shard2-results.json). draft_sha256 in review.json predates this revision.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `73b37fd4ed71ee70aeb4172bcc058b2cf3005edbd2b06f15b76227742fbd9ba9`.

Edits in this review:
- added harm guard: no email that is not addressed to the requester/sender

Luna replay (step-credit reader): 3 of 3 decided required findings met; failing goal checks: none; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Relaxed Thank/CSV+export/name checks keep recipient, project, and content requirements; not satisfiable by an empty run (verified). Luna meets all; official partial is a summary wording rule.
