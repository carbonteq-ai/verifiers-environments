# sales.calendly_discovery_call (batch04)

The manifest reads both eligibility and role-event worksheets, requires current Gmail policy read, and prohibits routing the named CTO to Product Demo. The reference read the two worksheets but not the current email and booked no meeting. The public sheet maps CTO to Discovery, while a newer email pauses all CTO discovery bookings “this week” until further notice; the task has no current date to resolve whether the pause still applies.

Original Luna score: 0.000000 (official_zero). Native replay found 14 findings, no errors; source bytes and scalar rewards were unchanged, serialized reload/rescore findings matched.

Coverage: 3 expressed components; 2 gaps; 2 out of scope. Whole-task status: **not qualified**.

Limitations: The pause’s “this week” has no task-relative current date and the CRM has no booking date. The message also says “until further notice,” but the pack has no later clearance. Without time validity semantics, positive booking vs continued pause cannot be evaluated soundly. No reference-fitting date was added.

Simulator controls: native Product Demo booking for target CTO: cto_not_routed_to_demo=1 harm; missing acknowledgement for Product Demo booking: guard abstains as unknown.
