# Review: operations.monday_calendar_emergency_drill

Component evidence only; the whole task remains `not_qualified`. The official partial reference is preserved unchanged.

Draft SHA-256: `b0a06ed7c31a4e33ac34fbe881f8b1cc4ce1d9c33fda6133c181acc2ec449ad2`.
Native replay SHA-256: `48a3813b4cfa1d0c8a6ae1fa30d5d1b841ae9b4d444bc078e025ff00ed2edb3d`; rescore/reload/scalar/episode-byte parity: True/True/True/True; errors: 0.

## Expressed checks

- `latest-hq-emergency-drill-email-read`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `hq-drill-calendar-updated-to-latest-email`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `hq-monday-item-updated-to-rescheduled-date`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]

## Genuine-handler controls

Status: executed. Control artifact: `/tmp/automationbench-luna-operations-20261005-batch06/handler_controls_batch06.json`. Controls that ran preserve the original benchmark reward assertions and compare manifest rewards to an independently scored ordinary AutomationBenchTask fixture.

## Remaining public scope

- The prompt makes an after-hours #emergency-team notice conditional but provides no public boundary for after-hours.

Source file SHA-256 fingerprints are recorded in `review.json`.

## Run provenance archive

Native full scored episode and latest-complete-per-run extraction: `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/monday_calendar_emergency_drill_scored_episode.json` and `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/monday_calendar_emergency_drill.json` (SHA-256 `be2e9655fdd9000441e8825d5a732920c81f6cffdf25fedb69bced6357a53674`).

Genuine-handler controls are retained at `/tmp/automationbench-luna-operations-20261005-batch06/handler_controls_batch06.json` (SHA-256 `2d94d9ddbb3490399ae51d93b12fa97c4a75447e8a4a752950133debe4796217`), including lifecycle snapshots, one latest complete result per run ID, raw returned receipt envelopes and state-write ACK payloads. Each scenario records pre/post SHA-256 fingerprints for its effective core, handlers, Verifiers modules, and harness files. Prior control and compact replay artifacts remain preserved and linked in `review.json`.
