# simple.trello_q1_marketing_budget

The draft binds its component checks to public task text and initial state. Current native replay reports: requested-card-created-in-target-list=valid:1.0, requested-card-created-outside-target-list=valid:0.0. The retained episode score and outcome are preserved as history and are not a qualification claim.

The card goal now requires a complete, ACKed Trello list-read result for the public board and list name, matched by returned list ID before card dispatch. Genuine-handler controls show correct order witnesses the goal; omitted or late reads leave it unsatisfied; a missing read ACK abstains, missing card-write ACK leaves outcome and harm scope unknown; and a wrong-list card triggers the existing harm guard. Full handler arguments/results, ACKs, raw snapshots, current source fingerprints, reward comparisons, and reload checks are linked in `review.json`.

Whole-task status: **not qualified**. This is task-component evidence without action credit; see `review.json` for original score, hashes, scope, and remaining limits.

## Round 2 review (reviewer A)

Verdict: ready.

Changes: the counted goal comparison on a possibly absent effect field is now guarded by `present` so an omitted field is a decided miss instead of an abstention (abstained goals drop out of the training denominator: a call that omits the field would have scored 0/0). No other change: the draft already bound the user message, and its goal and harm were already correct.

Evidence: Luna full pass (official 1.0): every counted goal met, no harm; no-op: 0 goals met, 0 harms; binding None at turn budgets 14 and 16; no assessment or credit errors. Synthetic controls (one-field-wrong, omitted-field, wrong-target, missing call) are in round2/a/simple/controls.json: every goal control leaves the targeted goal unmet and every guard control fires its harm (non-violating variants do not fire it).

Official-assertion differences: Official assertion is the card on board/list/name; the goal additionally requires that the board's lists were read first (prompt: 'First list the board's lists').
