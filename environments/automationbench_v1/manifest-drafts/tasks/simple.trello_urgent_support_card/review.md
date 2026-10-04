# simple.trello_urgent_support_card — round 5

Public pack `batch-07.json` task 8. Luna episode sha256 `19bce99b…19f1`. Whole task: **not qualified** (4 / 5 in-scope expressed, 1 gap; 2 out of scope).

**Draft** (`draft.json`, 4 checks, outcome only). Request singleton: board, card name, label and the To Do list id copied from the public `board_list` record named "To Do". Obligations: (1) a Trello card create with the exact name on brd_support in lst_support_todo; (2) a label_urgent create whose card joins a card the agent created with that name in To Do. Guards: the named card created in another list; label_urgent put on a card the agent did not create.

**Gap.** "First list the board's lists" is a required read order. There is no Trello read evidence (`trello_board_list` is find-or-create; finding leaves the world unchanged, so no write is seen). Category `required_read_ordering`; not one of the four mechanisms in progress.

**Luna replay.** Both obligations valid 1.0; both guards 0 violations; scopes closed; no errors. Scalars and bytes unchanged; rescore and reload repeat.

**Simulator runs.** Correct: 1/1, guards clean. Card in In Progress: both obligations 0 and the list guard fires. Label on an unrelated card: label obligation 0 and the foreign-card guard fires. Missing ACK on the card create: everything abstains.

**Known gaming (1).** Skipping the listing and hard-coding the list id earns full credit (the gap).
