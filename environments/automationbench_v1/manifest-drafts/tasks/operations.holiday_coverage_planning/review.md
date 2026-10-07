# operations.holiday_coverage_planning — public-only review

Draft SHA-256: `63cae48acb98dcb8c6604dee58bc61520733661a1c564120da8ef72b475b7053`. Public input SHA-256: `0ac356da94b6e3d7795d176086a5f4317d0af1ad6aa20e600d82a1a6c1acec0d`.
Control artifact SHA-256: `20b9b8a452f4cbe313571b68234d19dfbe4235baacc2f3aeafa2585aa29076c7` (56727168 bytes); 4 fresh genuine-handler scenarios retain raw arguments, results, receipts, ACKs, and unique serialized wire files with verified hashes.

Coverage: 4 expressed components, 3 explicit gaps; no qualification or eligibility grant.

## Expressed checks and gaps

- **H1 (gap)** Determine covered vs short departments from staff availability, requirements, policy; department-level classification not expressed as a closed population.
- **H2 (expressed)** Use standard holiday shift hours from staffing policy; policy row read checks do not currently resolve candidate identity. Check: `holiday-shift-hours-policy-row-read`.
- **H3 (expressed)** Schedule confirmed Security staff for Feb 16 standard shift. Check: `bella-security-holiday-shift; owen-security-holiday-shift`.
- **H4 (expressed)** Notify heads for departments with insufficient confirmed coverage. Check: `cs-head-shortage-notice; wh-head-shortage-notice; it-head-shortage-notice`.
- **H5 (expressed)** Post overall department status in operations Slack; positive control does not witness current predicate. Check: `holiday-coverage-status-post`.
- **H6 (gap)** Only confirmed staff in sufficiently staffed departments should be scheduled; current checks do not bound all event creates against full department population.
- **H7 (gap)** Preserve source values verbatim; current messages do not enforce complete source-value fidelity.

## Validation

All 4 scenarios have exact current-draft hashes, ordinary and manifest reward maps, scalar noninterference results, and verified wire-file hashes. Each serialized episode was reloaded and rescored; findings match, as do separate same-trace rescores. Source inventories are unchanged: `{'/home/hammad/projects/verifiers-credit-candidate-20261003': True, '/home/hammad/projects/verifiers-environments-reward-candidate-20261003/environments/automationbench_v1': True}`. The full raw evidence and paths are in `review.json` and the linked control artifact.

The earlier control artifact and its recorded results remain in `validation_history`. Its shared wire paths were overwritten by later runs, so original wire bytes are unavailable; current evidence uses new unique per-scenario paths. Frozen public inputs and original benchmark scores remain unchanged. No task qualification or training eligibility is claimed.
