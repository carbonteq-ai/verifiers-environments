# simple.trello_urgent_support_card — round 5

Public pack `batch-07.json` task 8. Luna episode sha256 `19bce99b…19f1`. Whole task: **not qualified** (4 / 5 in-scope expressed, 1 gap; 2 out of scope).

**Draft** (`draft.json`, 4 checks, outcome only). Request singleton: board, card name, label and the To Do list id copied from the public `board_list` record named "To Do". Obligations: (1) a Trello card create with the exact name on brd_support in lst_support_todo; (2) a label_urgent create whose card joins a card the agent created with that name in To Do. Guards: the named card created in another list; label_urgent put on a card the agent did not create.

**Gap.** "First list the board's lists" is a required read order. There is no Trello read evidence (`trello_board_list` is find-or-create; finding leaves the world unchanged, so no write is seen). Category `required_read_ordering`; not one of the four mechanisms in progress.

**Luna replay.** Both obligations valid 1.0; both guards 0 violations; scopes closed; no errors. Scalars and bytes unchanged; rescore and reload repeat.

**Simulator runs.** Correct: 1/1, guards clean. Card in In Progress: both obligations 0 and the list guard fires. Label on an unrelated card: label obligation 0 and the foreign-card guard fires. Missing ACK on the card create: everything abstains.

**Known gaming (1).** Skipping the listing and hard-coding the list id earns full credit (the gap).


## Current-byte validation addendum

Fresh retained-development replay executed with draft SHA `d578754319b859b0d69cecb86f953cabdd800dddb616fd9b706a4fbecf587c12` and episode SHA `19bce99b17771867fd928cefb8e1079895decac6359a92d47a2cf2491d1119f1`. Public prompt and normalized initial state match this episode, and the draft's public-pack and episode bindings returned no mismatch. The manifest and ordinary benchmark reward maps matched the retained pre-score map. Rescore and serialized-wire reload/rescore reproduced all 8 latest per-signal findings with zero errors; episode bytes and source module fingerprints remained stable.

The explicit list-before-create requirement remains a known gap. The current `trello.list_reads@1` adapter captures the acknowledged exact To Do lookup, but full source inventory is currently unavailable because a later `trello_card_label` mutation is not yet classified as a known Trello write. Thus this replay validates the four declared outcome checks, not the ordering requirement. The source-backed reproducer is recorded in `review.json`.

Evidence: [result JSON](/tmp/automationbench-luna-hr-linkage-closure-20261005/remaining-legacy-validation/evidence/simple_trello_urgent_support_card.result.json) (SHA-256 `c8cb279fec95d43cda6de611d57f4b1a726db515ac58238ca6a30becf09cf7a6`); [full scored WireEpisode](/tmp/automationbench-luna-hr-linkage-closure-20261005/remaining-legacy-validation/evidence/simple_trello_urgent_support_card.scored-wire.json) (SHA-256 `d10dd8e9a385aa9f0ebc17a49c2505453dbb70e0e921b1a274229b8d40136370`). This is development replay evidence only and does not revise the official score or establish qualification, action credit, or eligibility.


## Trello list-read ordering adoption

The current draft revision `round6_trello_read_order_v1` (SHA-256 `f9fb4590209e1071933a40a8187b8e61fa9a8a75583765d05441c857e7896066`) now binds the public instruction to list the board’s lists before card creation. The historical gap and earlier replay remain documented above; this addendum records the later shared `trello.list_reads@1` adoption.

Five genuine-handler controls ran against the exact public prompt and normalized initial state. The positive card creation after the acknowledged To Do listing scored 1.0; skipping the listing or reading after card creation scored 0.0; a missing listing ACK abstained. Missing card-write ACK also abstained. Ordinary, manifest and pre-score reward maps matched; saved-wire rescore and reload/rescore reproduced findings and rewards with no errors. Full scored wire archives retain dispatch/return evidence and ACK arrays. This remains component evidence only; it does not grant whole-task qualification, action credit or eligibility.

Control artifacts: [index](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence/index.json); [positive result](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence/positive.result.json) / [wire](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence/positive.scored-wire.json), [skip_listing result](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence/skip_listing.result.json) / [wire](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence/skip_listing.scored-wire.json), [late_read result](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence/late_read.result.json) / [wire](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence/late_read.scored-wire.json), [missing_ack_read result](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence/missing_ack_read.result.json) / [wire](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence/missing_ack_read.scored-wire.json), [missing_ack_card result](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence/missing_ack_card.result.json) / [wire](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence/missing_ack_card.scored-wire.json).


## Corrected self-contained control archives

A follow-up control set keeps the native `AutomationBenchTask` task object from the retained episode. The five saved wires retain all 17 task-data fields through reload, including assertions and initial state; public prompt and normalized initial-state comparisons pass on both sides of serialization. The prior five wires/results remain preserved as historical evidence because they lacked those fields.

Each reload/rescore reconstructed environment state only from the saved wire task data and `trace.info`; it did not inject the external fixture. Ordinary, manifest and pre-score reward maps matched, findings/rewards repeated after rescore and reload, and errors were empty. This is component evidence only.

Corrected artifacts: [index](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence_taskdata_v4/index.json); [positive result](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence_taskdata_v4/positive.result.json) / [wire](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence_taskdata_v4/positive.scored-wire.json), [skip_listing result](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence_taskdata_v4/skip_listing.result.json) / [wire](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence_taskdata_v4/skip_listing.scored-wire.json), [late_read result](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence_taskdata_v4/late_read.result.json) / [wire](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence_taskdata_v4/late_read.scored-wire.json), [missing_ack_read result](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence_taskdata_v4/missing_ack_read.result.json) / [wire](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence_taskdata_v4/missing_ack_read.scored-wire.json), [missing_ack_card result](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence_taskdata_v4/missing_ack_card.result.json) / [wire](/tmp/automationbench-luna-hr-linkage-closure-20261005/trello-ordering-adoption/evidence_taskdata_v4/missing_ack_card.scored-wire.json).
