# sales.champion_change_alert batch09 public-only review

This reserved evaluation task has no recorded Luna reference episode or score. The artifact is public-source-only authoring; it does not claim replay, task reward parity, training eligibility, or qualification.

Assignment: `91fc8d7578dff2611d6edd4aa8537763067edfc44f6f6c9cbe96b89c0e6ce28b`. Public input: `fc6ab4a1070b99d900230ecf40f86add2ff4dec40c2a8f29ce68dc692227b887`. Current draft: `574198fc39f3b3dd0a528580b884e854006f9ab0f0cb9d5073b10aff0e4af33b`.

The handler control reads the name-matching Gary profile, but the opportunity contact and LinkedIn profile emails conflict (`gary@champgone.example.com` vs `gary@newjob.example.com`). Name alone does not establish identity; no alert or contact update is asserted. The missing-ACK read control abstains because the native read receipt is unresolved.

Native genuine-handler component controls: 3. They used the complete public prompt, exact public initial input and declared tool catalog. Each control preserves dispatch/return envelopes, dynamic arguments, returned results, ACK/write receipts, pre/post state snapshots, actual numeric ordinary/manifest maps, and a serialized scored component episode that was reloaded and rescored.

Control cases:
- `profile-cross-reference`: sales.champion_change_alert.linkedin_cross_reference=1.0 (obligation_witnessed_required_effect), sales.champion_change_alert.linkedin_cross_reference.coverage=1.0 (obligation_scope_closed); missing ACK indices none; map equality True; scored reload equality True; source hashes stable True. Evidence: `/tmp/automationbench-luna-sales-batch09-public-20261005/controls/sales.champion_change_alert/profile-cross-reference/control.json`.
- `profile-read-missing-ack`: sales.champion_change_alert.linkedin_cross_reference=None (obligation_effect_scope_unavailable), sales.champion_change_alert.linkedin_cross_reference.coverage=None (obligation_scope_unavailable); missing ACK indices [0]; map equality True; scored reload equality True; source hashes stable True. Evidence: `/tmp/automationbench-luna-sales-batch09-public-20261005/controls/sales.champion_change_alert/profile-read-missing-ack/control.json`.
- `wrong-profile`: sales.champion_change_alert.linkedin_cross_reference=0.0 (obligation_required_effect_missing), sales.champion_change_alert.linkedin_cross_reference.coverage=1.0 (obligation_scope_closed); missing ACK indices none; map equality True; scored reload equality True; source hashes stable True. Evidence: `/tmp/automationbench-luna-sales-batch09-public-20261005/controls/sales.champion_change_alert/wrong-profile/control.json`.

Each ordinary/manifest numeric map is the zero-assertion harness output because this pack has no assertions. Equal maps are only a fixture/harness check. Outcome evidence remains separate from action credit. Coverage is partial authoring only; action credit and qualification are not granted.
