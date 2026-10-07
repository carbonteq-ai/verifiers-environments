# operations.mailchimp_campaign_tracking manifest review

The draft is bound to public pack index 2 and the exact public prompt/initial state. Original official outcome remains **official_zero**, partial reward 0.0. Qualification remains not granted.

- Draft SHA-256: `c5a83171a5fdacb4e49e4fe5a420917ecde8ffcbdb634076f44a1503c2b3b966`
- Public prompt SHA-256: `f7a8c094506f5ced8bba502190b395dc55111cabd81e483a367019b55d46f2f0`
- Public initial-state SHA-256: `ca8474f0fbc631b04b153b0eb28ea9121ff8282cdbba1795d9b52c6a51080abd`
- Original episode SHA-256: `2c83ad8ec1a88a631f2d901ffeebddfb0a5151f7b4d4c92933946f647c667a25`
- Native score/rescore/reload-rescore parity: `True`; ordinary scalar unchanged: `True`; source bytes unchanged: `True`; errors: 0.

Campaign declares a native acknowledged Mailchimp list-read source. Candidate-specific cleaned subscribers join to the same public aud_main row returned before Airtable updates; the report-send goal also requires an ordered aud_main read. Correct/alternative, wrong-recipient harm, missing/late/wrong-list read and read-ACK controls were executed with genuine handlers. The public Contacts table is empty, so no update target is available. Original Luna trace retains the update/report misses; no qualification is claimed.

## Native check outcomes

- `bounce-report-sent-to-policy-recipient`: valid 0.0 (obligation_required_effect_missing) ×1
- `cleaned-subscriber-airtable-status-invalid`: inapplicable None (obligation_not_required) ×5, valid 0.0 (obligation_required_effect_missing) ×2
- `mailchimp-bounce-rules-read`: valid 1.0 (obligation_witnessed_required_effect) ×1

## Genuine-handler controls

Controls with raw dispatch/return/ACK receipts, ordinary and manifest reward maps, latest-complete-per-run findings and pre/post fingerprints are saved at `/tmp/automationbench-luna-operations-20261005-batch07/campaign_tracking_controls.json`.

- `correct`: `bounce-report-sent-to-policy-recipient` valid 1.0 after aud_main read; Airtable update unavailable because public Contacts is empty
- `alternative`: `bounce-report-sent-to-policy-recipient` valid 1.0 after aud_main read
- `harmful`: `bounce-report-not-sent-to-unlisted-recipient` valid 1.0
- `missing_ack`: `bounce-report-sent-to-policy-recipient` abstained when Gmail send ACK absent
- `missing_read`: `bounce-report-sent-to-policy-recipient` valid 0.0
- `late_read`: `bounce-report-sent-to-policy-recipient` valid 0.0; list read returns after report dispatch
- `wrong_scope`: `bounce-report-sent-to-policy-recipient` valid 0.0; read is for aud_other
- `read_missing_ack`: `bounce-report-sent-to-policy-recipient` abstained when aud_main list-read ACK absent

The retained Luna result remains partial. Native replay parity confirms deterministic declaration execution and serialization, not successful task completion.

## Shared-source refresh (2026-10-05)

After the shared source-position selection and Buffer channel-read changes settled, the native three-phase replay and all persisted genuine-handler controls for this task were executed again. Current results are recorded in `/tmp/automationbench-luna-operations-20261005-batch07/operations07_shared_source_refresh.json`; prior run artifacts and reviews remain under `/tmp/automationbench-luna-operations-20261005-batch07/history_pre_shared_source_refresh_20261005`. The current replay retained findings/scalar/source-byte parity with zero errors. Control ordinary and manifest reward maps match in every rerun variant. Current source snapshot: 46 hashed files of 54 requested paths; missing source paths are listed in the linked JSON artifact. These component results do not grant whole-task qualification.
