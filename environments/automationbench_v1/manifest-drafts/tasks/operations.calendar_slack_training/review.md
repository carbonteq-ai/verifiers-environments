# Review: operations.calendar_slack_training

Component evidence only; the whole task remains `not_qualified`. The official partial reference is preserved unchanged.

Draft SHA-256: `2fa5b351d69e17777ab55c86edafb0f31a9c1dacfd90f85a6fc3936c86b2b093`.
Native replay SHA-256: `99b02ad938b2cdc69939d5cd304f8953698eea92e208031c1e7b856c2f8c37ef`; rescore/reload/scalar/episode-byte parity: True/True/True/True; errors: 0.

## Expressed checks

- `training-session-schedule-read`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `training-policy-read`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `location-requirement-read`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `blackout-date-read`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `next-eligible-forklift-training-added-to-calendar`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]
- `training-notice-to-ops-updates`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]

## Genuine-handler controls

Status: executed. Control artifact: `/tmp/automationbench-luna-operations-20261005-batch06/handler_controls_batch06.json`. Controls that ran preserve the original benchmark reward assertions and compare manifest rewards to an independently scored ordinary AutomationBenchTask fixture.

## Remaining public scope

- The check validates the public selected Feb 6 session component; complete global candidate/room/blackout enumeration across altered public inputs is not established.
- The earliest eligible date is used from the supplied schedule; the public request gives no independent clock beyond the cited calendar.

Source file SHA-256 fingerprints are recorded in `review.json`.

## Run provenance archive

Native full scored episode and latest-complete-per-run extraction: `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/calendar_slack_training_scored_episode.json` and `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/calendar_slack_training.json` (SHA-256 `a9c68310acc125216180fccb590c1d8db0a4e5236aebc9bb7904847cb765bf93`).

Genuine-handler controls are retained at `/tmp/automationbench-luna-operations-20261005-batch06/handler_controls_batch06.json` (SHA-256 `2d94d9ddbb3490399ae51d93b12fa97c4a75447e8a4a752950133debe4796217`), including lifecycle snapshots, one latest complete result per run ID, raw returned receipt envelopes and state-write ACK payloads. Each scenario records pre/post SHA-256 fingerprints for its effective core, handlers, Verifiers modules, and harness files. Prior control and compact replay artifacts remain preserved and linked in `review.json`.
