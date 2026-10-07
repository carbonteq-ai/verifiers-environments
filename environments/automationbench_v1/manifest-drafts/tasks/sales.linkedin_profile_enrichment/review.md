# sales.linkedin_profile_enrichment batch09 public-only review

This reserved evaluation task has no recorded Luna reference episode or score. The artifact is public-source-only authoring; it does not claim replay, task reward parity, training eligibility, or qualification.

Assignment: `91fc8d7578dff2611d6edd4aa8537763067edfc44f6f6c9cbe96b89c0e6ce28b`. Public input: `b82c10ab9cd2d1078eeeba83c5cafda83b20136a72717fc2395023c7641b5316`. Current draft: `b52b5ce4b6a601f1368b059bb4851bbd4e101a1f70eba4b5e6cd176be38ed1bb`.

The control reads one DataFlow Systems LinkedIn profile. The public initial state does not safely bind that person to the generic Salesforce lead or specify which fields to write; candidate selection, accurate enrichment, and opt-out handling remain unsupported. A missing read ACK makes that profile evidence unknown.

Native genuine-handler component controls: 3. They used the complete public prompt, exact public initial input and declared tool catalog. Each control preserves dispatch/return envelopes, dynamic arguments, returned results, ACK/write receipts, pre/post state snapshots, actual numeric ordinary/manifest maps, and a serialized scored component episode that was reloaded and rescored.

Control cases:
- `dataflow-profile-read`: sales.linkedin_profile_enrichment.linkedin_data_read=1.0 (obligation_witnessed_required_effect), sales.linkedin_profile_enrichment.linkedin_data_read.coverage=1.0 (obligation_scope_closed); missing ACK indices none; map equality True; scored reload equality True; source hashes stable True. Evidence: `/tmp/automationbench-luna-sales-batch09-public-20261005/controls/sales.linkedin_profile_enrichment/dataflow-profile-read/control.json`.
- `profile-read-missing-ack`: sales.linkedin_profile_enrichment.linkedin_data_read=None (obligation_effect_scope_unavailable), sales.linkedin_profile_enrichment.linkedin_data_read.coverage=None (obligation_scope_unavailable); missing ACK indices [0]; map equality True; scored reload equality True; source hashes stable True. Evidence: `/tmp/automationbench-luna-sales-batch09-public-20261005/controls/sales.linkedin_profile_enrichment/profile-read-missing-ack/control.json`.
- `wrong-profile`: sales.linkedin_profile_enrichment.linkedin_data_read=0.0 (obligation_required_effect_missing), sales.linkedin_profile_enrichment.linkedin_data_read.coverage=1.0 (obligation_scope_closed); missing ACK indices none; map equality True; scored reload equality True; source hashes stable True. Evidence: `/tmp/automationbench-luna-sales-batch09-public-20261005/controls/sales.linkedin_profile_enrichment/wrong-profile/control.json`.

Each ordinary/manifest numeric map is the zero-assertion harness output because this pack has no assertions. Equal maps are only a fixture/harness check. Outcome evidence remains separate from action credit. Coverage is partial authoring only; action credit and qualification are not granted.
