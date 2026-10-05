# operations.cross_department_budget_reconciliation — public-only review

Draft SHA-256: `983f7564616166de48f5a1a1d3f2bbb1cc31e86b67c843a0652bc2db4e059ac6`. Public input SHA-256: `b7918894aa8770814c279b62a0cae8ac75598425b224d67e7935ab80547f936b`.
Control artifact SHA-256: `20b9b8a452f4cbe313571b68234d19dfbe4235baacc2f3aeafa2585aa29076c7` (56727168 bytes); 4 fresh genuine-handler scenarios retain raw arguments, results, receipts, ACKs, and unique serialized wire files with verified hashes.

Coverage: 4 expressed components, 4 explicit gaps; no qualification or eligibility grant.

## Expressed checks and gaps

- **B1 (gap)** Reconcile spending and approved amendments across all worksheets; full population arithmetic is not expressed.
- **B2 (gap)** Exclude amendments not approved; source-relative filtering and adjusted budget computation are not fully checked.
- **B3 (gap)** Use variance threshold from policy tab; policy-row reads currently abstain due candidate identity ambiguity.
- **B4 (expressed)** Notify Engineering head of a source-derived overrun. Check: `eng-head-overrun-notice`.
- **B5 (expressed)** Notify Marketing head of a source-derived overrun. Check: `mkt-head-overrun-notice`.
- **B6 (expressed)** Notify Sales head of a source-derived overrun. Check: `sales-head-overrun-notice`.
- **B7 (expressed)** Post a heads-up to the finance alerts channel; current channel notification check does not witness the positive control. Check: `finance-alert-channel-overruns`.
- **B8 (gap)** Preserve exact source values in notices; current checks do not enforce verbatim values or complete numeric reconciliation.

## Validation

All 4 scenarios have exact current-draft hashes, ordinary and manifest reward maps, scalar noninterference results, and verified wire-file hashes. Each serialized episode was reloaded and rescored; findings match, as do separate same-trace rescores. Source inventories are unchanged: `{'/home/hammad/projects/verifiers-credit-candidate-20261003': True, '/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1': True}`. The full raw evidence and paths are in `review.json` and the linked control artifact.

The earlier control artifact and its recorded results remain in `validation_history`. Its shared wire paths were overwritten by later runs, so original wire bytes are unavailable; current evidence uses new unique per-scenario paths. Frozen public inputs and original benchmark scores remain unchanged. No task qualification or training eligibility is claimed.
