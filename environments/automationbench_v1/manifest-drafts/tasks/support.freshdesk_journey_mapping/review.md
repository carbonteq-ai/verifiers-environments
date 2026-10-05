# support.freshdesk_journey_mapping

Public-only authored partial manifest. No recorded reference, held-out outcome, hidden assertion or eligibility information was consulted.

Draft SHA-256: `ec825548b8e080147f22baf3ab2bcd4dcf34ba566c89b7d567352be6ee63c522`.
Source pack SHA-256: `f0bb907f040ac72f5caf2e395cf721d17800a93cc7b7253d9c82920162f32e02`.
Public input SHA-256: `2713306fc7bc764852ac0c50fde86d6d0f99bc267b62b4eaba6f913c61f27798`.

Fixture authority: this review binds directly to `tasks[task_name].public_input` from the cited pack. The control `AutomationBenchData` preserves that exact public `initial_state`, full system+user prompt, and tool list; each synthetic fixture was compared to those original values. Native assessment projects `task_evidence.initial` through `public_initial_state`, which flattens nested Google Sheets rows using the simulator schema and leaves other supplied services intact. Binding hashes use that same native normalized view; they do not replace the public fixture or authorize a different input. See `binding_normalization` and the binding digests in `review.json`.

Synthetic component controls: 9 (correct/harm/missing acknowledgement for 3 checks), using the exact public prompt, initial state and tools with native simulator handlers.

The separate standard-task score uses the same synthetic public fixture with empty assertions; scalar-map equality is harness parity only. It does not compare against the original benchmark baseline. Hidden assertions/outcomes, ordinary benchmark comparison and recorded-trajectory replay remain unavailable and unconsulted.

| Check | Role | Correct | Harm | Missing ACK |
|---|---|---:|---:|---:|
| `sync-healthy-existing-hubspot-contact` | goal | valid 1.0 (obligation_witnessed_required_effect) | valid 0.0 (obligation_required_effect_missing) | abstained — (obligation_effect_scope_unavailable) |
| `append-healthy-journey-row` | goal | valid 1.0 (obligation_witnessed_required_effect) | valid 0.0 (obligation_required_effect_missing) | abstained — (obligation_effect_scope_unavailable) |
| `post-journey-contact-result` | goal | valid 1.0 (obligation_witnessed_required_effect) | valid 0.0 (obligation_required_effect_missing) | abstained — (obligation_effect_scope_unavailable) |

Whole-task status: `not_qualified`. Public-population, eligibility, exact report amounts/counts, and unresolved cross-system joins remain explicit gaps in the structured review.
