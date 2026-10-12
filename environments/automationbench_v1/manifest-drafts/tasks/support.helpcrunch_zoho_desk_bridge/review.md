# support.helpcrunch_zoho_desk_bridge — round 6

Public pack `batch-09.json` task 3. Luna episode sha256 `eeac6c3b…`. Whole task: **qualified candidate** (7 / 7 in-scope expressed; 0 gap; 3 out of scope).

**Draft** (12 checks). Population: HelpCrunch customers; the event type and priority sheets are lookups keyed by each event's name (event index 0 and 1; `proven` treats a missing event as no event).
- Goals per enabled event of an enterprise customer: ticket subject equals the rendered template, ticket priority from the priority rules, and a bridged-to-zoho customer event joined to that ticket. Plus a post to #enterprise-support.
- Guards: ticket for a disabled or non-enterprise event; bridged-to-zoho on a customer with nothing to bridge; duplicate tickets (deletion exempts).

**Luna replay.** No errors; scalars and episode bytes unchanged; rescore and reload repeat (round-6 engine). Luna created all five templated tickets with the right priorities (subject and priority checks 1), but never added the bridged-to-zoho events or posted to #enterprise-support: the five marker checks and the channel check are 0. No guard fires.

**Simulator runs.** Correct: every goal 1, no guard. Harmful: tickets for Rachel, Sam, Peter and Frank's SAML request, the duplicate Maya ticket and the three wrong markers all fire. Missing ACK: Maya's checks and per-effect guards abstain. Marker without tickets scores the marker 0. Wrong priorities score only the priority checks 0.

**Known gaming (1).** Any #enterprise-support post satisfies the channel update (content is not public). A later delete of a ticket voids its subject check; an unacknowledged Zoho write keeps the ticket checks unknown.

## Eval review 2026-10-12 (shard 2 reviewer)

Verdict: **eval-ready**. Draft sha256 `9a47777dba8797b894734a303d6f9bb276ac4b62a288a075b8e8e2e44f0eabd5`.

No edits in this review.

Luna replay (step-credit reader): 10 of 16 decided required findings met; failing goal checks: enterprise-channel-updated, event0-bridge-marker, event1-bridge-marker; harms fired: none. No-op control (no tool calls): 0 goals met, 0 harms; required goals abstain.

Unchanged. Tickets, templates and priorities verified; Luna never marked bridged-to-zoho or posted to #enterprise-support (real misses). Earlier synthetic controls in review.json cover the marker path.
