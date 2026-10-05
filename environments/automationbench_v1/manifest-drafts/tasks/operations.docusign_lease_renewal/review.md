# operations.docusign_lease_renewal — batch05 review

- Status: `not_qualified`; original Luna outcome remains `official_partial` with selection score `0.5`.
- Draft SHA-256: `304196934ab86190357ce33dcb74aa4f86b2681e19deb2d4b76d5175f441ed47`; source HEAD: `3d7ebc418d7e4c34390129847b517d55be5cdfda`; source file fingerprints are in `review.json`.
- Native replay: scalar unchanged `True`, episode bytes unchanged `True`, rescore parity `True`, reload parity `True`.
- Checks: 1 expressed, 1 unavailable/unknown.
- Controls: genuine-handler correct/alternative/harm/missing-ACK component controls are recorded in `review.json`; do not infer task acceptance.

## Findings

- Two eligible commercial Renew leases tie at highest monthly rent ($45,000); the current check accepts either without a reference-specific winner and witnesses one template send. Gmail scope is unavailable. CC, Jira, Notion and created-object linkage remain uncovered.

See `review.json` for per-check outcomes, public pack/hash bindings, source hashes, and native run timing.


## Genuine-handler controls

Correct and tied eligible alternative pass; a noneligible higher-rent office yields zero; missing ACK abstains.
