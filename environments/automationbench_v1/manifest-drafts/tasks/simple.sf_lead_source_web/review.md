# simple.sf_lead_source_web

Public prompt: Update the lead source on Salesforce lead 00Q004 (Rajesh Gupta) to 'Web'.

The draft binds the exact public system/user prompt and native-normalized initial Salesforce state. It checks requested_lead_retained_with_profile_preserved. No action credit is assigned.

Native replay on the retained episode matched public prompt and initial state; source bytes and scalar rewards stayed unchanged. Replay, rescore, and reload completed with zero errors.

Three real-handler controls are linked in review.json: a correct operation, a materially wrong value, and an ACK omitted from the serialized wire evidence. Missing ACK preserves any independently verified terminal outcome and abstains on action evidence. Ordinary-vs-manifest reward maps and reload parity are recorded for each control.

The original score of 1.0 is retained. Whole-task qualification and training eligibility are not granted.

## Round 2 review (reviewer A)

Verdict: ready.

Changes: Rewritten bound to the user message (replay.py --write-rebound) so it binds at 14 and 16 turn budgets; the counted goal comparison on a possibly absent effect field is now guarded by `present` so an omitted field is a decided miss instead of an abstention (abstained goals drop out of the training denominator: a call that omits the field would have scored 0/0).

Evidence: Luna full pass (official 1.0): every counted goal met, no harm; no-op: 0 goals met, 0 harms; binding None at turn budgets 14 and 16; no assessment or credit errors. Synthetic controls (one-field-wrong, omitted-field, wrong-target, missing call) are in round2/a/simple/controls.json: every goal control leaves the targeted goal unmet and every guard control fires its harm (non-violating variants do not fire it).

Notes: Inert goal requested_lead_retained_with_profile_preserved (records.retained_when) is not counted; the counted effects goal (lead 00Q004 lead_source=Web) carries the requirement. No wrong-lead guard: one seeded lead; another id errors without state change.

Gaps: Profile-preserved check (inert).
