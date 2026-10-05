# Review: operations.hubspot_ticket_escalation

Component evidence only; the whole task remains `not_qualified`. The official partial reference is preserved unchanged.

Draft SHA-256: `175affdaff3c743d0b839c0ef17e6b3cfff7cded6bef607aac1a188aaa4e0749`.
Native replay SHA-256: `6f10f2167bed2163559d3c25ddcd363f39054ec6437fbacd6eb7721457af6528`; rescore/reload/scalar/episode-byte parity: True/True/True/True; errors: 0.

## Expressed checks

- `escalation-guidelines-read`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]
- `latest-urgent-customer-message-read`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `active-acme-incident-bridge-read`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]
- `high-priority-acme-ticket-with-public-cost-and-bridge`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]
- `support-escalation-channel-notified`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]
- `customer-acknowledgment-sent`: [{'status': 'valid', 'value': 0.0, 'reason': 'obligation_required_effect_missing', 'candidate_instances': 2}]

## Genuine-handler controls

Status: executed under the current helper (`c108f6f5576446a35ed29fab4d91ea2eb32ee23810aa304fb02fb2bb5b1dc6b0`). The refreshed controls preserve original benchmark reward assertions, compare manifest rewards to independently scored ordinary AutomationBenchTask fixtures, and record exact public initial-state parity for each scenario.

## Remaining public scope

- This checks the public Acme active-incident customer case only; complete ordering/reply-status selection across every urgent inbox email, all exclusion rules, and exact ticket-ID inclusion in customer acknowledgment remain unsupported.

Source file SHA-256 fingerprints are recorded in `review.json`.

## Run provenance archive

Native full scored episode and latest-complete-per-run extraction: `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/hubspot_ticket_escalation_scored_episode.json` and `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/hubspot_ticket_escalation.json` (SHA-256 `2d60cb8016f81759b58bb2fe15ebf545f8f4ef490e7f0cd2f06c735c16781791`).

Genuine-handler controls are retained at `/tmp/automationbench-luna-operations-20261005-batch06/ticket_controls.json` (SHA-256 `c854a79a5fe451961cc042cc93d2505a54488b6b358f5ffd1ebaecc565b86a86`), including lifecycle snapshots, one latest complete result per run ID, raw returned receipt envelopes and state-write receipt payloads. Each scenario records pre/post source fingerprints, ordinary and manifest reward maps, and a public initial-state parity assertion. The earlier artifact and its historical helper fingerprint are preserved under `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/history/`; provenance details are linked in `review.json`.
