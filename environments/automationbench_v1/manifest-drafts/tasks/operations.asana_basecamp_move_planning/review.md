# operations.asana_basecamp_move_planning — public-only review

Draft SHA-256: `e1674088f3c973803e34cc4ce1b1aeb45cf5318aa349f8ce64b00767b7beb0eb`. Public input SHA-256: `f50a3a7254fbb61109f40c9d9a83b358159304773b995094d2b0ac44a8e12550`.
Control artifact SHA-256: `20b9b8a452f4cbe313571b68234d19dfbe4235baacc2f3aeafa2585aa29076c7` (56727168 bytes); 7 fresh genuine-handler scenarios retain raw arguments, results, receipts, ACKs, and unique serialized wire files with verified hashes.

Coverage: 5 expressed components, 1 explicit gaps; no qualification or eligibility grant.

## Expressed checks and gaps

- **M1 (gap)** Choose the next Phase 1 floor-plan signoff task; row ordering/status/hold selection is not fully source-relative.
- **M2 (expressed)** Review status-filter and ownership-dispute hold policy rows before scheduling; exact sheet-scoped row reads are witnessed for the two required public rows via row_ids with per-candidate attribution. Check: `status-filter-policy-row-read; ownership-dispute-hold-policy-row-read`.
- **M3 (expressed)** Create Asana task using a phase-1 pending signoff candidate. Check: `phase1-pending-signoff-asana-task`.
- **M4 (expressed)** Attach created task to Move project Planning section. Check: `planning-section-attachment`.
- **M5 (expressed)** Tag created task Move. Check: `move-tag-attachment`.
- **M6 (expressed)** Create corresponding Basecamp todo with task name. Check: `basecamp-todo-target-name`.

## Validation

All 7 scenarios have exact current-draft hashes, ordinary and manifest reward maps, scalar noninterference results, and verified wire-file hashes. Each serialized episode was reloaded and rescored; findings match, as do separate same-trace rescores. Source inventories are unchanged: `{'/home/hammad/projects/verifiers-credit-candidate-20261003': True, '/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1': True}`. The full raw evidence and paths are in `review.json` and the linked control artifact.

The earlier control artifact and its recorded results remain in `validation_history`. Its shared wire paths were overwritten by later runs, so original wire bytes are unavailable; current evidence uses new unique per-scenario paths. Frozen public inputs and original benchmark scores remain unchanged. No task qualification or training eligibility is claimed.

For the row-read checks, omitting the policy read makes required read/action goals 0; reading after task creation leaves the read witnessed but the before-read task goal at 0; missing the policy-read ACK makes dependent read/action checks abstain.
