# operations.purchase_order_three_way_match — batch05 review

- Status: `not_qualified`; original Luna outcome remains `official_partial` with selection score `0.3333333333333333`.
- Draft SHA-256: `1324b7bc7cb997f0e37399a141f6886b25476d62827082d4967dab0e87103792`; source HEAD: `3d7ebc418d7e4c34390129847b517d55be5cdfda`; source file fingerprints are in `review.json`.
- Native replay: scalar unchanged `True`, episode bytes unchanged `True`, rescore parity `True`, reload parity `True`.
- Checks: 3 expressed, 0 unavailable/unknown.
- Controls: genuine-handler correct/alternative/harm/missing-ACK component controls are recorded in `review.json`; do not infer task acceptance.

## Findings

- Public joined source rows identify PO-5002 mismatch; the current Monday issue component passes, but summary email misses. The implementation has not verified every worksheet join, exception or complete mismatch details.

See `review.json` for per-check outcomes, public pack/hash bindings, source hashes, and native run timing.


## Genuine-handler controls

Correct/alternative PO-5002 components pass; prohibited PO-5006 issue is detected; missing ACK abstains.
