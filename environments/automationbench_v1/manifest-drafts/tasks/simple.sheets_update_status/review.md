# simple.sheets_update_status — public-only component review

Public input is reserved in `reward_test`; no recorded reference episode is supplied. The contract is **not qualified** and has no action credit or training eligibility.

Current draft SHA-256: `d95c6a87aeb98f351f09d7cfafa3e534bc0e07f392a24a7351e069b2ccb48121`. Public pack/input hashes and native source binding are recorded in `review.json`.

| Public obligation | Component evidence |
|---|---|
| read Marcus worksheet row | `row-read-marcus-row` — read the named row from ss_leads/ws_leads before updating |
| Marcus status qualified | `marcus-status-update` — preserve row identity, prior Contacted status, and new Qualified status |

Synthetic real-handler controls use the exact public prompt and native-normalized public initial state. Correct/adverse/missing-ACK cases retain raw handler material and scored native WireEpisodes. The ordinary-task comparator used empty assertions only; this is harness parity and does not substitute for the hidden `reward_test` baseline.

Validation:
- Native public binding/rescore/reload: errors `0`, public input match `True`, rescore `True`, reload `True`.
- Handler controls: 3 (correct, adverse, missing ACK); errors `0`, empty-assertion harness scalar equality `True`, reload parity `True`.
- Full controls: `/tmp/automationbench-luna-simple-batch28-20261005/controls_full_v3.json` (SHA-256 `7a69e28f3dacc4146c9de7222027bd4677d86fe5eec075bdff22aada1dc48a95`).
- Public binding pass: `/tmp/automationbench-luna-simple-batch28-20261005/replay_public_v2.json` (SHA-256 `0c5792a4aa4991e4311f7a7457cbeb19f024a979caee20223777417bc3f6604c`).

Limitations:
- No task-specific semantic gap found for the requested row/status component.

No original trajectory replay, hidden benchmark reward comparison, task qualification, action credit, or training eligibility is claimed.
