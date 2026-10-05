# operations.parking_allocation_management — batch05 review

- Status: `not_qualified`; original Luna outcome remains `official_partial` with selection score `0.5294117647058824`.
- Draft SHA-256: `d6271a2e332b8de4274166ce79048b5251d77c0882cffd1b5f57bf9d3437a696`; source HEAD: `3d7ebc418d7e4c34390129847b517d55be5cdfda`; source file fingerprints are in `review.json`.
- Native replay: scalar unchanged `True`, episode bytes unchanged `True`, rescore parity `True`, reload parity `True`.
- Checks: 9 expressed, 4 unavailable/unknown.
- Controls: genuine-handler correct/alternative/harm/missing-ACK component controls are recorded in `review.json`; do not infer task acceptance.

## Findings

- Public seniority sheet field is `Employment Status`, not `Status`. Genuine handler reads and the office Slack summary now pass. The public allocation stimulus assigns four requests; the retained terminal check has six positive and two zero candidate instances, which does not validate global matching. Existing-assignment/maintenance guards abstain on candidate identity, employee emails abstain on effect scope, visitor update is missed, and P-109 retained-row check is unavailable. No canonical employee-to-spot map is imposed.

See `review.json` for per-check outcomes, public pack/hash bindings, source hashes, and native run timing.


## Genuine-handler controls

Genuine reads and office Slack summary pass. Four allocations are exercised; terminal count yields six passing and two failing candidate instances, not a global assignment proof. Existing-row/maintenance harm check and notification joins remain abstained; missing read ACK abstains.
