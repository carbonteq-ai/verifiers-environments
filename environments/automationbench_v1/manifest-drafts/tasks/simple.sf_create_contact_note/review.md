# simple.sf_create_contact_note — Simple batch 19

**Status: not qualified.** This manifest covers selected public outcome components; the recorded reference score is preserved without promoting it to eligibility or qualification.

## Covered public obligations

- `requested_salesforce_note_created`: Requires one new note attached to source-bound contact id 003003, type contact, with exact requested title and body.

## Validation

- Current draft SHA: `ab8dbcb73b1eb23bcf1983b284d13eb88061ba4a07486144b69fb7bc75a56c80`. Native replay used the exact public prompt/initial/tool allowlist and source episode `50c8032c383ac651cefe874371db604d14ea11ec6ceb16548163bbe6e41e95b9`.
- 3 completed genuine-handler controls: correct, wrong-goal, missing write ACK.
 - Ordinary benchmark scalar, native findings and rewards remained equal after serialization/reload. No trace, assessment or credit errors were present. Raw arguments, results, ACK state, native episode and per-run source fingerprints are linked in `review.json`.

## Limits

- No action or token credit is declared. Shared narration policies remain out of scope. Wrong-goal controls do not claim harm absent public prohibition.

## Round 2 review (reviewer A)

Verdict: ready.

Changes: Rewritten bound to the user message (replay.py --write-rebound) so it binds at 14 and 16 turn budgets; every goal comparison on a possibly absent effect field is now guarded by `present` so an omitted field is a decided miss instead of an abstention (abstained goals drop out of the training denominator: a call that omits the field would have scored 0/0). Removed the custom_type=='contact' requirement (an optional tool argument Luna happened to pass; the prompt does not require it). Added harm note-on-wrong-parent (same title on another parent).

Evidence: Luna full pass (official 1.0): every counted goal met, no harm; no-op: 0 goals met, 0 harms; binding None at turn budgets 14 and 16; no assessment or credit errors. Synthetic controls (one-field-wrong, omitted-field, wrong-target, missing call) are in round2/a/simple/controls.json: every goal control leaves the targeted goal unmet and every guard control fires its harm (non-violating variants do not fire it).

Official-assertion differences: Official assertion needs only body contains 'data integration' + parent 003003; goal requires the exact title and body the prompt quotes.

Notes: Body must match the quoted text exactly.
