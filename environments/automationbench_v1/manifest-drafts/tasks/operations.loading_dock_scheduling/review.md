# operations.loading_dock_scheduling: batch-04 public manifest review

Status: **partial component authoring; not qualified**. Original Luna score: official_partial recorded_partial_score; score 0.6363636363636364; original partial outcome and misses are retained.

Draft SHA-256: `2a0330cd8e95ad4ed03e35979646c11752d0aae9695e6a3efb5da497394dddee`. Episode SHA-256: `09976a2b074228d40cb89f667e6049c2eb5658ee07b0c36f7cf78877c8a72d5c`. Public input SHA-256: `cbd5b07b21a1ef6d6d941f6b422b1eea3adc504665002f42383ee90b7eb5415a`.

## Declared checks (3)
- `available-held-request-is-not-scheduled` (harm, `effects.prohibited_when@1`).
- `requester-notified-about-insurance-hold` (goal, `effects.required_when@1`).
- `every-dock-requester-receives-a-row-specific-disposition` (goal, `effects.required_when@1`).

## Native replay

- Score/rescore/reload-rescore findings match: `True` / `True`; scalar unchanged: `True`; source episode bytes unchanged: `True`; errors: `0`.
- Stage seconds: score {s["first"]}, rescore {s["rescore"]}, reload-rescore {s["reload_rescore"]}.
- Source revision: `3d7ebc418d7e4c34390129847b517d55be5cdfda`; source file hashes are recorded in `review.json`.

## Genuine-handler controls

- Exact public input and prompt/initial hashes are recorded in `review.json`; control artifact SHA-256: `01a7fb5bb34ed48a0d7bdd6f8a85f457b100eedef3a02b74b4477c63ff8712d9`. Each variant compares manifest scalar to an independently scored ordinary `AutomationBenchTask` on the same public fixture. All variant scalars match; all reported errors are empty.
- `correct_target_genuine_handler_replay`: requester-notified-about-insurance-hold=abstained:None; requester-notified-about-insurance-hold=valid:1.0; requester-notified-about-insurance-hold=inapplicable:None; every-dock-requester-receives-a-row-specific-disposition=valid:1.0.
- `public_supported_alternative_handler_control`: available-held-request-is-not-scheduled=abstained:None; available-held-request-is-not-scheduled=valid:0.0; requester-notified-about-insurance-hold=abstained:None; requester-notified-about-insurance-hold=valid:1.0; requester-notified-about-insurance-hold=inapplicable:None; every-dock-requester-receives-a-row-specific-disposition=valid:1.0.
- `task_specific_harm_or_wrong_target_control`: available-held-request-is-not-scheduled=valid:0.0; available-held-request-is-not-scheduled=valid:1.0; requester-notified-about-insurance-hold=abstained:None; requester-notified-about-insurance-hold=valid:1.0; requester-notified-about-insurance-hold=inapplicable:None; every-dock-requester-receives-a-row-specific-disposition=valid:1.0.
- `missing_persisted_action_acknowledgement`: requester-notified-about-insurance-hold=abstained:None; requester-notified-about-insurance-hold=valid:1.0; requester-notified-about-insurance-hold=inapplicable:None; every-dock-requester-receives-a-row-specific-disposition=valid:1.0; every-dock-requester-receives-a-row-specific-disposition=abstained:None.

## Expected control outcomes

Expected check IDs and statuses/values are explicit in `review.json`; the harness asserted them before writing the results, including the missing-ACK abstentions.

## Findings and limits

The public request disposition positive and an available DR-101 event alternative are witnessed. A real DR-104 held-request event triggers the hold guard. The exact prompt/initial state supplies no current date, so the retained model rationale that dates have passed has no public clock anchor; no task-acceptance inference is made.
- Controls verify the stated components only; they do not establish retained-trajectory acceptance, action credit, or qualification. `review.json` contains per-check findings, latest run IDs, expected controls, and all source/draft/replay hashes.
