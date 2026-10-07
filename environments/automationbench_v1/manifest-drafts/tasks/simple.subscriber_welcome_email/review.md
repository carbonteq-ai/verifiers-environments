# simple.subscriber_welcome_email — public-only component review

Public input is reserved in `reward_test`; no recorded reference episode is supplied. The contract is **not qualified** and has no action credit or training eligibility.

Current draft SHA-256: `35279e16e791f1db6e61ef6ad6962d0d2312c854d379217abebb0cc6e5803c37`. Public pack/input hashes and native source binding are recorded in `review.json`.

| Public obligation | Component evidence |
|---|---|
| read notification | `reads-mia-welcome` — read the exact Gmail message and body |
| create HubSpot contact | `creates-mia-welcome` — create once with Mia Torres and the email in the notice |
| send welcome email | `sends-mia-welcome` — send once to the subscriber with welcome wording, after the read and contact action |

Synthetic real-handler controls use the exact public prompt and native-normalized public initial state. Correct/adverse/missing-ACK cases retain raw handler material and scored native WireEpisodes. The ordinary-task comparator used empty assertions only; this is harness parity and does not substitute for the hidden `reward_test` baseline.

Validation:
- Native public binding/rescore/reload: errors `0`, public input match `True`, rescore `True`, reload `True`.
- Handler controls: 3 (correct, adverse, missing ACK); errors `0`, empty-assertion harness scalar equality `True`, reload parity `True`.
- Full controls: `/tmp/automationbench-luna-simple-batch28-20261005/controls_full_v3.json` (SHA-256 `7a69e28f3dacc4146c9de7222027bd4677d86fe5eec075bdff22aada1dc48a95`).
- Public binding pass: `/tmp/automationbench-luna-simple-batch28-20261005/replay_public_v2.json` (SHA-256 `0c5792a4aa4991e4311f7a7457cbeb19f024a979caee20223777417bc3f6604c`).

Limitations:
- The public Gmail-only initial snapshot has no HubSpot contact collection to support a separate terminal created-and-retained check; creation is assessed from the authenticated native write.

No original trajectory replay, hidden benchmark reward comparison, task qualification, action credit, or training eligibility is claimed.
