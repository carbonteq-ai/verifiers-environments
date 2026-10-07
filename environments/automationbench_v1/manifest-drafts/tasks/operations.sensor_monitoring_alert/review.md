# operations.sensor_monitoring_alert manifest review

The draft is bound to public pack index 7 and the exact public prompt and initial state. Original recorded outcome remains **official_zero**, partial reward 0.0; this is manifest component evidence, not qualification.

- Draft SHA-256: `40348f57139e7d83ac4eb4a9e2cf77146e3b88f588b78e131011c14b9806edcb`
- Public prompt SHA-256: `e42f00676bd393f6b5e620ae6f98bcde2c516e27d8544207ef6bac23cbf99529`
- Public initial-state SHA-256: `520c4085eec6912a5cccf649bcd4fd03651cd026d91c352e7e6da00010969130`
- Original episode SHA-256: `cdf81697abe140806c20196a8be166880991197a72312c873e911e89e8e263b9`
- Native score / rescore / reload-rescore parity: `True`; ordinary scalar unchanged: `True`; source bytes unchanged: `True`; errors: 0.

Sensor and policy reads: the newest policy and maintenance log are witnessed, but dashboard rows read is not. Two active low-reading candidate email obligations and the summary notice are missing. East Wing in-progress work-zone rows remain explicitly excluded; the public fixture bounds this guard to that one named zone.

## Check outcomes

- `facilities-alert-summary`: valid 0.0 (obligation_required_effect_missing) ×1
- `flagged-sensor-email`: inapplicable None (obligation_not_required) ×22, valid 0.0 (obligation_required_effect_missing) ×2
- `maintenance-log-read`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `sensor-policy-q1-read`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `sensor-policy-read`: valid 1.0 (obligation_witnessed_required_effect) ×1
- `sensor-readings-read`: valid 0.0 (obligation_required_effect_missing) ×1

## Controls and qualification

The native three-phase replay verifies deterministic scoring and serialization. It does not by itself validate correct, alternative, harmful, or missing-ACK behavior. A complete task-bound genuine-handler control family is not claimed here; see `review.json` for the recorded probe evidence and source hashes. Whole-task qualification remains not granted.

Task-bound correct, alternative, harmful and missing-ACK controls use exact public state and genuine Sheet, Gmail and Slack handlers. Scenario rewards match ordinary AutomationBench rewards; dispatch/return receipts and source fingerprints are persisted at `/tmp/automationbench-luna-operations-20261005-batch07/sensor_controls.json`. These controls verify the sensor alert components only.

Correct, alternative, work-zone harm and missing-ACK controls ran through genuine simulator handlers and compare against independently scored ordinary AutomationBench rewards. Raw dispatch/return receipts, ACKs, findings and source fingerprints: `/tmp/automationbench-luna-operations-20261005-batch07/sensor_controls.json`. Whole-task qualification remains not granted.

## Shared-source refresh (2026-10-05)

After the shared source-position selection and Buffer channel-read changes settled, the native three-phase replay and all persisted genuine-handler controls for this task were executed again. Current results are recorded in `/tmp/automationbench-luna-operations-20261005-batch07/operations07_shared_source_refresh.json`; prior run artifacts and reviews remain under `/tmp/automationbench-luna-operations-20261005-batch07/history_pre_shared_source_refresh_20261005`. The current replay retained findings/scalar/source-byte parity with zero errors. Control ordinary and manifest reward maps match in every rerun variant. Current source snapshot: 46 hashed files of 54 requested paths; missing source paths are listed in the linked JSON artifact. These component results do not grant whole-task qualification.
