# Review: operations.hubspot_mailchimp_sync

Component evidence only; the whole task remains `not_qualified`. The official partial reference is preserved unchanged.

Draft SHA-256: `264566d2e4304894f9aa5e316b4a35b03d2c970ce83525144f0adc2520937a81`.
Native replay SHA-256: `9e0609638f2d68fd810222ced81a2c5f5dd79d2ea32b9bc3139eaebff52d7b7a`; rescore/reload/scalar/episode-byte parity: True/True/True/True; errors: 0.

## Expressed checks

- `sync-rules-read`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 8}]
- `hot-score-subscriber-tag-retained`: [{'status': 'valid', 'value': 0.0, 'reason': 'retained_record_predicate_verified', 'candidate_instances': 2}, {'status': 'inapplicable', 'value': None, 'reason': 'retained_record_not_required', 'candidate_instances': 6}]
- `warm-score-subscriber-tag-retained`: [{'status': 'inapplicable', 'value': None, 'reason': 'retained_record_not_required', 'candidate_instances': 6}, {'status': 'valid', 'value': 0.0, 'reason': 'retained_record_predicate_verified', 'candidate_instances': 2}]
- `cold-score-subscriber-tag-retained`: [{'status': 'inapplicable', 'value': None, 'reason': 'retained_record_not_required', 'candidate_instances': 8}]
- `opted-out-temperature-tags-removed`: [{'status': 'inapplicable', 'value': None, 'reason': 'retained_record_not_required', 'candidate_instances': 6}, {'status': 'valid', 'value': 0.0, 'reason': 'retained_record_predicate_verified', 'candidate_instances': 2}]

## Genuine-handler controls

Status: executed. Control artifact: `/tmp/automationbench-luna-operations-20261005-batch06/sync_controls.json`. Controls that ran preserve the original benchmark reward assertions and compare manifest rewards to an independently scored ordinary AutomationBenchTask fixture.

## Remaining public scope

- Only four initial Mailchimp subscribers are present for thirteen HubSpot contacts; adding absent subscribers and verifying all 13 outcomes is not covered.
- The public legal-hold rule is not closed across contacts with missing optional notes/lifecycle fields; sync-log writes are not checked.

Source file SHA-256 fingerprints are recorded in `review.json`.

## Run provenance archive

Native full scored episode and latest-complete-per-run extraction: `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/hubspot_mailchimp_sync_scored_episode.json` and `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/hubspot_mailchimp_sync.json` (SHA-256 `86a5a8e4b985f3e85376f62067506d667684040a185d99d144a34116ce62a08c`).

Genuine-handler controls are retained at `/tmp/automationbench-luna-operations-20261005-batch06/sync_controls.json` (SHA-256 `8a0ba7401b0ca9395c8549af00069055ca1b7b3e9aab179b64c0447ea022d1e3`), including lifecycle snapshots, one latest complete result per run ID, raw returned receipt envelopes and state-write ACK payloads. Each scenario records pre/post SHA-256 fingerprints for its effective core, handlers, Verifiers modules, and harness files. Prior control and compact replay artifacts remain preserved and linked in `review.json`.
