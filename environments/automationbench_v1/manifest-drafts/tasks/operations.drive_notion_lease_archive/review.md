# Review: operations.drive_notion_lease_archive

Component evidence only; the whole task remains `not_qualified`. The official partial reference is preserved unchanged.

Draft SHA-256: `dcab30e791261389e5d1c2b1b4afd8226332ed3162e27d523671aaf7f9785cb3`.
Native replay SHA-256: `75a913323d092feb062aeded1479948cc2d44d5ba8355dc6eff43baa33f8775c`; rescore/reload/scalar/episode-byte parity: True/True/True/True; errors: 0.

## Expressed checks

- `lease-status-sheet-read`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `lease-archive-policy-read`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `lease-email-read-1`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `lease-email-read-2`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `lease-email-read-3`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `lease-email-read-4`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `lease-email-read-5`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `lease-email-read-6`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]
- `lease-email-read-7`: [{'status': 'valid', 'value': 1.0, 'reason': 'obligation_witnessed_required_effect', 'candidate_instances': 2}]

## Genuine-handler controls

Status: executed. Control artifact: `/tmp/automationbench-luna-operations-20261005-batch06/drive_reads_controls.json`. Controls that ran preserve the original benchmark reward assertions and compare manifest rewards to an independently scored ordinary AutomationBenchTask fixture.

## Remaining public scope

- Public Google Drive action history names seven file IDs and titles, but the initial state has no typed Drive files or folders; Notion state and legal-parent page identity are absent. Read controls pass, but retained archive/page outcomes cannot be confirmed from this fixture.

Source file SHA-256 fingerprints are recorded in `review.json`.

## Run provenance archive

Native full scored episode and latest-complete-per-run extraction: `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/drive_notion_lease_archive_scored_episode.json` and `/tmp/automationbench-luna-operations-20261005-batch06/provenance_refresh/native/drive_notion_lease_archive.json` (SHA-256 `8e525df903ada365e701c5a53915e66576b87fcc98f0ca21d585029e096ab1eb`).

Genuine-handler controls are retained at `/tmp/automationbench-luna-operations-20261005-batch06/drive_reads_controls.json` (SHA-256 `1ad3539fd1cf335cb215a7984b6d0de0de392cdcca61487ba551b4c9158e8525`), including lifecycle snapshots, one latest complete result per run ID, raw returned receipt envelopes and state-write ACK payloads. Each scenario records pre/post SHA-256 fingerprints for its effective core, handlers, Verifiers modules, and harness files. Prior control and compact replay artifacts remain preserved and linked in `review.json`.
