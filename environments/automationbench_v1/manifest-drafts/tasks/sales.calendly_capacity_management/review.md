# sales.calendly_capacity_management (batch04)

The contract now calculates closed terminal event counts per initial rep candidate for 23 Feb–1 Mar and tests Discovery ≤8, Demo ≤4 and Total ≤10. It also requires a #capacity-alerts summary. Original replay has Alice out of capacity; Bob and Carol satisfy the thresholds. A genuine two-event Alice cancellation makes all three candidates pass. The reference posted no summary and made no capacity change.

Original Luna score: 0.000000 (official_zero). Native replay found 20 findings, no errors; source bytes and scalar rewards were unchanged, serialized reload/rescore findings matched.

Coverage: 4 expressed components; 1 gaps; 2 out of scope. Whole-task status: **not qualified**.

Limitations: The manifest can check final weekly per-rep limits and channel presence, but does not bind a principled set of cancellations or prove which invitees are affected and notified; no per-invitee communication requirement is expressed. The policy gives counts but no priority order for choosing events to cancel. The 2-event synthetic control is an outcome check, not an asserted unique cancellation policy.

Simulator controls: cancel two active Alice Discovery meetings during requested week: next_week_capacity_limits=1 for all three reps after cancellation; this is retained outcome only, not cancellation action credit; cancel a different two Alice Discovery events on Feb 24: next_week_capacity_limits=1 for all three reps; second valid set demonstrates no policy-specific event choice; missing acknowledgement for one of the two cancellations: final retained capacity outcome remains 1 for all three reps; no action credit is declared.
