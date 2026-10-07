# operations.sheets_monday_maintenance_queue manifest review

Bound to the exact public prompt and initial state. The recorded reference remains a zero-scored partial; this review does not qualify the whole task.

- Draft SHA-256: `ef89df398f972494a1cb605ca1ed1101e125d6bbec1b3daaec90db4d5c98f151`
- Public prompt SHA-256: `175a3136440d0fe39fe1a0ec9ba5242fcdb61a1c0ee3e97f58c904a1a7d918b3`
- Public initial-state SHA-256: `262f1a64adde902594384be18556ad0a2a1ac2304deb811c2885af2edba0e38a`
- Original episode SHA-256: `83f578dc2c1f539adb9bb59fa17184a2eacc37769ccb154c7773ee0c4135e5af`
- Native score / rescore / reload-rescore parity: `True`; ordinary scalar unchanged: `True`; source bytes unchanged: `True`; errors: 0.

A typed priority order narrows candidates to the tied top High items: Boiler 1 and Conveyor. Boiler 1 has no Due value; Conveyor has Due 2026-02-05. Monday has a public item identity only for Conveyor (`itm_700`). The selection check abstains on the unresolved tie instead of requiring every open row to be updated or declaring a unique winner. The held HVAC Filter guard binds its actual Monday item id (`itm_702`) and the queue/policy reads pass. The ops notice remains missing (0.0).

## Check outcomes

- `eligible-maintenance-monday-update`: abstained None (obligation_requirement_unavailable) ×6
- `maintenance-ops-notified`: valid 0.0 (obligation_required_effect_missing) ×1
- `maintenance-policy-read`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `maintenance-queue-read`: valid 1.0 (obligation_witnessed_required_effect) ×1

The native three-phase replay proves declaration determinism and persistence parity, not task qualification. The public tie and missing Boiler 1 Monday identity remain open.
## Controls and provenance

Queue/policy read controls pass. Date-column lookup for brd_ops returns no columns; priority tie has blank-Due Boiler 1 and mapped Conveyor, so no schedule or held-row write control is claimed. Genuine-handler scenarios and raw receipts are in `/tmp/automationbench-luna-operations-20261005-batch07/queue_read_controls.json`. Latest-complete-per-run findings, lifecycle snapshots, reward maps, ACK receipts and source fingerprints are retained per scenario. Earlier controls and declaration variants remain under `/tmp/automationbench-luna-operations-20261005-batch07/history_latest_complete_extract`.

## Shared-source refresh (2026-10-05)

After the shared source-position selection and Buffer channel-read changes settled, the native three-phase replay and all persisted genuine-handler controls for this task were executed again. Current results are recorded in `/tmp/automationbench-luna-operations-20261005-batch07/operations07_shared_source_refresh.json`; prior run artifacts and reviews remain under `/tmp/automationbench-luna-operations-20261005-batch07/history_pre_shared_source_refresh_20261005`. The current replay retained findings/scalar/source-byte parity with zero errors. Control ordinary and manifest reward maps match in every rerun variant. Current source snapshot: 46 hashed files of 54 requested paths; missing source paths are listed in the linked JSON artifact. These component results do not grant whole-task qualification.
