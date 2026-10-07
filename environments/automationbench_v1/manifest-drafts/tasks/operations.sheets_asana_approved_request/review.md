# operations.sheets_asana_approved_request — public component review

Status: **not qualified**. This is a public-only component draft for reserved `reserved` input; the reference episode and hidden evaluator were not read. Training eligibility remains ungranted.

Draft: `draft.json`, SHA-256 `3685bf24b406e127ec8e2c0d8cd26ed0542dbd5bb43b08b4c5dd388266a07817`. Public input hash: `0d3e3501fe59a28230d302a60c7641c54bba1c4d681c0875ff294d87ff9fffae`. Pack SHA-256: `32899f5b41f2be22bb139fadf50f7d0a2750cb8171b9fb1d26545cec4564a353` (index 1).

Expressed from public sources:
- Guard rejects an Asana task naming a request explicitly excluded by public eligibility notes (hold, duplicate, budget freeze, superseded, assessment-only, inspection pending, retracted)
- Guard discriminates correct harmless nonexcluded HVAC task from held fridge task in synthetic handler controls

Remaining public obligations and limits:
- No positive goal currently verifies a valid Facilities action, request eligibility, Asana project/section/due date or task description fields
- No email read obligation verifies whether request was reapproved; the prompt explicitly requires an audit note
- Several same-priority eligible requests remain and no public ranking rule resolves “most urgent”; retain this ambiguity instead of selecting an arbitrary row

Validation: three genuine-handler synthetic component controls (positive, adverse, missing ACK) per task; each uses the exact public prompt/tool list and normalized initial state, raw handler materials and native dispatch/return envelopes, plus a distinct scored WireEpisode archive. Scalar values compare ordinary and manifest tasks with an empty assertion set only; this is harness parity, not hidden benchmark parity. Rescore findings match after ignoring the naturally different run ID; full reward maps match, no assessment/credit errors were recorded. Source files in the control artifact have before/after SHA maps (24 source modules) with no drift.

Controls artifact: `/tmp/automationbench-luna-operations09-20261005/controls_full_v4_reviewable.json` (SHA `6747613d458c87bb7d6d616bb622be2cc7577ef48416ae485756d166d40547af`); raw run snapshot: `/tmp/automationbench-luna-operations09-20261005/controls_full_v4_run_immutable.json` (SHA `cd6cd6e70d5b1c86c44eee51ae1ae587248cb7a6eba746ba1fca6858e6afbe78`). Full tool arguments/results, raw receipt material, archive paths and per-check findings are in the JSON artifact and this folder's `review.json`.
