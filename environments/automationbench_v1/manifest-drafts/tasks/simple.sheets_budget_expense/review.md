# simple.sheets_budget_expense

Public-only component assessment for the reserved `reward_test` input.

Draft SHA-256: `2194e254f99f8df307cb4dc6cd0e61955c25b1ce1a44c5a531f4b7156f891c87`
Public pack SHA-256: `26ed59295b49a23a3ba89d051239a368e5bfa77b922e75914e38e0f30dc1dd77`; input SHA-256: `2f137bfe9cb04e5ff1693aa323022fb7c81249ec3ce7a2be3996adf9f4153d84`.

The contract checks All five requested cells are matched to the public prompt and persisted on the appended row. Date uses the target worksheet ISO YYYY-MM-DD representation. This is bounded component coverage, not whole-task qualification.

Genuine handler controls: [first2_controls.json](/tmp/automationbench-luna-simple-20261005-batch27/first2_controls.json) (SHA-256 `f3361afb27094c0466740e97ba7a3f0893d2e5ccae3ba10451c32c6b12e360ef`), cases: correct, alternate_values, wrong, unrelated, missing_write_ack. Each case records the exact executed draft hash, raw handler arguments/results/ACKs, native wire archive/hash, complete error inventory and before/after source module fingerprints.

The task data preserves the public prompt, initial service state and tool catalog. Manifest and ordinary synthetic-task reward maps match; serialized reload preserves reward maps and deduplicated findings. These controls use `assertions=[]` because this public-only assignment has no recorded reference. No original scalar, native reference replay, action credit, qualification or training eligibility is asserted.

Remaining gap or scope boundary: Only the declared target row and exact requested cells are checked; arbitrary unrelated writes and alternative amount/text corruption cases are outside this bounded guard. No reference task replay exists.
