# Review: operations.calendar_airtable_maintenance

Component evidence only; the whole task remains `not_qualified`. The official partial reference is preserved unchanged.

Draft SHA-256: `9a9e4327be65dec9382753b7ff0889a322dba8eefe400b41de41c9183dcb398a`.
Native replay SHA-256: `cf167f0b28dcc6b7ee5b391c2242737a0e75b1f4fac5740a966fc1e45771c896`; rescore/reload/scalar/episode-byte parity: True/True/True/True; errors: 0.

## Expressed checks

- `maintenance-windows-read`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `base-scheduling-policy-read`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]
- `q1-maintenance-policy-read`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]
- `vendor-confirmation-log-read`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]
- `feb-12-vendor-confirmation-read`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `confirmed-next-window-added-to-ops-calendar`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]

## Genuine-handler controls

Status: executed. Control artifact: `/tmp/automationbench-luna-operations-20261005-batch06/handler_controls_batch06.json`. Controls that ran preserve the original benchmark reward assertions and compare manifest rewards to an independently scored ordinary AutomationBenchTask fixture.

## Remaining public scope

- The public request requires Airtable base/table/record changes, but the public initial fixture has no Airtable service/records; no target state was fabricated.
- The recorded Luna path has no matching event; the check verifies only the named, publicly anchored Feb 12 event component.

Source file SHA-256 fingerprints are recorded in `review.json`.

## Run provenance archive

Native full scored episode and latest-complete-per-run extraction: `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/calendar_airtable_maintenance_scored_episode.json` and `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/calendar_airtable_maintenance.json` (SHA-256 `2ffb39ae943d4a58a5c64f0c9a8c118c2913e8a503dbcb40743bd6ec70f33346`).

Genuine-handler controls are retained at `/tmp/automationbench-luna-operations-20261005-batch06/handler_controls_batch06.json` (SHA-256 `2d94d9ddbb3490399ae51d93b12fa97c4a75447e8a4a752950133debe4796217`), including lifecycle snapshots, one latest complete result per run ID, raw returned receipt envelopes and state-write ACK payloads. Each scenario records pre/post SHA-256 fingerprints for its effective core, handlers, Verifiers modules, and harness files. Prior control and compact replay artifacts remain preserved and linked in `review.json`.
