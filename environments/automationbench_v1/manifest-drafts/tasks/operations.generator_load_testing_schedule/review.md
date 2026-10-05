# Review: operations.generator_load_testing_schedule

Component evidence only; the whole task remains `not_qualified`. The official partial reference is preserved unchanged.

Draft SHA-256: `a6a680085202e302571495274a4f17695846dae442878626cb949cd8161e7822`.
Native replay SHA-256: `7c55656c4ee17389af798a354487f0c1203282d797e0497b686071c2587fab76`; rescore/reload/scalar/episode-byte parity: True/True/True/True; errors: 0.

## Expressed checks

- `generator-unit-roster-read`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 16}]
- `assigned-facilities-engineers-read`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 16}]
- `each-due-generator-has-load-test-event`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 10}, {'status': 'inapplicable', 'value': None, 'reason': 'obligation_not_required', 'candidate_instances': 6}]
- `no-generator-test-while-under-repair-or-event-assigned`: []
- `facilities-engineer-1-emailed-total-test-count`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 6}, {'status': 'inapplicable', 'value': None, 'reason': 'obligation_not_required', 'candidate_instances': 10}]
- `facilities-engineer-2-emailed-total-test-count`: [{'status': 'inapplicable', 'value': None, 'reason': 'obligation_not_required', 'candidate_instances': 12}, {'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 4}]
- `facilities-engineer-3-emailed-total-test-count`: [{'status': 'inapplicable', 'value': None, 'reason': 'obligation_not_required', 'candidate_instances': 12}, {'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 4}]
- `facilities-engineer-4-emailed-total-test-count`: [{'status': 'inapplicable', 'value': None, 'reason': 'obligation_not_required', 'candidate_instances': 14}, {'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]

## Genuine-handler controls

Status: executed. Control artifact: `/tmp/automationbench-luna-operations-20261005-batch06/generator_controls.json`. Controls that ran preserve the original benchmark reward assertions and compare manifest rewards to an independently scored ordinary AutomationBenchTask fixture.

## Remaining public scope

- Emails to the four unique engineer addresses are tested with the shared aggregate count; wording could imply one email per assigned building, while policy gives no separate per-building count, so per-building cardinality is not claimed.
- Exact emergency-run note handling is bound to the one public row; broader varied note/date parsing behavior is untested.

Source file SHA-256 fingerprints are recorded in `review.json`.

## Run provenance archive

Native full scored episode and latest-complete-per-run extraction: `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/generator_load_testing_schedule_scored_episode.json` and `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/generator_load_testing_schedule.json` (SHA-256 `5f6455f83bce6beafadce386a17749bf8102320aeba321061f2db4c144f25fdb`).

Genuine-handler controls are retained at `/tmp/automationbench-luna-operations-20261005-batch06/generator_controls.json` (SHA-256 `d30a411c94c248e29b495205e12ba319fc4256433ddc970c913bc8590f240fce`), including lifecycle snapshots, one latest complete result per run ID, raw returned receipt envelopes and state-write ACK payloads. Each scenario records pre/post SHA-256 fingerprints for its effective core, handlers, Verifiers modules, and harness files. Prior control and compact replay artifacts remain preserved and linked in `review.json`.
