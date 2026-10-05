# simple.sheets_read_then_email

Public-only component assessment for the reserved `reward_test` input.

Current draft SHA-256: `f90d910594744f3965ed4944be7ac836b3152bf12f044ce63a4d0dbdc3735760`. Public pack SHA-256: `26ed59295b49a23a3ba89d051239a368e5bfa77b922e75914e38e0f30dc1dd77`; input SHA-256: `bff2b2b35fe2c5633c0c51b833c30a8d9ba94ea8dcc59cd79f3244755d284cc4`.

The contract checks Requires an acknowledged read of the exact public worksheet before sending; selects the first Pending row by native source path index; the send recipient is linked to that selected row and subject is exact. Correct, alternate body, second-pending wrong recipient, reordered public rows, late read and missing read/write ACK controls were run. This is bounded component coverage, not whole-task qualification.

Fresh genuine-handler controls: [remaining_controls.json](/tmp/automationbench-luna-simple-20261005-batch27/remaining_controls.json) (SHA-256 `72a50dc2b00f4f107ffb201c1ab1807a383d3f28865a4d19fa8561aa83b8d2a4`), cases: correct, alternate, wrong, reordered_public, late, missing_read_ack, missing_write_ack. Raw handler materials and native wire episodes are stored under `/tmp/automationbench-luna-simple-20261005-batch27-rerun-1248/`; every index row binds each file hash to the exact executed draft hash, complete error inventory, source fingerprint and reload result.

Earlier control history remains in `validation_history` and [the preserved stale index](/tmp/automationbench-luna-simple-20261005-batch27/remaining_controls-pre-repair-stale-index-20261005.json) (SHA-256 `ffebf6b6b9fb8071866a08c17b11b4eab8fcd36c602856763f04fe99ff82041b`). The earlier same-named raw/wire files were overwritten and no matching historical bytes were found; those earlier results are not treated as byte-verified current evidence.

Manifest and ordinary synthetic-task reward maps match on the same public input with `assertions=[]`; the default scalar of zero is not a success claim. Serialized reload preserves reward maps and findings. No reference replay, original scalar, action credit, qualification or training eligibility is asserted.

Remaining gap or scope boundary: Free-form introductory email meaning/content is not checked. The reordered-rows test uses a separate public-input variant with its own binding hash and is component robustness evidence, not the assigned task input or a benchmark replay.
