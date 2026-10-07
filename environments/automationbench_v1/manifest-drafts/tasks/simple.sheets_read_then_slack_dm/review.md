# simple.sheets_read_then_slack_dm

Public-only component assessment for the reserved `reward_test` input.

Current draft SHA-256: `0d11cf0fcc3c0c33d15345699bbb8bd8b27fcfd2c07be074e6d6b675014d65b2`. Public pack SHA-256: `26ed59295b49a23a3ba89d051239a368e5bfa77b922e75914e38e0f30dc1dd77`; input SHA-256: `49cdd2279579abbda0c163acdfcc9fd1acfd40d54467de1cd816a250ebd547d8`.

The contract now checks the acknowledged sheet read, an acknowledged Slack user lookup bound to the manager email and returned ID, and a persisted DM to that user after the lookup returns. The bounded wrong-recipient guard remains explicit. The DM content meaning is still a gap because semantic paraphrase cannot be decided by these predicates.

Current genuine-handler controls: [simple_sheets_read_then_slack_dm-lookup-controls-20261005.json](/tmp/automationbench-luna-simple-20261005-batch27/simple_sheets_read_then_slack_dm-lookup-controls-20261005.json) (SHA-256 `8af86de56049485190af3f15197b6c5e365ec5509e282b5163fa431d1d444365`), cases: ordered_correct, omitted, late, wrong_user, missing_lookup_ack, missing_send_ack. Each case records the exact executed draft hash, raw handler arguments/results/ACKs, native wire archive/hash, source fingerprints, full errors, findings and serialized reload comparison. The older pre-adapter evidence is preserved in `validation_history` and the original control artifact.

The task data preserves the exact public prompt, initial state and tool catalog. Ordinary and manifest reward maps match on the same synthetic input with `assertions=[]`; the default partial-credit scalar is zero and does not establish task success. No reference replay, original scalar, action credit, qualification or training eligibility is claimed.
